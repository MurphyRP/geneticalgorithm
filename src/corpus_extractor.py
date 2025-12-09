"""
Text extraction and chunking for corpus preparation.

This module extracts ~600-word chunks from documents (PDF, HTML, Markdown) using
the unstructured.io library. Chunks are stored in the Couchbase `unstructured`
collection with full metadata preservation.

Key features:
- Auto-detection of file types (PDF, HTML, MD)
- Preservation of unstructured.io element metadata (types, page numbers, etc.)
- ~600 word chunking while respecting element boundaries
- Fail-fast error handling (no silent fallbacks)

Used by: Corpus preparation scripts
Creates: Diverse text corpus for compression experiments (Paper 1)
"""

import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from unstructured.partition.auto import partition
from src.couchbase_client import CouchbaseClient


def extract_chunks(file_path: str, target_words: int = 600) -> List[Dict]:
    """
    Extract text from document and chunk it into ~target_words segments,
    preserving unstructured.io's native element metadata.

    Uses unstructured.io's partition() function for automatic file type detection
    and content extraction. Chunks elements into ~600 word pieces while maintaining
    element boundaries and metadata.

    Args:
        file_path: Path to the document file (PDF, HTML, MD, etc.)
        target_words: Target word count per chunk (default: 600)

    Returns:
        List of chunk dictionaries with text and preserved metadata

    Raises:
        FileNotFoundError: If file doesn't exist
        Exception: If extraction fails (fail loud per CLAUDE.md)

    Example:
        chunks = extract_chunks("papers/research.pdf")
        # Returns list of ~600-word chunks with metadata
    """
    # Verify file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Extract elements using unstructured.io
    try:
        elements = partition(filename=file_path)
    except Exception as e:
        raise Exception(f"Failed to extract content from {file_path}: {str(e)}")

    if not elements:
        raise Exception(f"No content extracted from {file_path}")

    chunks = []
    current_chunk = {
        "chunk_id": str(uuid.uuid4()),
        "source_file": os.path.basename(file_path),
        "source_type": os.path.splitext(file_path)[1][1:].lower(),  # Extension without dot
        "elements": [],
        "text_parts": [],
        "word_count": 0,
        "element_types": {},
        "page_numbers": set(),
        "created_at": datetime.utcnow().isoformat() + "Z"
    }

    for element in elements:
        # Extract element metadata
        element_dict = {
            "type": element.category,  # NarrativeText, Title, ListItem, etc.
            "text": str(element),
        }

        # Add page number if available (PDFs)
        if hasattr(element, 'metadata') and hasattr(element.metadata, 'page_number') and element.metadata.page_number is not None:
            element_dict["page_number"] = element.metadata.page_number
            current_chunk["page_numbers"].add(element.metadata.page_number)

        # Add coordinates if available
        if hasattr(element, 'metadata') and hasattr(element.metadata, 'coordinates') and element.metadata.coordinates is not None:
            try:
                element_dict["coordinates"] = element.metadata.coordinates.to_dict()
            except:
                pass  # Coordinates might not always be serializable

        # Store any other metadata
        if hasattr(element, 'metadata'):
            try:
                metadata_dict = element.metadata.to_dict()
                # Filter out already-captured fields and None values
                element_dict["metadata"] = {
                    k: v for k, v in metadata_dict.items()
                    if k not in ['coordinates', 'page_number'] and v is not None
                }
            except:
                pass  # If metadata can't be serialized, skip it

        # Calculate word count for this element
        element_words = len(str(element).split())

        # Check if adding this element exceeds target
        if current_chunk["word_count"] + element_words > target_words and current_chunk["elements"]:
            # Finalize current chunk
            chunks.append(_finalize_chunk(current_chunk))

            # Start new chunk
            current_chunk = {
                "chunk_id": str(uuid.uuid4()),
                "source_file": os.path.basename(file_path),
                "source_type": os.path.splitext(file_path)[1][1:].lower(),
                "elements": [],
                "text_parts": [],
                "word_count": 0,
                "element_types": {},
                "page_numbers": set(),
                "created_at": datetime.utcnow().isoformat() + "Z"
            }

        # Add element to current chunk
        current_chunk["elements"].append(element_dict)
        current_chunk["text_parts"].append(str(element))
        current_chunk["word_count"] += element_words

        # Track element type distribution
        element_type = element.category
        current_chunk["element_types"][element_type] = \
            current_chunk["element_types"].get(element_type, 0) + 1

    # Don't forget the last chunk
    if current_chunk["elements"]:
        chunks.append(_finalize_chunk(current_chunk))

    # Add chunk position metadata
    total_chunks = len(chunks)
    for idx, chunk in enumerate(chunks):
        chunk["chunk_index"] = idx
        chunk["total_chunks"] = total_chunks

    return chunks


