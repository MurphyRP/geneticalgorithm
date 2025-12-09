# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an open source framework for genetic algorithm-based prompt optimization. The project focuses on making prompt optimization accessible to practitioners while maintaining rigorous lineage tracking for phylogenetic analysis.

**Core Goals:**
- Build accessible prompt optimization framework using genetic algorithms
- Track complete evolutionary lineage for phylogenetic analysis
- Produce two research papers: (1) GA framework, (2) phylogenetic analysis
- Demonstrate multi-model diversity in prompt generation

**Tech Stack:** Python + Couchbase
**Timeline:** 10-14 days of 1-2 hour sessions

## CRITICAL: Keep It Simple

**This is an OPEN SOURCE FRAMEWORK - it must be elegant, lean, and understandable**

- **NO complex abstractions** - Simple, direct implementations only
- **NO over-engineering** - If it can be done simply, do it simply
- **NO automatic "smart" features** - Be explicit and predictable
- **MINIMAL code** - Every line should have a clear purpose
- **When asked for specific changes, implement ONLY those changes** - Don't add extra features or complexity
- **Reproducibility is key** - Code should be clear enough for researchers to replicate

## Code Documentation Philosophy

This framework is designed for open source contribution and academic reproducibility. Documentation is critical.

### What to Document

- **WHAT and WHY** - Not just what the code does, but why it exists in the architecture
- **Relationships** - How each file relates to other files in the system
- **Architecture context** - Where does this component fit in the bigger picture?
- **Clear docstrings** - Every class and non-trivial function should explain its purpose
- **Lineage tracking** - This is critical for phylogenetic analysis, document the parent/child relationships carefully

### Documentation Standards

```python
# GOOD - Shows what, why, and context
class Prompt:
    """
    Represents a single prompt with its tags and evaluation results.

    This is the core unit of evolution. Each prompt contains 5 tags that can
    be mutated or crossed over. Prompts track their parents via prompt_id
    references, enabling phylogenetic tree construction later.

    Used by: GeneticAlgorithm, CouchbaseManager, EvaluationPipeline
    Creates: Generation statistics, lineage data for Paper 2
    """

# BAD - Just describes the obvious
class Prompt:
    """A prompt object."""
```

## Communication Style

- **Always discuss before implementing** - don't jump straight to building
- **Ask for clarification** when requests could be interpreted multiple ways
- **Propose solutions first** - get approval before executing
- **When in doubt, ask** - This is research code, precision matters

## When to Build vs Discuss

- **Discuss first** for new features, significant changes, or ambiguous requests
- **Build immediately** only when explicitly requested with clear requirements
- **For testing** - Prefer simple Python scripts over complex test frameworks during development

## CRITICAL: Error Handling Philosophy

- **NEVER implement quiet failures or silent fallbacks** - If a critical component fails, the application should fail loudly and clearly
- **NO "limited functionality" modes** - If database connections or model APIs fail, the system should not continue
- **FAIL FAST, FAIL LOUD** - Better to have a clear error that forces fixing the root cause than to mask issues with fallbacks
- **Hard-coded fallbacks that hide failures are FORBIDDEN** - They make debugging impossible and create false confidence
- **Every critical failure must be visible and actionable** - Don't catch and suppress errors that indicate fundamental problems

## CRITICAL: Trust the LLM Principle

**This is a fundamental design paradigm for the research validity of this framework.**

The research goal is to discover **generalizable compression approaches** that work across diverse text types. To achieve this, we must trust LLMs to create domain-agnostic prompts without biasing them toward specific content.

### Core Principles

- **LLMs generate prompts WITHOUT seeing input text** - No sample text context during generation
- **No domain-specific instructions or hints** - Let LLMs create generalizable approaches naturally
- **No "smart" matching features** - Don't bias toward specific text types or domains
- **LLMs should be creative and generalizable** - Not tailored to legal, medical, technical, etc.

### Why This Matters

Providing sample text context during prompt generation causes LLMs to create domain-specific prompts (e.g., "legal expert" for legal text, "medical expert" for medical text), which:

1. **Defeats the generalization objective** - Research tests universal compression, not domain-specific optimization
2. **Makes prompts brittle** - A "legal expert" prompt fails on medical text and vice versa
3. **Invalidates research conclusions** - Can't claim universal effectiveness if prompts are domain-matched
4. **Creates unfair fitness comparisons** - Domain-matched prompts have artificial advantage over mismatched ones

