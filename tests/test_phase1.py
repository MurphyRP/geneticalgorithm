"""
Phase 1 Integration Tests - Smoke tests for all foundation components.

This script verifies that all Phase 1 components work correctly:
1. Environment variables load
2. Data models serialize/deserialize
3. All three LLM APIs are callable
4. Couchbase connection works
5. Document CRUD operations work

Run this script after completing Phase 1 to verify the foundation is solid.

Usage:
    python tests/test_phase1.py
"""

import sys
import os
from uuid import uuid4

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models import PromptTag, Prompt
from src.llm_clients import generate_with_openai, generate_with_claude, generate_with_gemini, generate_with_random_model
from src.couchbase_client import CouchbaseClient


def test_environment_variables():
    """Test 1: Verify all required environment variables are set."""
    print("\n=== Test 1: Environment Variables ===")

    required_vars = [
        "COUCHBASE_CONNECTION_STRING",
        "COUCHBASE_USERNAME",
        "COUCHBASE_PASSWORD",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY"
    ]

    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)

    if missing:
        print(f"✗ FAILED - Missing environment variables: {', '.join(missing)}")
        return False

    print("✓ PASSED - All environment variables set")
    return True


def test_prompt_tag_model():
    """Test 2: Verify PromptTag serialization/deserialization."""
    print("\n=== Test 2: PromptTag Model ===")

    try:
        # Create a tag
        tag = PromptTag(
            text="You are an expert at compression",
            parent_tag_guid="parent-123",
            source="mutation"
        )

        # Serialize
        tag_dict = tag.to_dict()

        # Deserialize
        tag_restored = PromptTag.from_dict(tag_dict)

        # Verify
        assert tag_restored.text == tag.text
        assert tag_restored.parent_tag_guid == tag.parent_tag_guid
        assert tag_restored.source == tag.source
        assert tag_restored.guid == tag.guid

        print("✓ PASSED - PromptTag serialization works")
        return True

    except Exception as e:
        print(f"✗ FAILED - {str(e)}")
        return False


def test_prompt_model():
    """Test 3: Verify Prompt serialization/deserialization."""
    print("\n=== Test 3: Prompt Model ===")

    try:
        # Create a complete prompt
        prompt = Prompt(
            generation=5,
            era="test-1",
            type="mutation",
            parents=["parent-uuid-123"],
            model_used="claude",
            role=PromptTag(text="Role text", source="mutation"),
            compression_target=PromptTag(text="Target text", source="mutation"),
            fidelity=PromptTag(text="Fidelity text", source="crossover"),
            constraints=PromptTag(text="Constraints text", source="crossover"),
            output=PromptTag(text="Output text", source="mutation"),
            fitness=12.5
        )

        # Serialize
        prompt_dict = prompt.to_dict()

        # Deserialize
        prompt_restored = Prompt.from_dict(prompt_dict)

        # Verify
        assert prompt_restored.generation == 5
        assert prompt_restored.era == "test-1"
        assert prompt_restored.type == "mutation"
        assert prompt_restored.parents == ["parent-uuid-123"]
        assert prompt_restored.model_used == "claude"
        assert prompt_restored.role.text == "Role text"
        assert prompt_restored.fitness == 12.5

        print("✓ PASSED - Prompt serialization works")
        return True

    except Exception as e:
        print(f"✗ FAILED - {str(e)}")
        return False


def test_openai_api():
    """Test 4: Verify OpenAI API connection."""
    print("\n=== Test 4: OpenAI API ===")

    try:
        response = generate_with_openai(
            "Say 'Hello' in exactly one word.",
            temperature=0.0
        )

        if len(response) > 0:
            print(f"✓ PASSED - OpenAI returned: {response[:50]}")
            return True
        else:
            print("✗ FAILED - Empty response from OpenAI")
            return False

    except Exception as e:
        print(f"✗ FAILED - {str(e)}")
        return False


