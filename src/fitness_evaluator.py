"""
Fitness evaluation pipeline for genetic algorithm prompt optimization.

This module evaluates how well a prompt compresses text by:
1. Executing compression using the prompt
2. Judging quality with three LLM judges
3. Calculating fitness score based on compression ratio × quality × survival

The fitness function is the selection mechanism for the genetic algorithm.
Prompts with higher fitness scores are more likely to:
- Be selected as elite (top 20%)
- Become parents for crossover
- Have their mutations survive

Multi-Model Judging Strategy:
- All three models (OpenAI, Claude, Gemini) judge each compression
- Reduces model-specific bias
- Provides more robust quality signal
- Each judge uses temperature=0 for deterministic scoring

Fitness Formula:
    fitness = quality_score_avg × compression_ratio × survival_factor

    where:
        compression_ratio = original_words / compressed_words
        quality_score_avg = average of 3 judge scores (0-10)
        survival_factor = 0 if expanded, 1 if compressed

Scoring Rubric (0-10 scale):
    Faithfulness (0-5): Core concepts, entities, relationships preserved
    Clarity (0-3): Clear and understandable
    Readability (0-2): Natural, grammatical flow

Used by: GA evolution loop, generation evaluation
Creates: Fitness scores, quality assessments, compression metrics
Critical for: Selection pressure, evolution gradient

Related files:
- src/models.py: Prompt and PromptTag structures
- src/llm_clients.py: LLM API wrappers
- project_docs/fitness_function.md: Reference implementation pattern
- project_docs/phase_2.md: Full specification
"""

import json
import time
from typing import Dict, List, Optional
import tiktoken
from src.models import Prompt
from src.llm_clients import (
    generate_with_openai,
    generate_with_claude,
    generate_with_gemini,
    generate_with_gemini3
)

# Initialize tokenizer once at module level for efficiency
# Using cl100k_base (GPT-4 tokenizer) as standardized token counting
_tokenizer = tiktoken.get_encoding("cl100k_base")


def count_words(text: str) -> int:
    """
    Count words in text using simple whitespace splitting.

    Args:
        text: Input text

    Returns:
        Word count

    Note: Uses simple splitting for speed. Compression ratio accuracy
    difference vs tokenization is <5%, which is acceptable for GA selection.
    """
    return len(text.split())


def count_tokens(text: str) -> int:
    """
    Count tokens using tiktoken cl100k_base encoding.

    Uses GPT-4 tokenizer as standardized token counting method.
    This is not model-specific - provides consistent measurement
    across the framework regardless of which LLM is used.

    Args:
        text: Input text

    Returns:
        Token count

    Note: Tokens are more meaningful than words for LLM contexts
    (token limits, actual API costs). For English text, expect
    token_count >= word_count (words have ~1.3 tokens on average).
    """
    return len(_tokenizer.encode(text))


def compress_text(
    prompt_object: Prompt,
    paragraph_text: str,
    compression_model: str = "claude"
) -> str:
    """
    Apply a prompt to compress a paragraph.

    Builds the full compression prompt from the 5 tags and executes
    compression using the specified model.

    Args:
        prompt_object: Prompt with 5 tags (role, compression_target,
                      fidelity, constraints, output)
        paragraph_text: Original text to compress
        compression_model: Which model to use ("openai", "claude", "gemini")

    Returns:
        Compressed text string (empty string if compression fails)

    Error Handling:
        NOTE: This function returns empty string on API failure (not ideal per the
        fail-loud principle in CLAUDE.md). This is acceptable because:
        - Empty string triggers survival_factor=0 and fitness=0
        - This effectively penalizes the prompt (fitness becomes 0)
        - The orchestrator logs the error separately

        Ideally, should raise exception and let caller decide retry strategy.
        This is a known limitation; see project_docs/ for discussion.
    """
    try:
        # Build full compression prompt from 5 tags
        full_prompt = f"""{prompt_object.role.text}

{prompt_object.compression_target.text}

{prompt_object.fidelity.text}

{prompt_object.constraints.text}

{prompt_object.output.text}

Original Text:
{paragraph_text}"""

        # Call appropriate model
        if compression_model == "openai":
            compressed = generate_with_openai(full_prompt)
        elif compression_model == "claude":
            compressed = generate_with_claude(full_prompt)
        elif compression_model == "gemini":
            compressed = generate_with_gemini(full_prompt)
        elif compression_model == "gemini3":
            compressed = generate_with_gemini3(full_prompt)
        else:
            print(f"Error: Unknown compression model '{compression_model}'")
            return ""

        # Return compressed text (strip whitespace)
        return compressed.strip()

    except Exception as e:
        print(f"Compression failed with {compression_model}: {e}")
        return ""


