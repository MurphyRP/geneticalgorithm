#!/bin/bash
#
# Couchbase Database Setup Script
#
# Creates the required bucket, scope, and collections for the genetic prompt
# evolution framework.
#
# Usage:
#   ./scripts/setup_couchbase.sh [--verify] [--dry-run] [--force] [--help]
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

print_info() {
    echo "  $1"
}

# Function to show help
show_help() {
    cat << EOF
Couchbase Database Setup Script

Creates the required bucket, scope, and collections for the genetic prompt
evolution framework.

Usage:
  ./scripts/setup_couchbase.sh [OPTIONS]

Options:
  --verify      Verify existing structure without creating
  --dry-run     Show what would be created without actually creating
  --force       Force recreate (WARNING: destroys existing data)
  --help        Show this help message

Examples:
  # Create database structure
  ./scripts/setup_couchbase.sh

  # Verify existing structure
  ./scripts/setup_couchbase.sh --verify

  # Preview what would be created
  ./scripts/setup_couchbase.sh --dry-run

  # Force recreate (destroys data!)
  ./scripts/setup_couchbase.sh --force

Database Structure:
  Bucket: genetic
  └── Scope: g_scope
      ├── unstructured (corpus text chunks)
      ├── generations (all evolved prompts)
      ├── generation_stats (per-generation statistics)
      └── eras (experiment configurations)

Prerequisites:
  1. Run: source ./set_env.sh
  2. Ensure .env file has Couchbase credentials
  3. Verify IP is whitelisted in Couchbase Capella

For more information, see:
  - COUCHBASE_SETUP.md
  - project_docs/DATA_IMPORT.md
EOF
}

# Parse command line arguments
VERIFY=false
DRY_RUN=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --verify)
            VERIFY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Run './scripts/setup_couchbase.sh --help' for usage"
            exit 1
            ;;
    esac
done

# Print header
echo "=== Couchbase Database Setup ==="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check if .env file exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    print_error ".env file not found"
    print_info "Copy .env.example to .env and add your credentials:"
    print_info "  cp .env.example .env"
    exit 1
fi

# Check if environment variables are loaded
if [ -z "$COUCHBASE_CONNECTION_STRING" ]; then
    print_error "Environment variables not loaded"
    print_info "Run: source ./set_env.sh"
    exit 1
fi

print_success "Environment variables loaded"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
if [ $? -eq 0 ]; then
    print_success "Python $PYTHON_VERSION found"
else
    print_error "Python 3 not found"
    print_info "Install Python 3.13+ to use this framework"
    exit 1
fi