def _finalize_chunk(chunk: Dict) -> Dict:
    """
    Helper to finalize a chunk by combining text and computing page ranges.

    Args:
        chunk: Partially constructed chunk dictionary

    Returns:
        Finalized chunk with text combined and page_range computed
    """
    # Combine text parts with double newline separation
    chunk["text"] = "\n\n".join(chunk["text_parts"])
    del chunk["text_parts"]  # Remove temporary field

    # Create page range if we have page numbers
    if chunk["page_numbers"]:
        page_list = sorted(list(chunk["page_numbers"]))
        chunk["page_range"] = {
            "start": page_list[0],
            "end": page_list[-1]
        }
    else:
        chunk["page_range"] = None

    # Convert set to list for JSON serialization (or remove it)
    del chunk["page_numbers"]  # Remove temporary set

    return chunk


def store_chunks_to_db(
    chunks: List[Dict],
    domain: Optional[str] = None,
    db_client: Optional[CouchbaseClient] = None
) -> tuple[int, int]:
    """
    Store extracted chunks to Couchbase genetic.g_scope.unstructured collection.

    Args:
        chunks: List of chunk dictionaries from extract_chunks()
        domain: Optional domain classification to add to each chunk
                (academic, conversational, technical, narrative, legal, mixed)
        db_client: CouchbaseClient instance (will create if not provided)

    Returns:
        Tuple of (stored_count, failed_count)

    Raises:
        Exception: If storage fails (fail loud per CLAUDE.md)

    Example:
        with CouchbaseClient() as cb:
            stored, failed = store_chunks_to_db(chunks, domain="academic", db_client=cb)
    """
    # Create client if not provided
    close_on_exit = False
    if db_client is None:
        db_client = CouchbaseClient()
        db_client.connect()
        close_on_exit = True

    try:
        # Get the unstructured collection
        collection = db_client.get_collection('unstructured')

        stored_count = 0
        failed_count = 0

        for chunk in chunks:
            try:
                # Add domain classification if provided
                if domain:
                    chunk["domain"] = domain
                elif "domain" not in chunk:
                    # Default to "mixed" if not specified
                    chunk["domain"] = "mixed"

                # Store to Couchbase using chunk_id as document key
                collection.upsert(chunk["chunk_id"], chunk)
                stored_count += 1

            except Exception as e:
                print(f"✗ Failed to store chunk {chunk['chunk_id']}: {e}")
                failed_count += 1
                # Continue trying other chunks

        print(f"\n✓ Stored {stored_count} chunks to genetic.g_scope.unstructured")
        if failed_count > 0:
            print(f"✗ Failed to store {failed_count} chunks")

        return stored_count, failed_count

    finally:
        if close_on_exit:
            db_client.close()


def extract_and_store(
    file_path: str,
    domain: str,
    target_words: int = 600,
    db_client: Optional[CouchbaseClient] = None
) -> int:
    """
    Convenience function to extract chunks from a file and store them immediately.

    Args:
        file_path: Path to document
        domain: Domain classification (academic, conversational, technical, narrative, legal)
        target_words: Target chunk size (default: 600)
        db_client: Optional CouchbaseClient instance

    Returns:
        Number of chunks stored

    Raises:
        Exception: If extraction or storage fails
    """
    print(f"\nProcessing: {os.path.basename(file_path)}")

    # Extract chunks
    chunks = extract_chunks(file_path, target_words)
    print(f"  → Extracted {len(chunks)} chunks")

    # Store to database
    stored, failed = store_chunks_to_db(chunks, domain, db_client)

    if failed > 0:
        raise Exception(f"Failed to store {failed} chunks from {file_path}")

    return stored