def judge_compression(
    original_text: str,
    compressed_text: str,
    judge_model: str = "claude"
) -> Dict:
    """
    Have an LLM judge score the compression quality.

    Uses a 3-dimension rubric:
    - Faithfulness (0-5): Are core concepts preserved?
    - Clarity (0-3): Is it clear and understandable?
    - Readability (0-2): Is it grammatical and natural?

    Total score: 0-10 (sum of dimensions)

    Args:
        original_text: Original paragraph
        compressed_text: Compressed version
        judge_model: Which model to use as judge ("openai", "claude", "gemini")

    Returns:
        {
            "score": int (0-10),
            "faithfulness": int (0-5),
            "clarity": int (0-3),
            "readability": int (0-2),
            "comments": str,
            "judge_model": str,
            "judge_duration_ms": int
        }

        On error returns: {"score": None, "error": str, ...}

    Implementation notes:
    - Uses temperature=0 for deterministic scoring
    - Handles Claude markdown code blocks (```json ... ```)
    - Tracks duration for performance monitoring
    """
    start_time = time.time()

    # Create judge prompt with rubric and calibration examples
    judge_prompt = f"""You are evaluating a text compression. Score the compressed text on three dimensions:

ORIGINAL TEXT:
{original_text}

COMPRESSED TEXT:
{compressed_text}

SCORING RUBRIC:

Faithfulness (0-5 points):
- Are all core concepts preserved?
- Are entity names and relationships maintained?
- Is the logical structure intact?

CALIBRATION EXAMPLES:
5 points: All entities, relationships, and core concepts perfectly preserved
4 points: Minor details lost but all main ideas intact
3 points: Main ideas preserved but missing some key details
2 points: Significant information loss or some distortion
1 point: Major concepts missing or distorted
0 points: Completely unfaithful to original

Clarity (0-3 points):
- Is the compressed text clear and understandable?
- Are there any ambiguities?

CALIBRATION EXAMPLES:
3 points: Perfectly clear and understandable on its own
2 points: Clear with minor ambiguity that doesn't impede understanding
1 point: Somewhat unclear or requires original for interpretation
0 points: Confusing or unclear

Readability (0-2 points):
- Is it grammatically correct?
- Does it flow naturally?

CALIBRATION EXAMPLES:
2 points: Natural, grammatical, flows well
1 points: Readable but awkward or has minor grammar issues
0 points: Choppy, ungrammatical, or hard to read

IMPORTANT: Respond with ONLY a JSON object in this exact format:
{{
  "faithfulness": <0-5>,
  "clarity": <0-3>,
  "readability": <0-2>,
  "score": <sum of above, 0-10>,
  "comments": "<brief 1-2 sentence explanation>"
}}"""

    try:
        # Call appropriate judge model with temperature=0
        if judge_model == "openai":
            response = generate_with_openai(
                judge_prompt,
                temperature=0
            )
        elif judge_model == "claude":
            response = generate_with_claude(
                judge_prompt,
                temperature=0
            )
        elif judge_model == "gemini":
            response = generate_with_gemini(
                judge_prompt,
                temperature=0
            )
        else:
            return {
                "score": None,
                "error": f"Unknown judge model: {judge_model}",
                "judge_model": judge_model
            }

        # Parse JSON response (handle markdown code blocks from Claude)
        response_text = response.strip()

        # Remove markdown code blocks if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]

        if response_text.endswith('```'):
            response_text = response_text[:-3]

        # Parse JSON
        result = json.loads(response_text.strip())

        # Add metadata
        result["judge_model"] = judge_model
        result["judge_duration_ms"] = int((time.time() - start_time) * 1000)

        return result

    except Exception as e:
        return {
            "score": None,
            "error": str(e),
            "judge_model": judge_model,
            "judge_duration_ms": int((time.time() - start_time) * 1000)
        }


