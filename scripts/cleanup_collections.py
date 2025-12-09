#!/usr/bin/env python3
"""
Clean up Couchbase collections for fresh test runs.

Deletes all documents from:
- generations (all prompts)
- generation_stats (statistics)
- eras (era metadata)

Preserves:
- unstructured (raw corpus data - reusable across experiments)

Note: The 'prompts' collection is deprecated and no longer used.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.couchbase_client import CouchbaseClient


def count_documents(cb: CouchbaseClient, collection_name: str) -> int:
    """Count documents in a collection."""
    query = f"SELECT COUNT(*) as count FROM {collection_name}"
    try:
        result = cb.scope.query(query)
        rows = list(result.rows())
        if rows and len(rows) > 0:
            return rows[0].get('count', 0)
        return 0
    except Exception as e:
        print(f"  Error counting {collection_name}: {e}")
        return 0


def delete_all_documents(cb: CouchbaseClient, collection_name: str) -> int:
    """Delete all documents from a collection. Returns count deleted."""
    # First get count before deleting
    count_before = count_documents(cb, collection_name)

    if count_before == 0:
        return 0

    query = f"DELETE FROM {collection_name}"
    try:
        print(f"    Deleting from {collection_name} ({count_before} docs)...", end=" ", flush=True)

        # Execute the delete using scope.query() to set proper context
        result = cb.scope.query(query)

        # IMPORTANT: Must consume the result to actually execute the DELETE
        list(result.rows())

        # Verify deletion by counting again
        count_after = count_documents(cb, collection_name)
        actual_deleted = count_before - count_after

        print(f"✓ {actual_deleted} deleted")

        if actual_deleted != count_before:
            print(f"    WARNING: Expected to delete {count_before}, actually deleted {actual_deleted}")

        return actual_deleted
    except Exception as e:
        print(f"\n  ✗ Error deleting from {collection_name}: {e}")
        import traceback
        traceback.print_exc()
        return 0


def main():
    """Main cleanup routine."""
    # Collections to clean (everything except unstructured)
    collections_to_clean = [
        'generations',
        'generation_stats',
        'eras'
    ]

    print("=" * 70)
    print("COUCHBASE COLLECTION CLEANUP")
    print("=" * 70)
    print()
    print("This will DELETE ALL DOCUMENTS from the following collections:")
    for coll in collections_to_clean:
        print(f"  - {coll}")
    print()
    print("The 'unstructured' collection will be PRESERVED.")
    print()

    # Show current document counts
    print("Current document counts:")
    print("-" * 40)

    with CouchbaseClient() as cb:
        print(f"✓ Connected to Couchbase: {cb.bucket_name}/{cb.scope_name}")

        for coll in collections_to_clean:
            count = count_documents(cb, coll)
            print(f"  {coll:20} {count:>6} documents")

        print()

        # Confirmation
        response = input("Proceed with deletion? (type 'yes' to confirm): ").strip().lower()

        if response != 'yes':
            print(f"\n✗ Cancelled (you typed '{response}'). No data was deleted.")
            print("  Note: You must type exactly 'yes' to proceed.")
            return

        print()
        print("Deleting documents...")
        print("-" * 40)

        total_deleted = 0

        for coll in collections_to_clean:
            deleted = delete_all_documents(cb, coll)
            print(f"  {coll:20} {deleted:>6} deleted")
            total_deleted += deleted

        print()
        print("=" * 70)
        print(f"COMPLETE: {total_deleted} total documents deleted")
        print("=" * 70)


if __name__ == "__main__":
    main()