# Activate virtual environment if it exists and not already activated
if [ -z "$VIRTUAL_ENV" ] && [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    print_info "Activating virtual environment..."
    source "$PROJECT_ROOT/venv/bin/activate"
    print_success "Virtual environment activated"
elif [ -z "$VIRTUAL_ENV" ]; then
    print_warning "Virtual environment not found"
    print_info "Some dependencies may be missing. Create venv with:"
    print_info "  python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
fi

echo ""

# Build Python command
PYTHON_CMD="python3 $SCRIPT_DIR/setup_couchbase.py --json"

if [ "$VERIFY" = true ]; then
    PYTHON_CMD="$PYTHON_CMD --verify"
fi

if [ "$DRY_RUN" = true ]; then
    PYTHON_CMD="$PYTHON_CMD --dry-run"
fi

if [ "$FORCE" = true ]; then
    # Confirm force mode
    echo -e "${YELLOW}WARNING: --force will destroy existing data!${NC}"
    read -p "Are you sure you want to continue? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
    PYTHON_CMD="$PYTHON_CMD --force"
fi

# Run Python script
if [ "$DRY_RUN" = true ]; then
    echo "Running dry-run..."
    python3 "$SCRIPT_DIR/setup_couchbase.py" --dry-run
    exit 0
fi

echo "Running database setup..."
echo ""

# Execute Python script and capture JSON output
JSON_OUTPUT=$(eval "$PYTHON_CMD" 2>&1)
EXIT_CODE=$?

# Parse JSON output
if command -v jq &> /dev/null; then
    # Use jq if available for better parsing
    SUCCESS=$(echo "$JSON_OUTPUT" | jq -r '.success')
else
    # Fallback to grep
    if echo "$JSON_OUTPUT" | grep -q '"success": true'; then
        SUCCESS="true"
    else
        SUCCESS="false"
    fi
fi

# Print results
if [ "$SUCCESS" = "true" ]; then
    print_success "Database setup successful"
    echo ""

    # Count operations
    if command -v jq &> /dev/null; then
        CREATED=$(echo "$JSON_OUTPUT" | jq '[.operations[] | select(.status=="created")] | length')
        SKIPPED=$(echo "$JSON_OUTPUT" | jq '[.operations[] | select(.status=="skipped")] | length')
    else
        CREATED=$(echo "$JSON_OUTPUT" | grep -o '"status": "created"' | wc -l | tr -d ' ')
        SKIPPED=$(echo "$JSON_OUTPUT" | grep -o '"status": "skipped"' | wc -l | tr -d ' ')
    fi

    if [ "$CREATED" -gt 0 ]; then
        echo "Created $CREATED resources"
    fi

    if [ "$SKIPPED" -gt 0 ]; then
        echo "Skipped $SKIPPED existing resources"
    fi

    # Show verification if available
    if command -v jq &> /dev/null && echo "$JSON_OUTPUT" | jq -e '.verification' > /dev/null 2>&1; then
        BUCKET_OK=$(echo "$JSON_OUTPUT" | jq -r '.verification.bucket')
        SCOPE_OK=$(echo "$JSON_OUTPUT" | jq -r '.verification.scope')

        if [ "$BUCKET_OK" = "true" ] && [ "$SCOPE_OK" = "true" ]; then
            echo ""
            echo "Verification:"
            print_success "Bucket 'genetic' accessible"
            print_success "Scope 'g_scope' accessible"

            # Check collections
            for coll in "unstructured" "generations" "generation_stats" "eras"; do
                COLL_OK=$(echo "$JSON_OUTPUT" | jq -r ".verification.collections.${coll}")
                if [ "$COLL_OK" = "true" ]; then
                    print_success "Collection 'g_scope.${coll}' accessible"
                else
                    print_warning "Collection 'g_scope.${coll}' not accessible"
                fi
            done
        fi
    fi

    # Print next steps
    if [ "$VERIFY" != true ]; then
        echo ""
        echo "=== Next Steps ==="
        echo ""
        echo "1. Load your text corpus:"
        echo "   python scripts/populate_corpus.py --domain mixed --dir /path/to/docs"
        echo ""
        echo "2. Run your first experiment:"
        echo "   python scripts/run_experiment.py --era test-1 --population 5 --generations 5 --model claude"
        echo ""
        echo "See project_docs/DATA_IMPORT.md for corpus preparation details."
    fi

    exit 0
else
    print_error "Database setup failed"
    echo ""

    # Show errors
    if command -v jq &> /dev/null; then
        ERRORS=$(echo "$JSON_OUTPUT" | jq -r '.errors[]' 2>/dev/null)
        if [ -n "$ERRORS" ]; then
            echo "Errors:"
            echo "$ERRORS" | while read -r ERROR; do
                print_error "$ERROR"
            done
        fi
    else
        echo "Errors:"
        echo "$JSON_OUTPUT" | grep -o '"errors":.*' | head -1
    fi

    echo ""
    echo "Common issues:"
    print_info "Check COUCHBASE_CONNECTION_STRING in .env"
    print_info "Verify your IP is whitelisted in Couchbase Capella"
    print_info "Confirm COUCHBASE_USERNAME and COUCHBASE_PASSWORD are correct"
    print_info "Ensure your Couchbase cluster is running"

    exit 1
fi
