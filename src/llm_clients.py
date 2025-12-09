"""
LLM API client wrappers for multi-model prompt generation.

This module provides consistent interfaces to OpenAI, Claude, and Gemini APIs.
Used throughout the framework for:
- Prompt generation (random model selection)
- Compression execution (single model per era)
- Quality judging (all three models)

Critical: Multi-model diversity is a core research goal. The generate_with_random_model()
function ensures truly random selection (no distribution balancing) to demonstrate
that genetic algorithms can produce diverse, high-quality results across model types.

Used by: GA operators, evaluation pipeline, immigration
Creates: Prompt content, compression results, quality scores
"""

import os
import random
import itertools
import threading
from typing import Tuple, Dict

from openai import OpenAI
from anthropic import Anthropic
import google.generativeai as genai
# Gemini 3 uses new SDK (google-genai package)
from google import genai as genai3
from google.genai import types as genai3_types
from dotenv import load_dotenv


# Load environment variables
load_dotenv()


# Initialize clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# === GEMINI ROUND-ROBIN CONFIGURATION ===
# Load all four Gemini API keys from environment
GEMINI_API_KEYS = [
    os.getenv("GOOGLE_API_KEY"),
    os.getenv("GOOGLE_API_KEY_GENETIC_ONE"),
    os.getenv("GOOGLE_API_KEY_GENETIC_TWO"),
    os.getenv("GOOGLE_API_KEY_GENETIC_THREE")
]

# Validate that all keys are present
GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k is not None and k.strip()]

if len(GEMINI_API_KEYS) == 0:
    raise ValueError(
        "No Gemini API keys found in environment. "
        "Please set GOOGLE_API_KEY, GOOGLE_API_KEY_GENETIC_ONE, GOOGLE_API_KEY_GENETIC_TWO, "
        "and GOOGLE_API_KEY_GENETIC_THREE in .env file."
    )

print(f"✓ Loaded {len(GEMINI_API_KEYS)} Gemini API key(s) for round-robin rotation")

# Create round-robin iterator (cycles through keys infinitely)
_gemini_key_cycle = itertools.cycle(enumerate(GEMINI_API_KEYS))
_gemini_key_lock = threading.Lock()  # Thread-safe access to iterator

def _get_next_gemini_key() -> Tuple[int, str]:
    """
    Get next Gemini API key from round-robin pool.

    Returns:
        Tuple of (key_index, api_key)

    Thread-safe: Uses lock to protect iterator access.
    """
    with _gemini_key_lock:
        return next(_gemini_key_cycle)


def generate_with_openai(prompt: str, temperature: float = 1.0) -> str:
    """
    Generate text using OpenAI GPT-4o.

    Args:
        prompt: The input prompt
        temperature: Sampling temperature (0.0-2.0, default 1.0)

    Returns:
        Generated text response

    Raises:
        Exception: If API call fails (no fallback, fail loud)
    """
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        raise Exception(f"OpenAI API call failed: {str(e)}")


def generate_with_claude(prompt: str, temperature: float = 1.0) -> str:
    """
    Generate text using Claude Sonnet 4.5.

    Includes retry logic with exponential backoff for transient errors
    (529 Overloaded, 529 rate limits).

    Args:
        prompt: The input prompt
        temperature: Sampling temperature (0.0-1.0, default 1.0)

    Returns:
        Generated text response

    Raises:
        Exception: If API call fails after retries (no fallback, fail loud)
    """
    import time

    MAX_RETRIES = 5
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Check for retryable errors (overloaded, rate limit)
            if "overloaded" in error_str or "529" in error_str or "rate" in error_str:
                wait_time = 2 ** attempt  # 1, 2, 4, 8, 16 seconds
                print(f"[Claude] Overloaded/rate limit (attempt {attempt + 1}/{MAX_RETRIES}), waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                # Non-retryable error, fail immediately
                raise Exception(f"Claude API call failed: {str(e)}")

    # All retries exhausted
    raise Exception(f"Claude API call failed after {MAX_RETRIES} retries: {str(last_error)}")


def generate_with_gemini(prompt: str, temperature: float = 1.0) -> str:
    """
    Generate text using Google Gemini 2.0 Flash with round-robin key rotation.

    Uses round-robin strategy across 3 Gemini API keys to work around
    per-project rate limits. Rotates on every call for maximum distribution.

    If a key fails with rate limit error, tries the next key up to 3 times
    (one attempt per key). If all keys fail, raises exception (fail loud).

    Args:
        prompt: The input prompt
        temperature: Sampling temperature (0.0-2.0, default 1.0)

    Returns:
        Generated text response

    Raises:
        Exception: If API call fails on all keys (no fallback, fail loud)
    """
    MAX_RETRIES = len(GEMINI_API_KEYS)  # Try each key once
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            # Get next key from round-robin pool
            key_index, api_key = _get_next_gemini_key()

            # Configure Gemini with this key (genai uses global config)
            genai.configure(api_key=api_key)

            # Log which key we're using (observable behavior)
            print(f"[Gemini] Using API key #{key_index + 1}")

            # Make API call
            model = genai.GenerativeModel("gemini-2.0-flash-exp")
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature
                )
            )

            # Success! Return result
            return response.text

        except Exception as e:
            last_error = e
            error_msg = str(e).lower()

            # Check if this is a rate limit error
            is_rate_limit = any(phrase in error_msg for phrase in [
                "quota", "rate limit", "resource exhausted", "429"
            ])

            if is_rate_limit:
                print(f"[Gemini] Key #{key_index + 1} hit rate limit, trying next key...")
                # Continue to next key
                continue
            else:
                # Non-rate-limit error - fail immediately (don't retry)
                raise Exception(f"Gemini API call failed (key #{key_index + 1}): {str(e)}")

    # All keys exhausted - FAIL LOUD
    raise Exception(
        f"Gemini API call failed on ALL {MAX_RETRIES} keys. "
        f"All keys may have hit rate limits. Last error: {last_error}"
    )


