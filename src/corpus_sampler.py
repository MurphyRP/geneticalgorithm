"""
Evaluation corpus selection for fitness testing.

Selects N suitable paragraphs for generation-wide evaluation.
All prompts in a generation randomly select from this vetted pool.

Used by: evolution.py
Creates: Quality-controlled test sets for fair fitness comparison
Related: fitness_evaluator.py, couchbase_client.py

Key features:
- Lazy rating: Only rates chunks when first encountered
- Caching: Stores suitability ratings in database
- Word count filtering: Pre-filters to 550-650 words
- Retry logic: Continues sampling until N suitable chunks found
"""

from typing import List, Dict, Optional
from datetime import datetime
import random

from src.couchbase_client import CouchbaseClient
from src.llm_clients import generate_with_claude


def select_evaluation_corpus(
    couchbase_client: CouchbaseClient,
    corpus_size: int = 20,
    min_words: int = 550,
    max_words: int = 650,
    batch_size: int = 100
) -> List[Dict]:
    """
    Select N suitable paragraphs for generation evaluation pool.

    Each generation gets a fresh pool of vetted paragraphs.
    Individual prompts randomly select from this pool.

    Process:
    1. Query chunks with word count in range (pre-filter)
    2. Sample random batch
    3. For each chunk:
       - Check if rated (cached in document)
       - If not rated, call LLM to rate
       - If suitable, add to corpus
    4. Repeat until corpus_size reached

    Args:
        couchbase_client: Connected CouchbaseClient
        corpus_size: Number of paragraphs to select (default: 20)
        min_words: Minimum word count (default: 550)
        max_words: Maximum word count (default: 650)
        batch_size: Number of chunks to sample per batch (default: 100)

    Returns:
        List of paragraph dicts with 'chunk_id', 'text', 'word_count'

    Raises:
        Exception: If unable to find enough suitable chunks after reasonable attempts
    """
    print(f"\nSelecting evaluation corpus ({corpus_size} paragraphs, {min_words}-{max_words} words)...")

    suitable_chunks = []
    attempts = 0
    max_attempts = 10  # Prevent infinite loops

    while len(suitable_chunks) < corpus_size and attempts < max_attempts:
        attempts += 1
        print(f"  Attempt {attempts}: Sampling {batch_size} chunks...")

        # Query chunks in word count range
        query = f"""
            SELECT chunk_id, text, word_count, suitable_for_compression_testing
            FROM `{couchbase_client.bucket_name}`.`{couchbase_client.scope_name}`.`unstructured`
            WHERE word_count BETWEEN {min_words} AND {max_words}
            ORDER BY RANDOM()
            LIMIT {batch_size}
        """

        try:
            result = couchbase_client.cluster.query(query)
            chunks = list(result.rows())

            if not chunks:
                raise Exception(
                    f"No chunks found with word count between {min_words}-{max_words}. "
                    f"Check that unstructured collection has suitable data."
                )

            print(f"  Found {len(chunks)} chunks in word range, checking suitability...")

            # Check each chunk for suitability
            checked = 0
            newly_rated = 0

            for chunk in chunks:
                if len(suitable_chunks) >= corpus_size:
                    break

                checked += 1

                # Check if chunk is suitable (cached or newly rated)
                is_suitable = is_suitable_for_compression_testing(
                    chunk_id=chunk['chunk_id'],
                    text=chunk['text'],
                    cached_rating=chunk.get('suitable_for_compression_testing'),
                    couchbase_client=couchbase_client
                )

                # Track if we had to rate it
                if chunk.get('suitable_for_compression_testing') is None:
                    newly_rated += 1

                if is_suitable:
                    suitable_chunks.append({
                        'chunk_id': chunk['chunk_id'],
                        'text': chunk['text'],
                        'word_count': chunk['word_count']
                    })

            print(f"  Checked {checked} chunks ({newly_rated} newly rated), found {len(suitable_chunks)}/{corpus_size} suitable")

        except Exception as e:
            raise Exception(f"Failed to query or process chunks: {str(e)}")

    # Verify we found enough
    if len(suitable_chunks) < corpus_size:
        raise Exception(
            f"Unable to find {corpus_size} suitable chunks after {attempts} attempts. "
            f"Only found {len(suitable_chunks)}. Consider expanding word range or reviewing corpus quality."
        )

    # Return exactly corpus_size chunks (trim if we got more)
    final_corpus = suitable_chunks[:corpus_size]
    print(f"✓ Selected {len(final_corpus)} paragraphs for evaluation corpus")

    return final_corpus


def is_suitable_for_compression_testing(
    chunk_id: str,
    text: str,
    cached_rating: Optional[bool],
    couchbase_client: CouchbaseClient
) -> bool:
    """
    Check if a chunk is suitable for compression testing.

    Uses cached rating if available, otherwise calls LLM to rate
    and caches the result in the document.

    Args:
        chunk_id: Document ID in unstructured collection
        text: Chunk text content
        cached_rating: Cached suitability rating (if exists)
        couchbase_client: Connected CouchbaseClient

    Returns:
        True if suitable, False otherwise
    """
    # Use cached rating if available
    if cached_rating is not None:
        return cached_rating

    # No cache - need to rate with LLM
    is_suitable = rate_chunk_with_llm(text)

    # Cache the rating in the document
    try:
        collection = couchbase_client.get_collection("unstructured")

        # Use subdocument mutation to add fields without reading full document
        from couchbase.options import MutateInOptions
        from couchbase.subdocument import upsert

        collection.mutate_in(
            chunk_id,
            [
                upsert("suitable_for_compression_testing", is_suitable),
                upsert("rated_at", datetime.utcnow().isoformat() + "Z")
            ]
        )

    except Exception as e:
        # Log but don't fail - rating is still valid even if cache fails
        print(f"  Warning: Failed to cache rating for {chunk_id}: {e}")

    return is_suitable


def rate_chunk_with_llm(text: str) -> bool:
    """
    Ask LLM if chunk is suitable for compression testing.

    Uses Claude with temperature=0 for deterministic binary ratings.

    Exclusion criteria:
    - Lists, tables, or structured data
    - References, citations, bibliographies
    - Code snippets or technical specs
    - Already maximally compressed text
    - Fragmented or incomplete thoughts

    Args:
        text: Chunk text to rate

    Returns:
        True if suitable for compression testing, False otherwise
    """
    prompt = f"""Is this text suitable for testing compression prompts?

Answer NO if it is:
- Lists, tables, or structured data
- References, citations, or bibliographies
- Code snippets or technical specifications
- Already maximally compressed (dense jargon, telegraphic style, no redundancy)
- Fragmented or incomplete thoughts
- Primarily metadata or formatting

Answer YES if:
- None of the above exclusions apply
- Text has narrative or conversational structure
- Contains semantic content with concepts and relationships
- Has natural language flow

Text to evaluate:
{text}

Respond with ONLY: YES or NO"""

    try:
        response = generate_with_claude(
            prompt=prompt,
            temperature=0  # Deterministic for consistency
        )

        # Parse response
        answer = response.strip().upper()

        if "YES" in answer:
            return True
        elif "NO" in answer:
            return False
        else:
            # Unexpected response - fail loud
            raise Exception(f"Unexpected LLM response for chunk rating: '{response}'")

    except Exception as e:
        # Fail loud - don't silently skip chunks
        raise Exception(f"Failed to rate chunk with LLM: {str(e)}")
