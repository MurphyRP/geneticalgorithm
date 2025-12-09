#!/usr/bin/env python3
"""
Populate unstructured collection from source documents.

This script extracts ~600-word chunks from documents and stores them in the
Couchbase genetic.g_scope.unstructured collection for use in compression experiments.

Usage:
    # Process single file
    python scripts/populate_corpus.py --domain academic --file papers/research.pdf

    # Process directory
    python scripts/populate_corpus.py --domain legal --dir contracts/

    # Custom chunk size
    python scripts/populate_corpus.py --domain technical --dir docs/ --target-words 500

Domain options:
    - academic: Research papers, textbooks
    - medical: Medical research, clinical studies
    - conversational: Podcasts, interviews, dialogues
    - technical: Documentation, how-tos, specifications
    - narrative: News articles, blog posts, stories
    - legal: Contracts, policies, regulations
    - mixed: Miscellaneous/uncategorized content
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.corpus_extractor import extract_and_store
from src.couchbase_client import CouchbaseClient


def main():
    """Main entry point for corpus population script."""
    parser = argparse.ArgumentParser(
        description="Extract and store corpus chunks to Couchbase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--domain",
        required=True,
        choices=["academic", "medical", "conversational", "technical", "narrative", "legal", "mixed"],
        help="Domain classification for the content"
    )

    parser.add_argument(
        "--file",
        type=str,
        help="Single file path to process"
    )

    parser.add_argument(
        "--dir",
        type=str,
        help="Directory path to process (processes all PDF/HTML/MD files)"
    )

    parser.add_argument(
        "--target-words",
        type=int,
        default=600,
        help="Target word count per chunk (default: 600)"
    )

    args = parser.parse_args()

    # Validate that either --file or --dir is provided
    if not args.file and not args.dir:
        parser.error("Must specify either --file or --dir")

    if args.file and args.dir:
        parser.error("Cannot specify both --file and --dir")

    # Collect files to process
    files = []

    if args.file:
        file_path = Path(args.file)
        if not file_path.is_file():
            print(f"✗ Error: File not found: {file_path}")
            sys.exit(1)
        files = [file_path]

    elif args.dir:
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            print(f"✗ Error: Directory not found: {dir_path}")
            sys.exit(1)

        # Collect all supported file types
        files = (
            list(dir_path.glob("*.pdf")) +
            list(dir_path.glob("*.html")) +
            list(dir_path.glob("*.htm")) +
            list(dir_path.glob("*.md"))
        )

        if not files:
            print(f"✗ Error: No PDF, HTML, or MD files found in {dir_path}")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Corpus Population")
    print(f"{'='*60}")
    print(f"Domain: {args.domain}")
    print(f"Files to process: {len(files)}")
    print(f"Target chunk size: ~{args.target_words} words")
    print(f"{'='*60}\n")

    # Process files
    total_chunks = 0
    successful_files = 0
    failed_files = []

    with CouchbaseClient() as cb:
        for file_path in files:
            try:
                chunks_stored = extract_and_store(
                    str(file_path),
                    args.domain,
                    args.target_words,
                    cb
                )
                total_chunks += chunks_stored
                successful_files += 1

            except Exception as e:
                print(f"✗ Error processing {file_path.name}: {e}")
                failed_files.append((file_path.name, str(e)))
                # Continue with other files

    # Print summary
    print(f"\n{'='*60}")
    print(f"Summary")
    print(f"{'='*60}")
    print(f"✓ Successfully processed: {successful_files}/{len(files)} files")
    print(f"✓ Total chunks stored: {total_chunks}")

    if failed_files:
        print(f"\n✗ Failed files: {len(failed_files)}")
        for filename, error in failed_files:
            print(f"  - {filename}: {error}")
        print(f"{'='*60}\n")
        sys.exit(1)  # Exit with error if any files failed

    print(f"{'='*60}\n")
    print(f"✅ COMPLETE: All files processed successfully!")


if __name__ == "__main__":
    main()