### Implementation

- **Generation 0 (`generate_initial_prompt`)**: LLMs create prompts with NO text examples
- **Immigration (`create_immigrant`)**: Fresh prompts generated with NO text context
- **Mutation (`mutate_prompt`)**: Improvements based on tag text alone, no external context
- **Crossover (`crossover`)**: Recombines existing tags, no new LLM generation needed

### What Text IS Used For

- **Fitness evaluation** - Prompts are tested on diverse text corpus (this is correct and necessary)
- **Quality judging** - Judges see original + compressed text to score quality (necessary for evaluation)
- **Corpus metadata** - Domain labels help analyze which text types compress well (Paper 2 analysis)

The separation is clear: **Generation = blind, Evaluation = informed**.

---

**Date Added:** 2025-11-12
**Rationale:** Core design principle ensuring research validity and generalizability

## Architecture

### Data Model - Couchbase Collections

The framework uses 4 collections in the `genetic` bucket, `g_scope` scope:

1. **unstructured** - Source corpus for compression tasks
   - Contains diverse text chunks extracted from documents
   - ~600-word segments, various domains (academic, medical, conversational, etc.)
   - Each chunk rated for suitability via `suitable_for_compression_testing` field
   - Key: `chunk_id`
   - Used by: `corpus_sampler.py` for evaluation corpus selection

2. **generations** - ALL prompts from ALL generations (Gen 0, 1, 2, ..., N)
   - Contains complete prompt genome (5 tags) + evaluation results + lineage
   - Each document = ONE PROMPT with fitness scores and compression results
   - Tracks parents, generation, era, model used
   - Key: `{era}-gen-{generation}-{prompt_id}`
   - **Critical for Paper 2**: Enables recursive lineage queries across all generations

3. **generation_stats** - Summary statistics per generation
   - Enables gradient visualization without querying all prompts
   - Contains mean/std/median fitness, operator counts, timing
   - Key: `{era}-gen-{generation}`

4. **eras** - Configuration and metadata for each experimental run
   - Tracks compression model, population size, GA parameters
   - Records start/end time, completion status, final statistics
   - Format: `{domain}-{run_number}` (e.g., "mixed-1", "test-1")
   - Key: `{era}`

**Note:** The `prompts` and `paragraphs` collections are deprecated as of 2025-01-12.
All prompts are now in `generations` collection with proper document ID format.

### Core Architecture Components

**Genetic Algorithm Pipeline:**
```
1. Corpus Preparation → unstructured collection (via corpus_extractor.py)
2. Corpus Vetting → rate chunks via corpus_sampler.py
3. Generation 0 → Initial population (default: 20 prompts)
4. Evaluation → Execute compression + judge quality + calculate fitness
5. Selection → Top 20% elite
6. Operators → Mutation (20%) + Crossover (fill) + Immigration (8% odd gens only)
7. Statistical Tests → Check for stagnation, adapt parameters
8. Loop until descent complete
```

**Key Files Structure** (will be created):
- `models/` - Data classes (Prompt, Tag, Generation, Era)
- `db/` - Couchbase connection and queries
- `execution/` - Model executors (OpenAI, Claude, Gemini)
- `ga/` - GA operators (selection, mutation, crossover, immigration)
- `evaluation/` - Fitness calculation pipeline
- `analysis/` - Statistical tests and visualization

### Multi-Model Strategy

**For prompt generation:**
- Three models: OpenAI (GPT-4o), Claude (Sonnet 4.5), Gemini
- Truly random selection each time (no distribution balancing)
- Each prompt tracks which model generated it via `model_used` field

**For compression execution:**
- ONE model per era (consistent across all prompts in that era)
- Specified in era config as `compression_model`
- Example: All prompts in "mixed-1" use Claude for compression

**For quality judging:**
- ALL THREE models judge each compression
- Each gives score 0-10 on clarity, faithfulness, readability
- Average the three scores for `quality_score_avg`
- Stored as: `{"openai": 8.5, "claude": 7.2, "gemini": 8.8}`

### Fitness Function

```python
fitness = quality_score_avg × compression_ratio × survival_factor

where:
  compression_ratio = original_words / compressed_words
  quality_score_avg = average of 3 judge scores (0-10)
  survival_factor = 0 if expanded, 1 if compressed
```

### Lineage Tracking

**Critical for Paper 2 - Phylogenetic Analysis**

