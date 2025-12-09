#!/usr/bin/env python3
"""
Import pre-processed JSON documents and chunk them for corpus.

This script reads JSON files that have already been processed by unstructured.io
(format: array of {text, type, page_number, source_file} objects) and chunks
them into ~600 word pieces for the corpus.

Usage:
    python scripts/import_json_chunks.py --domain technical --file docs/processed.json
    python scripts/import_json_chunks.py --domain technical --dir input_docs/
"""

import argparse
import json
import sys
import uuid
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.couchbase_client import CouchbaseClient


def chunk_json_elements(elements: list, target_words: int = 600) -> list:
    """
    Chunk pre-processed JSON elements into ~600 word pieces.

    Args:
        elements: List of dicts with {text, type, page_number, source_file}
        target_words: Target chunk size (default: 600)

    Returns:
        List of chunk dictionaries ready for Couchbase
    """
    chunks = []
    current_chunk = {
        "chunk_id": str(uuid.uuid4()),
        "source_file": elements[0]["source_file"] if elements else "unknown",
        "source_type": "json",
        "elements": [],
        "text_parts": [],
        "word_count": 0,
        "element_types": {},
        "page_numbers": set(),
        "created_at": datetime.utcnow().isoformat() + "Z"
    }

    for element in elements:
        # Build element dict
        element_dict = {
            "type": element.get("type", "NarrativeText"),
            "text": element["text"]
        }

        # Add page number if available
        if "page_number" in element and element["page_number"] is not None:
            element_dict["page_number"] = element["page_number"]
            current_chunk["page_numbers"].add(element["page_number"])

        # Calculate word count
        element_words = len(element["text"].split())

        # Check if adding this element exceeds target
        if current_chunk["word_count"] + element_words > target_words and current_chunk["elements"]:
            # Finalize current chunk
            chunks.append(_finalize_chunk(current_chunk, elements[0]["source_file"]))

            # Start new chunk
            current_chunk = {
                "chunk_id": str(uuid.uuid4()),
                "source_file": elements[0]["source_file"],
                "source_type": "json",
                "elements": [],
                "text_parts": [],
                "word_count": 0,
                "element_types": {},
                "page_numbers": set(),
                "created_at": datetime.utcnow().isoformat() + "Z"
            }

        # Add element to current chunk
        current_chunk["elements"].append(element_dict)
        current_chunk["text_parts"].append(element["text"])
        current_chunk["word_count"] += element_words

        # Track element type distribution
        element_type = element.get("type", "NarrativeText")
        current_chunk["element_types"][element_type] = \
            current_chunk["element_types"].get(element_type, 0) + 1

    # Don't forget the last chunk
    if current_chunk["elements"]:
        chunks.append(_finalize_chunk(current_chunk, elements[0]["source_file"]))

    # Add chunk position metadata
    total_chunks = len(chunks)
    for idx, chunk in enumerate(chunks):
        chunk["chunk_index"] = idx
        chunk["total_chunks"] = total_chunks

    return chunks


def _finalize_chunk(chunk: dict, source_file: str) -> dict:
    """Finalize chunk by combining text and computing page ranges."""
    # Combine text parts
    chunk["text"] = "\n\n".join(chunk["text_parts"])
    del chunk["text_parts"]

    # Create page range if we have page numbers
    if chunk["page_numbers"]:
        page_list = sorted(list(chunk["page_numbers"]))
        chunk["page_range"] = {
            "start": page_list[0],
            "end": page_list[-1]
        }
    else:
        chunk["page_range"] = None

    del chunk["page_numbers"]

    # Ensure source_file is set
    if not chunk.get("source_file"):
        chunk["source_file"] = source_file

    return chunk


def import_json_file(file_path: Path, domain: str, db_client: CouchbaseClient) -> int:
    """
    Import a single JSON file and store chunks to Couchbase.

    Args:
        file_path: Path to JSON file
        domain: Domain classification
        db_client: CouchbaseClient instance

    Returns:
        Number of chunks stored
    """
    print(f"\nProcessing: {file_path.name}")

    # Read JSON
    try:
        with open(file_path, 'r') as f:
            elements = json.load(f)
    except Exception as e:
        print(f"✗ Failed to read JSON: {e}")
        return 0

    if not elements:
        print(f"✗ No elements found in JSON")
        return 0

    print(f"  → Found {len(elements)} elements")

    # Chunk elements
    chunks = chunk_json_elements(elements)
    print(f"  → Created {len(chunks)} chunks")

    # Store to database
    collection = db_client.get_collection('unstructured')
    stored_count = 0

    for chunk in chunks:
        try:
            chunk["domain"] = domain
            collection.upsert(chunk["chunk_id"], chunk)
            stored_count += 1
        except Exception as e:
            print(f"✗ Failed to store chunk: {e}")

    print(f"  → Stored {stored_count} chunks")
    return stored_count


def main():
    """Main entry point for JSON import script."""
    parser = argparse.ArgumentParser(
        description="Import pre-processed JSON documents to Couchbase corpus"
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
        help="Single JSON file path to process"
    )

    parser.add_argument(
        "--dir",
        type=str,
        help="Directory path to process (processes all JSON files)"
    )

    parser.add_argument(
        "--target-words",
        type=int,
        default=600,
        help="Target word count per chunk (default: 600)"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.file and not args.dir:
        parser.error("Must specify either --file or --dir")

    if args.file and args.dir:
        parser.error("Cannot specify both --file and --dir")

    # Collect files
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

        files = list(dir_path.glob("*.json"))

        if not files:
            print(f"✗ Error: No JSON files found in {dir_path}")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"JSON Import to Corpus")
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
                chunks_stored = import_json_file(file_path, args.domain, cb)
                total_chunks += chunks_stored
                successful_files += 1
            except Exception as e:
                print(f"✗ Error processing {file_path.name}: {e}")
                failed_files.append((file_path.name, str(e)))

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
        sys.exit(1)

    print(f"{'='*60}\n")
    print(f"✅ COMPLETE: All files processed successfully!")


if __name__ == "__main__":
    main()