def generate_with_gemini3(prompt: str, temperature: float = 1.0) -> str:
    """
    Generate text using Google Gemini 3 Pro with thinking mode.

    Uses the new google-genai SDK with thinking_level="low" for
    fast, focused compression output. Round-robin key rotation
    applies same as standard Gemini.

    Args:
        prompt: The input prompt
        temperature: Not used with thinking mode (included for API consistency)

    Returns:
        Generated text response

    Raises:
        Exception: If API call fails on all keys (no fallback, fail loud)
    """
    MAX_RETRIES = len(GEMINI_API_KEYS)
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            key_index, api_key = _get_next_gemini_key()
            print(f"[Gemini3] Using API key #{key_index + 1}")

            # New SDK uses Client pattern
            client = genai3.Client(api_key=api_key)

            response = client.models.generate_content(
                model="gemini-3-pro-preview",
                contents=prompt,
                config=genai3_types.GenerateContentConfig(
                    thinking_config=genai3_types.ThinkingConfig(thinking_level="low")
                )
            )

            return response.text

        except Exception as e:
            last_error = e
            error_msg = str(e).lower()

            is_rate_limit = any(phrase in error_msg for phrase in [
                "quota", "rate limit", "resource exhausted", "429"
            ])

            if is_rate_limit:
                print(f"[Gemini3] Key #{key_index + 1} hit rate limit, trying next key...")
                continue
            else:
                raise Exception(f"Gemini 3 API call failed (key #{key_index + 1}): {str(e)}")

    raise Exception(
        f"Gemini 3 API call failed on ALL {MAX_RETRIES} keys. "
        f"Last error: {last_error}"
    )


def generate_with_random_model(prompt: str, temperature: float = 1.0) -> Tuple[str, str]:
    """
    Generate text using a randomly selected model.

    This function demonstrates multi-model diversity in prompt generation,
    a core goal of this research. Selection is truly random (no balancing)
    to show that genetic algorithms can work across diverse model types.

    Args:
        prompt: The input prompt
        temperature: Sampling temperature (default 1.0)

    Returns:
        Tuple of (generated_text, model_name)
        where model_name is "openai" | "claude" | "gemini"

    Raises:
        Exception: If selected model API call fails (no fallback)
    """
    model_name = random.choice(["openai", "claude", "gemini"])

    if model_name == "openai":
        text = generate_with_openai(prompt, temperature)
    elif model_name == "claude":
        text = generate_with_claude(prompt, temperature)
    else:  # gemini
        text = generate_with_gemini(prompt, temperature)

    return text, model_name


def test_all_models() -> Dict[str, bool]:
    """
    Test all three LLM APIs with a simple prompt.

    Used during setup to verify API keys and connectivity.
    Returns dictionary of {model_name: success_boolean}.
    """
    results = {}
    test_prompt = "Say 'Hello' in exactly one word."

    # Test OpenAI
    try:
        response = generate_with_openai(test_prompt, temperature=0.0)
        results["openai"] = len(response) > 0
    except Exception as e:
        print(f"OpenAI test failed: {e}")
        results["openai"] = False

    # Test Claude
    try:
        response = generate_with_claude(test_prompt, temperature=0.0)
        results["claude"] = len(response) > 0
    except Exception as e:
        print(f"Claude test failed: {e}")
        results["claude"] = False

    # Test Gemini (with round-robin keys)
    try:
        response = generate_with_gemini(test_prompt, temperature=0.0)
        results["gemini"] = len(response) > 0
        print(f"✓ Gemini test passed using {len(GEMINI_API_KEYS)} key(s)")
    except Exception as e:
        print(f"Gemini test failed: {e}")
        results["gemini"] = False

    # Test Gemini 3 (with thinking mode)
    try:
        response = generate_with_gemini3(test_prompt)
        results["gemini3"] = len(response) > 0
        print(f"✓ Gemini 3 test passed using {len(GEMINI_API_KEYS)} key(s)")
    except Exception as e:
        print(f"Gemini 3 test failed: {e}")
        results["gemini3"] = False

    return results
