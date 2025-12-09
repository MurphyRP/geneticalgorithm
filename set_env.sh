#!/bin/bash
#
# set_env.sh - Load environment variables from .env file
#
# Usage:
#   source ./set_env.sh
#   OR
#   . ./set_env.sh
#
# This script reads the .env file and exports all variables into your current shell.
#

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    echo ""
    echo "Please create a .env file with your credentials:"
    echo "  cp .env.example .env"
    echo "  # Then edit .env with your actual values"
    return 1 2>/dev/null || exit 1
fi

# Load and export variables from .env
echo "Loading environment variables from .env..."
set -a  # Automatically export all variables
source .env
set +a  # Turn off automatic export

# Verify critical variables are set
MISSING_VARS=()

if [ -z "$COUCHBASE_CONNECTION_STRING" ]; then
    MISSING_VARS+=("COUCHBASE_CONNECTION_STRING")
fi

if [ -z "$COUCHBASE_USERNAME" ]; then
    MISSING_VARS+=("COUCHBASE_USERNAME")
fi

if [ -z "$COUCHBASE_PASSWORD" ]; then
    MISSING_VARS+=("COUCHBASE_PASSWORD")
fi

if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
    MISSING_VARS+=("At least one LLM API key (OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY)")
fi

# Report status
if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo ""
    echo "WARNING: The following required variables are missing or empty:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Please update your .env file with the missing values."
    return 1 2>/dev/null || exit 1
fi

echo "✓ Environment variables loaded successfully!"
echo ""
echo "Configured:"
echo "  Couchbase: ${COUCHBASE_CONNECTION_STRING}"
echo "  Bucket:    ${COUCHBASE_BUCKET:-genetic}"
echo "  Scope:     ${COUCHBASE_SCOPE:-g_scope}"
echo ""
echo "API Keys:"
[ -n "$OPENAI_API_KEY" ] && echo "  ✓ OpenAI"
[ -n "$ANTHROPIC_API_KEY" ] && echo "  ✓ Anthropic (Claude)"
[ -n "$GOOGLE_API_KEY" ] && echo "  ✓ Google (Gemini)"
echo ""
echo "Ready to run experiments!"