Every prompt tracks lineage via:
- `parents`: Array of parent prompt_id(s) - null for initial/immigrant
- `type`: "initial" | "mutation" | "crossover" | "immigrant"

Every tag tracks lineage via:
- `parent_tag_guid`: The tag guid this evolved from - null for initial/immigrant
- `source`: "initial" | "mutation" | "crossover" | "immigrant"
- `guid`: Unique identifier - NEW guid on mutation, INHERITED on crossover

This enables:
- Building phylogenetic trees for prompts
- Tracing tag evolution through generations
- Analyzing which mutations led to fitness improvements
- Identifying successful vs failed evolutionary paths

## Directory Structure and Conventions

**All paths are relative to the project root.**

### `/project_docs/`
All project documentation (Markdown files) lives here:
- Architecture documents
- Design decisions
- Implementation plans
- Phase documentation
- Research notes
- Meeting notes

**Examples:**
- `/project_docs/phase_1.md`
- `/project_docs/architecture_overview.md`
- `/project_docs/ga_implementation_plan.md`

**Why:** Keeps all documentation organized and separate from code. Easy to find, easy to maintain.

### `/tmp/`
All temporary files for testing or ANY temporary needs:
- Test outputs
- Scratch files
- Debug dumps
- Temporary data files
- Experimental code

**Examples:**
- `/tmp/test_output.json`
- `/tmp/debug_prompt.txt`
- `/tmp/fitness_test.csv`

**Why:** Clear separation of temporary vs permanent. Easy cleanup. No confusion about what should be committed.

### Core Project Directories

```
genetic-prompts/
├── project_docs/           # All .md documentation files
├── tmp/                    # All temporary/test files
├── src/                    # Production Python code
├── tests/                  # Unit and integration tests
├── requirements.txt        # Dependencies
├── .env                    # API keys (gitignored)
├── .gitignore              # Ignore tmp/ and .env
└── README.md               # Main project README
```

### Guidelines

1. **Documentation:** If it's a `.md` file explaining something, it goes in `/project_docs/`
2. **Temporary:** If it's for testing, debugging, or experimentation, it goes in `/tmp/`
3. **Code:** If it's production Python, it goes in `/src/`
4. **Tests:** If it's a test file, it goes in `/tests/`

### Git Behavior

**Commit:**
- `/project_docs/` - Always commit
- `/src/` - Always commit
- `/tests/` - Always commit

**Ignore:**
- `/tmp/` - Always ignore (in .gitignore)
- `.env` - Always ignore (in .gitignore)

---

**Date Added:** 2025-11-03
**Purpose:** Maintain clean, organized project structure

## Common Commands

### Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode (when setup.py exists)
pip install -e .
```

### Running the Framework

```bash
# Run corpus preparation (Day 1)
python scripts/prepare_corpus.py

# Quick test evolution (default: 20 prompts, fast iteration)
python scripts/run_experiment.py --era quicktest --population 20 --generations 5

# Standard test evolution
python scripts/run_experiment.py --era test-1 --population 20 --generations 10

# Production evolution (larger population)
python scripts/run_experiment.py --era mixed-1 --population 100 --generations 20

# Custom parameters (percentage-based)
python scripts/run_evolution.py --era custom-1 --population 20 --generations 10 \
    --mutation-fraction 0.2 --immigration-fraction 0.08

# Analyze results
python scripts/analyze_results.py --era quicktest
```

### Development Testing

```bash
# Test Couchbase connection
python -c "from db.manager import CouchbaseManager; cm = CouchbaseManager(); print('Connected!')"

# Test model executors
python tests/test_models.py

# Test GA operators
python tests/test_ga_operators.py

# Run full test suite
pytest tests/
```

### Couchbase Queries (via MCP or N1QL)

```sql
-- Get all prompts in a generation
SELECT * FROM `genetic`.`g_scope`.`generations`
WHERE era = 'mixed-1' AND generation = 5
ORDER BY fitness DESC;

-- Get generation statistics
SELECT * FROM `genetic`.`g_scope`.`generation_stats`
WHERE era = 'mixed-1'
ORDER BY generation;

-- Trace prompt lineage
SELECT prompt_id, generation, parents, fitness
FROM `genetic`.`g_scope`.`generations`
WHERE prompt_id = 'target-prompt-id' OR prompt_id IN (
  -- Recursive query to find all ancestors
);

