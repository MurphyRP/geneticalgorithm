#!/usr/bin/env python3
"""
Couchbase Database Setup Script

Creates the required bucket, scope, and collections for the genetic prompt
evolution framework.

Usage:
    python scripts/setup_couchbase.py [--verify] [--dry-run] [--force] [--json]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from couchbase.management.buckets import BucketSettings, BucketType, StorageBackend
from couchbase.exceptions import (
    BucketAlreadyExistsException,
    ScopeAlreadyExistsException,
    CollectionAlreadyExistsException,
    BucketNotFoundException,
    ScopeNotFoundException
)
from src.couchbase_client import CouchbaseClient


# Database structure constants
BUCKET_NAME = "genetic"
SCOPE_NAME = "g_scope"
COLLECTIONS = [
    "unstructured",       # Corpus text chunks
    "generations",        # All evolved prompts
    "generation_stats",   # Per-generation statistics
    "eras"                # Experiment configurations
]


def check_env_vars():
    """Check that required environment variables are set."""
    required_vars = [
        "COUCHBASE_CONNECTION_STRING",
        "COUCHBASE_USERNAME",
        "COUCHBASE_PASSWORD",
        "COUCHBASE_BUCKET",
        "COUCHBASE_SCOPE"
    ]

    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        return False, f"Missing environment variables: {', '.join(missing)}"

    # Verify bucket/scope match constants
    if os.getenv("COUCHBASE_BUCKET") != BUCKET_NAME:
        return False, f"COUCHBASE_BUCKET should be '{BUCKET_NAME}' but is '{os.getenv('COUCHBASE_BUCKET')}'"

    if os.getenv("COUCHBASE_SCOPE") != SCOPE_NAME:
        return False, f"COUCHBASE_SCOPE should be '{SCOPE_NAME}' but is '{os.getenv('COUCHBASE_SCOPE')}'"

    return True, "Environment variables configured correctly"


def test_connection():
    """Test Couchbase connection."""
    try:
        with CouchbaseClient() as cb:
            return True, "Connection successful"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"


def verify_structure(cb: CouchbaseClient):
    """Verify the database structure exists and is accessible."""
    results = {
        "bucket": False,
        "scope": False,
        "collections": {}
    }

    try:
        # Try to access bucket
        bucket = cb.cluster.bucket(BUCKET_NAME)
        bucket.ping()
        results["bucket"] = True

        # Try to access scope
        try:
            scopes = bucket.collections().get_all_scopes()
            scope_exists = any(s.name == SCOPE_NAME for s in scopes)
            results["scope"] = scope_exists

            if scope_exists:
                # Check collections
                for scope in scopes:
                    if scope.name == SCOPE_NAME:
                        existing_collections = {c.name for c in scope.collections}
                        for coll_name in COLLECTIONS:
                            results["collections"][coll_name] = coll_name in existing_collections
        except Exception as e:
            results["scope"] = False

    except Exception as e:
        results["bucket"] = False

    return results


def create_bucket(cb: CouchbaseClient, force=False):
    """Create bucket if it doesn't exist."""
    bucket_mgr = cb.cluster.buckets()

    try:
        # Check if bucket exists
        try:
            bucket_mgr.get_bucket(BUCKET_NAME)
            if force:
                bucket_mgr.drop_bucket(BUCKET_NAME)
                # Wait for bucket to be dropped
                import time
                time.sleep(2)
            else:
                return "skipped", "Bucket already exists"
        except BucketNotFoundException:
            pass  # Bucket doesn't exist, will create

        # Create bucket with minimal settings for development
        settings = BucketSettings(
            name=BUCKET_NAME,
            bucket_type=BucketType.COUCHBASE,
            ram_quota_mb=256,  # Minimal for development
            num_replicas=0,    # No replicas for development
            flush_enabled=False,
            storage_backend=StorageBackend.COUCHSTORE
        )

        bucket_mgr.create_bucket(settings)

        # Wait for bucket to be ready
        import time
        time.sleep(3)

        return "created", "Bucket created successfully"

    except BucketAlreadyExistsException:
        return "skipped", "Bucket already exists"
    except Exception as e:
        return "error", f"Failed to create bucket: {str(e)}"