def test_claude_api():
    """Test 5: Verify Claude API connection."""
    print("\n=== Test 5: Claude API ===")

    try:
        response = generate_with_claude(
            "Say 'Hello' in exactly one word.",
            temperature=0.0
        )

        if len(response) > 0:
            print(f"✓ PASSED - Claude returned: {response[:50]}")
            return True
        else:
            print("✗ FAILED - Empty response from Claude")
            return False

    except Exception as e:
        print(f"✗ FAILED - {str(e)}")
        return False


def test_gemini_api():
    """Test 6: Verify Gemini API connection."""
    print("\n=== Test 6: Gemini API ===")

    try:
        response = generate_with_gemini(
            "Say 'Hello' in exactly one word.",
            temperature=0.0
        )

        if len(response) > 0:
            print(f"✓ PASSED - Gemini returned: {response[:50]}")
            return True
        else:
            print("✗ FAILED - Empty response from Gemini")
            return False

    except Exception as e:
        print(f"✗ FAILED - {str(e)}")
        return False


def test_random_model_selection():
    """Test 7: Verify random model selection works."""
    print("\n=== Test 7: Random Model Selection ===")

    try:
        response, model_name = generate_with_random_model(
            "Say 'Hello' in exactly one word.",
            temperature=0.0
        )

        if len(response) > 0 and model_name in ["openai", "claude", "gemini"]:
            print(f"✓ PASSED - {model_name} returned: {response[:50]}")
            return True
        else:
            print(f"✗ FAILED - Invalid response or model name: {model_name}")
            return False

    except Exception as e:
        print(f"✗ FAILED - {str(e)}")
        return False


def test_couchbase_connection():
    """Test 8: Verify Couchbase connection."""
    print("\n=== Test 8: Couchbase Connection ===")

    try:
        with CouchbaseClient() as cb:
            # Just verify we can get a collection handle
            cb.get_collection("prompts")
            print("✓ PASSED - Couchbase connection works")
            return True

    except Exception as e:
        print(f"✗ FAILED - {str(e)}")
        return False


def test_couchbase_document_operations():
    """Test 9: Verify Couchbase read/write operations."""
    print("\n=== Test 9: Couchbase Document Operations ===")

    test_id = f"test-prompt-{uuid4()}"

    try:
        with CouchbaseClient() as cb:
            # Create a test prompt
            test_prompt = Prompt(
                prompt_id=test_id,
                generation=0,
                era="test",
                type="initial",
                model_used="test",
                role=PromptTag(text="Test role")
            )

            # Save to database
            cb.save_document("prompts", test_id, test_prompt.to_dict())
            print(f"  → Saved test document: {test_id}")

            # Retrieve from database
            retrieved = cb.get_document("prompts", test_id)
            print(f"  → Retrieved test document")

            # Verify
            restored_prompt = Prompt.from_dict(retrieved)
            assert restored_prompt.prompt_id == test_id
            assert restored_prompt.generation == 0
            assert restored_prompt.role.text == "Test role"

            print("✓ PASSED - Document read/write works")
            print(f"  → Test document {test_id} left in database for inspection")
            return True

    except Exception as e:
        print(f"✗ FAILED - {str(e)}")
        return False


def main():
    """Run all Phase 1 smoke tests."""
    print("\n" + "="*60)
    print("PHASE 1 INTEGRATION TESTS")
    print("="*60)

    tests = [
        test_environment_variables,
        test_prompt_tag_model,
        test_prompt_model,
        test_openai_api,
        test_claude_api,
        test_gemini_api,
        test_random_model_selection,
        test_couchbase_connection,
        test_couchbase_document_operations
    ]

    results = []
    for test_func in tests:
        try:
            results.append(test_func())
        except Exception as e:
            print(f"\n✗ UNEXPECTED ERROR: {str(e)}")
            results.append(False)

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Tests Passed: {passed}/{total}")

    if passed == total:
        print("\n✓ ALL TESTS PASSED - Phase 1 foundation is solid!")
        print("  Ready to proceed to Phase 2 (Corpus Preparation)")
        return 0
    else:
        print(f"\n✗ {total - passed} TEST(S) FAILED - Fix issues before proceeding")
        return 1


if __name__ == "__main__":
    sys.exit(main())