def calculate_fitness(
    original_text: str,
    compressed_text: str,
    quality_scores: List[float],
    use_token_metric: bool = False
) -> Dict:
    """
    Calculate fitness score using Framework v2 weighted formula.

    Formula (Framework v2):
        quality_norm = quality_score_avg / 10.0
        compression_norm = min(compression_ratio / 20.0, 1.0)
        raw_fitness = (0.75 * quality_norm) + (0.25 * compression_norm)
        fitness = raw_fitness * survival_factor

    Where:
        compression_ratio = original_words / compressed_words (or tokens if use_token_metric)
        quality_score_avg = mean of judge scores (0-10)
        quality_norm = normalized quality (0.0-1.0)
        compression_norm = normalized compression (0.0-1.0, capped at 20x)
        survival_factor = 0 if expanded, 1 if compressed (binary gate, word-based)

    Rationale:
        - Weighted formula balances quality (75%) vs compression (25%)
        - Normalization ensures fitness in 0.0-1.0 range
        - Compression capped at 20x prevents runaway scores
        - Survival factor remains binary gate (expansion = death)
        - Both word and token metrics always computed and stored

    Args:
        original_text: Original paragraph
        compressed_text: Compressed version
        quality_scores: List of 0-10 scores from judges
        use_token_metric: If True, use token ratio for fitness; else use word ratio (default)

    Returns:
        {
            "original_words": int,
            "compressed_words": int,
            "compression_ratio": float,  # The ratio used for fitness (word or token)
            "original_tokens": int,
            "compressed_tokens": int,
            "token_compression_ratio": float,
            "quality_score_avg": float,
            "survival_factor": int,  # 0 or 1
            "fitness": float  # 0.0-1.0 range
        }

    Edge cases:
    - Empty compressed_text: survival_factor=0, fitness=0
    - Empty quality_scores: quality_avg=0, fitness=0
    - Expanded text: survival_factor=0, fitness=0
    """
    # Count both words and tokens (always compute both)
    original_words = count_words(original_text)
    compressed_words = count_words(compressed_text)
    original_tokens = count_tokens(original_text)
    compressed_tokens = count_tokens(compressed_text)

    # Calculate both compression ratios
    if compressed_words > 0:
        word_compression_ratio = original_words / compressed_words
    else:
        word_compression_ratio = 0.0

    if compressed_tokens > 0:
        token_compression_ratio = original_tokens / compressed_tokens
    else:
        token_compression_ratio = 0.0

    # Choose which ratio to use for fitness calculation
    if use_token_metric:
        compression_ratio = token_compression_ratio
    else:
        compression_ratio = word_compression_ratio

    # Calculate average quality score
    if len(quality_scores) > 0:
        quality_score_avg = sum(quality_scores) / len(quality_scores)
    else:
        quality_score_avg = 0.0

    # Determine survival factor (always word-based for simplicity)
    # 0 if text expanded or failed to compress, 1 if successfully compressed
    if compressed_words == 0 or compressed_words >= original_words:
        survival_factor = 0
    else:
        survival_factor = 1

    # Calculate normalized fitness (Framework v2)
    quality_norm = quality_score_avg / 10.0
    compression_norm = min(compression_ratio / 20.0, 1.0)
    raw_fitness = (0.75 * quality_norm) + (0.25 * compression_norm)
    fitness = raw_fitness * survival_factor

    return {
        "original_words": original_words,
        "compressed_words": compressed_words,
        "compression_ratio": compression_ratio,  # The one used for fitness
        "original_tokens": original_tokens,
        "compressed_tokens": compressed_tokens,
        "token_compression_ratio": token_compression_ratio,
        "quality_score_avg": quality_score_avg,
        "survival_factor": survival_factor,
        "fitness": fitness
    }