def create_scope(cb: CouchbaseClient, force=False):
    """Create scope if it doesn't exist."""
    try:
        bucket = cb.cluster.bucket(BUCKET_NAME)
        coll_mgr = bucket.collections()

        # Check if scope exists
        try:
            scopes = coll_mgr.get_all_scopes()
            scope_exists = any(s.name == SCOPE_NAME for s in scopes)

            if scope_exists:
                if force:
                    coll_mgr.drop_scope(SCOPE_NAME)
                    import time
                    time.sleep(1)
                else:
                    return "skipped", "Scope already exists"
        except Exception:
            pass  # Scope doesn't exist, will create

        # Create scope
        coll_mgr.create_scope(SCOPE_NAME)

        return "created", "Scope created successfully"

    except ScopeAlreadyExistsException:
        return "skipped", "Scope already exists"
    except Exception as e:
        return "error", f"Failed to create scope: {str(e)}"


def create_collection(cb: CouchbaseClient, collection_name: str, force=False):
    """Create a collection if it doesn't exist."""
    try:
        bucket = cb.cluster.bucket(BUCKET_NAME)
        coll_mgr = bucket.collections()

        # Check if collection exists
        try:
            scopes = coll_mgr.get_all_scopes()
            for scope in scopes:
                if scope.name == SCOPE_NAME:
                    existing_collections = {c.name for c in scope.collections}
                    if collection_name in existing_collections:
                        if force:
                            coll_mgr.drop_collection(SCOPE_NAME, collection_name)
                            import time
                            time.sleep(1)
                        else:
                            return "skipped", f"Collection '{collection_name}' already exists"
        except Exception:
            pass  # Collection doesn't exist, will create

        # Create collection
        from couchbase.management.collections import CollectionSpec
        spec = CollectionSpec(collection_name, scope_name=SCOPE_NAME)
        coll_mgr.create_collection(spec)

        return "created", f"Collection '{collection_name}' created successfully"

    except CollectionAlreadyExistsException:
        return "skipped", f"Collection '{collection_name}' already exists"
    except Exception as e:
        return "error", f"Failed to create collection '{collection_name}': {str(e)}"