-- Find best performing prompts
SELECT prompt_id, fitness, compression_ratio, quality_score_avg
FROM `genetic`.`g_scope`.`generations`
WHERE era = 'mixed-1'
ORDER BY fitness DESC
LIMIT 10;
```

## MCP Tools Available

The following Couchbase MCP tools are pre-approved and configured:
- `mcp__couchbase-mcp__get_scopes_and_collections_in_bucket`
- `mcp__couchbase-mcp__get_server_configuration_status`
- `mcp__couchbase-mcp__test_cluster_connection`
- `mcp__couchbase-mcp__get_schema_for_collection`
- `mcp__couchbase-mcp__run_sql_plus_plus_query`
- `mcp__couchbase-mcp__get_document_by_id`

### MCP Configuration

**IMPORTANT:** Claude Code MCP configuration has changed in recent updates. There are now three config scopes:

**1. User Config (Global)** - `~/.claude.json`
- Available across ALL your projects
- Best for personal development setups
- **Not shared** in version control

**2. Project Config (Shared)** - `.mcp.json` in project root
- Shared via git for team collaboration
- Enables reproducible research environments
- **Should be gitignored** with credentials as placeholders
- This is NEW as of Claude Code 2.x updates

**3. Local Config (Private)** - `~/.claude.json` with project scope
- Private overrides for this specific project
- Managed internally by Claude Code

### Configuration for This Project

**Database Connection:**
- Bucket: `genetic`
- Scope: `g_scope`
- Collections: `unstructured`, `prompts`, `generations`, `eras`

**For Contributors:**

1. Copy `.mcp.json` template in project root
2. Update with your Couchbase cluster credentials:
   - `CB_CONNECTION_STRING`: Your cluster connection string
   - `CB_USERNAME`: Your cluster username
   - `CB_PASSWORD`: Your cluster password
3. Keep `.mcp.json` gitignored to protect credentials

**Example `.mcp.json` format:**
```json
{
  "mcpServers": {
    "couchbase-mcp": {
      "command": "uvx",
      "args": ["couchbase-mcp-server"],
      "env": {
        "CB_CONNECTION_STRING": "couchbases://your-cluster.cloud.couchbase.com",
        "CB_USERNAME": "your_username",
        "CB_PASSWORD": "your_password",
        "CB_BUCKET_NAME": "genetic",
        "CB_SCOPE_NAME": "g_scope",
        "CB_MCP_READ_ONLY_QUERY_MODE": "false"
      }
    }
  }
}
```

## Implementation Guidelines

### When Starting a New Component

1. **Read the implementation plan** (`ga_implementation_plan_final.md`) for context
2. **Understand the data flow** - What comes before? What comes after?
3. **Document relationships** - Which files does this interact with?
4. **Keep it simple** - Resist the urge to add "nice to have" features
5. **Test incrementally** - Don't build everything before testing

### Code Organization Principles

- **One concern per file** - Don't mix data models with execution logic
- **Clear interfaces** - Functions should have obvious inputs/outputs
- **Minimize dependencies** - Each module should be as independent as possible
- **Type hints required** - Use Python type hints for all function signatures
- **Dataclasses preferred** - Use `@dataclass` for data structures

### Testing Strategy

- **Unit tests** for GA operators (mutation, crossover, selection)
- **Integration tests** for full pipeline (small population runs)
- **Validation tests** for data integrity (lineage completeness)
- **Performance tests** for API call efficiency
- **Cost tracking** for API usage monitoring

## Research Goals & Success Metrics

### Paper 1: GA Framework
- [ ] Descent achieved within 10-15 generations
- [ ] Final prompts: >40% token reduction
- [ ] Quality scores: >7/10 average
- [ ] Complete lineage data collected
- [ ] Reproducible methodology documented

### Paper 2: Phylogenetic Analysis
- [ ] Complete phylogenetic trees constructed
- [ ] ≥2 tag types show clear mutation correlation with fitness
- [ ] Successful lineage patterns identified
- [ ] Failure modes cataloged
- [ ] Methodology generalizable to other optimization tasks

## Cost Management

**Estimated costs per era run:**
- Generation: ~1,000 prompts × random models = ~1,000 API calls
- Compression: ~1,000 compressions × 1 model = ~1,000 API calls
- Judging: ~1,000 judgments × 3 models = ~3,000 API calls
- **Total: ~5,000 API calls per era**
- **Estimated cost: $30-80** depending on models used

Always track API usage and costs during runs. Paper 2 requires NO additional API calls.