def evaluate_prompt_fitness(
    prompt_object: Prompt,
    paragraph_text: str,
    compression_model: str = "claude",
    judge_models: Optional[List[str]] = None,
    use_token_metric: bool = False
) -> Dict:
    """
    Complete fitness evaluation pipeline.

    Orchestrates:
    1. Text compression
    2. Multi-model quality judging
    3. Fitness calculation
    4. Result packaging

    Args:
        prompt_object: Prompt to evaluate
        paragraph_text: Text to compress
        compression_model: Model for compression execution
        judge_models: List of models to use as judges (default: all 3)

    Returns:
        Complete evaluation results ready for Prompt object update:
        {
            "original_text": str,
            "compressed_text": str,
            "original_words": int,
            "compressed_words": int,
            "compression_ratio": float,
            "original_tokens": int,
            "compressed_tokens": int,
            "token_compression_ratio": float,
            "quality_scores": {"openai": 8.5, "claude": 7.2, "gemini": 8.8},
            "quality_score_avg": float,
            "survival_factor": int,
            "fitness": float,
            "judge_details": {
                "openai": {...},  # Full judge response
                "claude": {...},
                "gemini": {...}
            }
        }

    Error handling:
    - Compression fails → fitness=0, log error
    - Judge fails → exclude from average, use remaining judges
    - All judges fail → fitness=0, log error
    - Pipeline completes in all cases
    """
    # Default to all three judges
    if judge_models is None:
        judge_models = ["openai", "claude", "gemini"]

    # Step 1: Compress text
    print(f"Compressing with {compression_model}...")
    compressed_text = compress_text(prompt_object, paragraph_text, compression_model)

    if not compressed_text:
        print("Warning: Compression returned empty string")

    # Step 2: Judge compression with all models
    print(f"Judging with {len(judge_models)} models...")
    judge_details = {}
    quality_scores_dict = {}
    valid_scores = []

    for judge_model in judge_models:
        print(f"  - Judging with {judge_model}...")
        result = judge_compression(paragraph_text, compressed_text, judge_model)
        judge_details[judge_model] = result

        # Track valid scores for averaging
        if result.get("score") is not None:
            quality_scores_dict[judge_model] = result["score"]
            valid_scores.append(result["score"])
        else:
            print(f"    Warning: {judge_model} judge failed - {result.get('error', 'unknown error')}")
            quality_scores_dict[judge_model] = None

        # Small delay for rate limiting
        time.sleep(0.2)

    # Check if we have any valid scores
    if len(valid_scores) == 0:
        print("Error: All judges failed - fitness will be 0")

    # Step 3: Calculate fitness
    fitness_metrics = calculate_fitness(paragraph_text, compressed_text, valid_scores, use_token_metric)

    # Step 4: Package complete results
    results = {
        "original_text": paragraph_text,
        "compressed_text": compressed_text,
        "original_words": fitness_metrics["original_words"],
        "compressed_words": fitness_metrics["compressed_words"],
        "compression_ratio": fitness_metrics["compression_ratio"],
        "original_tokens": fitness_metrics["original_tokens"],
        "compressed_tokens": fitness_metrics["compressed_tokens"],
        "token_compression_ratio": fitness_metrics["token_compression_ratio"],
        "quality_scores": quality_scores_dict,
        "quality_score_avg": fitness_metrics["quality_score_avg"],
        "survival_factor": fitness_metrics["survival_factor"],
        "fitness": fitness_metrics["fitness"],
        "judge_details": judge_details
    }

    print(f"Evaluation complete - Fitness: {results['fitness']:.4f}")

    return results