def main():
    parser = argparse.ArgumentParser(
        description="Setup Couchbase database structure for genetic prompt evolution framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/setup_couchbase.py                 # Create database structure
  python scripts/setup_couchbase.py --verify        # Verify existing structure
  python scripts/setup_couchbase.py --dry-run       # Show what would be created
  python scripts/setup_couchbase.py --force         # Recreate (WARNING: destroys data)
  python scripts/setup_couchbase.py --json          # Output JSON for parsing
        """
    )

    parser.add_argument("--verify", action="store_true",
                       help="Verify existing structure without creating")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be created without actually creating")
    parser.add_argument("--force", action="store_true",
                       help="Force recreate (WARNING: destroys existing data)")
    parser.add_argument("--json", action="store_true",
                       help="Output results as JSON")

    args = parser.parse_args()

    results = {
        "success": False,
        "env_check": {},
        "connection": {},
        "operations": [],
        "verification": {},
        "errors": []
    }

    # Check environment variables
    env_ok, env_msg = check_env_vars()
    results["env_check"] = {"success": env_ok, "message": env_msg}

    if not env_ok:
        results["errors"].append(env_msg)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Error: {env_msg}", file=sys.stderr)
            print("\nRun: source ./set_env.sh", file=sys.stderr)
        sys.exit(1)

    # Test connection
    conn_ok, conn_msg = test_connection()
    results["connection"] = {"success": conn_ok, "message": conn_msg}

    if not conn_ok:
        results["errors"].append(conn_msg)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Error: {conn_msg}", file=sys.stderr)
            print("\nCommon issues:", file=sys.stderr)
            print("  • Check COUCHBASE_CONNECTION_STRING in .env", file=sys.stderr)
            print("  • Verify your IP is whitelisted in Couchbase Capella", file=sys.stderr)
            print("  • Confirm COUCHBASE_USERNAME and COUCHBASE_PASSWORD are correct", file=sys.stderr)
        sys.exit(1)

    # Connect to Couchbase
    try:
        with CouchbaseClient() as cb:
            # Verify mode - just check what exists
            if args.verify:
                verification = verify_structure(cb)
                results["verification"] = verification
                results["success"] = True

                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print("Verification:")
                    print(f"  {'✓' if verification['bucket'] else '✗'} Bucket '{BUCKET_NAME}' accessible")
                    print(f"  {'✓' if verification['scope'] else '✗'} Scope '{SCOPE_NAME}' accessible")
                    for coll_name, exists in verification['collections'].items():
                        print(f"  {'✓' if exists else '✗'} Collection '{SCOPE_NAME}.{coll_name}' accessible")
                sys.exit(0)

            # Dry-run mode - show what would be done
            if args.dry-run:
                print("Dry-run mode - no changes will be made\n")
                verification = verify_structure(cb)

                if not verification['bucket']:
                    print(f"Would create: Bucket '{BUCKET_NAME}'")
                else:
                    print(f"Already exists: Bucket '{BUCKET_NAME}'")

                if not verification['scope']:
                    print(f"Would create: Scope '{SCOPE_NAME}'")
                else:
                    print(f"Already exists: Scope '{SCOPE_NAME}'")

                for coll_name in COLLECTIONS:
                    if not verification['collections'].get(coll_name):
                        print(f"Would create: Collection '{SCOPE_NAME}.{coll_name}'")
                    else:
                        print(f"Already exists: Collection '{SCOPE_NAME}.{coll_name}'")

                sys.exit(0)

            # Create bucket
            status, msg = create_bucket(cb, force=args.force)
            results["operations"].append({"resource": "bucket", "status": status, "message": msg})

            if status == "error":
                results["errors"].append(msg)
                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print(f"Error creating bucket: {msg}", file=sys.stderr)
                sys.exit(1)

            # Create scope
            status, msg = create_scope(cb, force=args.force)
            results["operations"].append({"resource": "scope", "status": status, "message": msg})

            if status == "error":
                results["errors"].append(msg)
                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print(f"Error creating scope: {msg}", file=sys.stderr)
                sys.exit(1)

            # Create collections
            for coll_name in COLLECTIONS:
                status, msg = create_collection(cb, coll_name, force=args.force)
                results["operations"].append({"resource": f"collection:{coll_name}", "status": status, "message": msg})

                if status == "error":
                    results["errors"].append(msg)

            # Verify final structure
            verification = verify_structure(cb)
            results["verification"] = verification
            results["success"] = len(results["errors"]) == 0

            # Output results
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                if results["success"]:
                    created_count = sum(1 for op in results["operations"] if op["status"] == "created")
                    skipped_count = sum(1 for op in results["operations"] if op["status"] == "skipped")

                    print("\n✓ Database setup successful\n")
                    if created_count > 0:
                        print(f"Created {created_count} resources")
                    if skipped_count > 0:
                        print(f"Skipped {skipped_count} existing resources")

                    # Show verification
                    if any(not v for v in [verification['bucket'], verification['scope']] + list(verification['collections'].values())):
                        print("\nVerification:")
                        print(f"  {'✓' if verification['bucket'] else '✗'} Bucket '{BUCKET_NAME}' accessible")
                        print(f"  {'✓' if verification['scope'] else '✗'} Scope '{SCOPE_NAME}' accessible")
                        for coll_name, exists in verification['collections'].items():
                            print(f"  {'✓' if exists else '✗'} Collection '{SCOPE_NAME}.{coll_name}' accessible")
                else:
                    print("\n✗ Database setup failed\n")
                    print("Errors:")
                    for error in results["errors"]:
                        print(f"✗ {error}")
                    sys.exit(1)

    except Exception as e:
        results["errors"].append(str(e))
        results["success"] = False

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\nError: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
