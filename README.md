# Genetic Prompt Evolution Framework

A genetic algorithm framework for optimizing text compression prompts through multi-model LLM evolution. Uses evolutionary operators (selection, crossover, mutation, immigration) to discover compression strategies that balance quality and token reduction according to your specific needs.

**What This Framework Does:**
- Automatically generates text compression prompts using three different LLMs
- Tests each prompt on your corpus to measure compression quality
- Evolves prompts across generations using genetic algorithm operators
- Tracks complete evolutionary lineage for analysis and reproducibility
- Enables configuration of your quality-compression tradeoff

**Tech Stack:** Python 3.13+ • Couchbase • OpenAI/Claude/Gemini APIs

---

## Why Use This Framework?

Text compression (semantic summarization) presents a fundamental optimization challenge: reducing token count while preserving meaning. Different applications have different tradeoffs:

- **AI memory systems** prioritize extreme compression, accepting some information loss
- **Legal discovery systems** demand high fidelity, tolerating larger token counts
- **Customer support** seeks middle ground between compression and clarity
- **Research literature review** might favor aggressive compression for volume processing

This framework lets you define YOUR quality-compression tradeoff through configuration, then systematically search for prompts that achieve it. Rather than manual prompt engineering, the genetic algorithm explores the prompt space automatically across multiple generations.

---

## Prerequisites

- **Python:** 3.13 or higher
- **Couchbase:** Cloud or local cluster with bucket named `genetic`, scope `g_scope`
- **API Keys:** OpenAI, Anthropic (Claude), Google (Gemini)
- **Collections:** The framework will create/use these Couchbase collections automatically:
  - `unstructured` - Your corpus of text chunks for evaluation
  - `generations` - All evolved prompts with results and lineage
  - `generation_stats` - Summary statistics per generation
  - `eras` - Configuration and metadata for each experimental run

---

## Quick Start (5 minutes)

### 1. Clone and Setup

```bash
# Navigate to project directory
cd genprompt

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# OR
.\venv\Scripts\activate   # Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Credentials

Create a `.env` file with your credentials:

```bash
cp .env.example .env
# Edit .env with your actual values
```

**Required variables:**
```env
COUCHBASE_CONNECTION_STRING=couchbases://your-cluster.cloud.couchbase.com
COUCHBASE_USERNAME=your_username
COUCHBASE_PASSWORD=your_password
COUCHBASE_BUCKET=genetic
COUCHBASE_SCOPE=g_scope

OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
GOOGLE_API_KEY=your-google-api-key-here
```

### 4. Load Environment

```bash
source ./set_env.sh
```

### 5. Run Your First Experiment

```bash
# Quick test (20 prompts, 5 generations, ~15-25 minutes)
python scripts/run_experiment.py --era quicktest --population 20 --generations 5 --model claude
```

**Expected output:** Initial population created, then 5 generations of evolution with fitness improvements visible in console output.

---

## Three-Phase Workflow

### Phase 1: Prepare Your Corpus (One-time Setup)

Before evolution can begin, populate the `unstructured` collection with text chunks:

```bash
# Process a single file
python scripts/populate_corpus.py --domain mixed --file /path/to/document.pdf

# Process a directory (all PDF/HTML/MD files)
python scripts/populate_corpus.py --domain mixed --dir /path/to/documents/

# Custom chunk size (default is 600 words)
python scripts/populate_corpus.py --domain mixed --dir /path/to/documents/ --target-words 500
```

**Supported file types:** PDF, HTML, Markdown

**Chunk size:** Default 600 words works well for most text types. Adjust `--target-words` based on your needs.

The corpus preparation is a one-time process. You can run multiple experiments against the same corpus.

---

### Phase 2 & 3: Create and Evolve Prompts

The recommended approach is to use `run_experiment.py` which handles everything in a single command:

```bash
# Quick validation (5 prompts, 5 generations)
python scripts/run_experiment.py --era test-quick --population 5 --generations 5 --model claude

# Standard test (20 prompts, 10 generations)
python scripts/run_experiment.py --era test-1 --population 20 --generations 10 --model claude

# Production run (100 prompts, 20 generations)
python scripts/run_experiment.py --era prod-1 --population 100 --generations 20 --model claude

# Custom parameters
python scripts/run_experiment.py --era custom-1 --population 20 --generations 10 \
    --elite 0.2 --mutation-fraction 0.2 --tags-per-mutation 1 --immigration-fraction 0.08
```

**Runtime expectations:**
- Gen 0 creation: 3-10 minutes (depends on population size)
- Each subsequent generation: 2-5 minutes
- Evolution stops automatically if fitness plateaus

---

### Phase 4: Analyze Results

Query results using Python or Couchbase directly:

```python
from src.couchbase_client import CouchbaseClient

with CouchbaseClient() as cb:
    # Get generation statistics for your experiment
    query = """
        SELECT generation, mean_fitness, median_fitness, std_fitness
        FROM generation_stats
        WHERE era = 'test-1'
        ORDER BY generation
    """
    for row in cb.cluster.query(query):
        print(f"Generation {row['generation']}: mean_fitness={row['mean_fitness']}")

    # Get top 10 prompts by fitness
    query = """
        SELECT prompt_id, generation, fitness, compression_ratio, quality_score_avg
        FROM generations
        WHERE era = 'test-1'
        ORDER BY fitness DESC
        LIMIT 10
    """
    for prompt in cb.cluster.query(query):
        print(f"Prompt {prompt['prompt_id']}: fitness={prompt['fitness']}")
```

---

## Configuration Guide

### Key Parameters

| Parameter | Description | Default | Typical Values |
|-----------|-------------|---------|-----------------|
| `--population` | Number of prompts per generation | 20 | 20 (testing), 50-100 (production) |
| `--generations` | Number of generations to evolve | 10 | 5 (quick test), 20+ (thorough search) |
| `--elite` | Fraction of population to preserve unchanged | 0.2 | 0.2 (20%) |
| `--mutation-fraction` | Fraction created via mutation | 0.2 | 0.2 (20%) |
| `--tags-per-mutation` | Number of tags to mutate per prompt | 1 | 1-2 |
| `--immigration-fraction` | Fraction of fresh prompts (odd generations) | 0.08 | 0.08 (8%) |
| `--model` | Compression model to use | claude | claude (recommended) |

### Model Selection Strategy

**Prompt generation (automatic):**
- Randomly selects among OpenAI GPT-4o, Claude Sonnet 4.5, Gemini Pro, Gemini 3 Pro for each new prompt
- Ensures diversity in prompt creation styles
- Each prompt tracks which model generated it

**Compression execution (per experiment):**
- Single model specified for entire experiment (--model flag)
- All compressions in an experiment use the same model for fair comparison
- Choose `claude`, `openai`, or `gemini` based on your needs

**Quality judging (automatic):**
- All three models judge each compression independently
- Each provides a score (0-10) on clarity, faithfulness, readability
- Final quality score is the average of all three
- Provides more robust assessment than single-model judging

---

## Understanding Fitness

The framework uses a fitness function to measure how well each prompt performs:

```
fitness = quality_score_avg × compression_ratio × survival_factor

where:
  compression_ratio = original_words / compressed_words
  quality_score_avg = average of 3 judge scores (0-10 scale)
  survival_factor = 1 if text compressed, 0 if text expanded
```

**Quality score:** Averages evaluations from three different LLMs to reduce bias
**Compression ratio:** Higher ratio means more aggressive compression
**Survival filter:** Prompts that expand text are eliminated (fitness = 0)

This means fitness prioritizes quality while rewarding compression. You can adjust the emphasis by modifying the fitness function in `src/fitness_evaluator.py`.

---

## Project Structure

```
genprompt/
├── src/                        # Core framework code
│   ├── models.py               # Data models (Prompt, PromptTag)
│   ├── couchbase_client.py     # Database connection
│   ├── llm_clients.py          # OpenAI/Claude/Gemini integration
│   ├── initial_prompts.py      # Generation 0 creation
│   ├── ga_operators.py         # Selection, mutation, crossover, immigration
│   ├── fitness_evaluator.py    # Compression + judging pipeline
│   ├── evolution.py            # Evolution orchestrator
│   ├── corpus_extractor.py     # Text extraction from documents
│   └── corpus_sampler.py       # Evaluation corpus selection
│
├── scripts/                    # Executable scripts
│   ├── populate_corpus.py      # Phase 1: Corpus preparation
│   ├── run_experiment.py       # Complete workflow
│   ├── import_json_chunks.py   # Alternative import method
│   └── cleanup_collections.py  # Database maintenance
│
├── project_docs/              # User documentation
│   ├── fitness_function.md    # How fitness is calculated
│   ├── DATA_IMPORT.md         # Corpus preparation guide
│   ├── runme.md               # Execution patterns and timing
│   └── generalized_to_targeted.md  # Domain adaptation guide
│
├── viz/                       # Visualization dashboard
│   ├── app.py                 # Flask server (1200+ lines)
│   ├── templates/             # Dashboard HTML pages
│   ├── static/                # JavaScript charts and CSS
│   └── requirements_viz.txt   # Dashboard dependencies
│
├── tests/                     # Test suite
├── tmp/                       # Temporary files (gitignored)
├── requirements.txt           # Python dependencies
├── .env.example               # Environment template
├── .gitignore                 # Git ignore rules
├── CLAUDE.md                  # Architecture notes (for contributors)
└── README.md                  # This file
```

---

## Visualization & Analysis Dashboard

The framework includes a complete Flask-based web dashboard for analyzing evolution results in real-time.

### Quick Start

```bash
cd viz
pip install -r requirements_viz.txt
python app.py
# Open http://localhost:8080
```

### Dashboard Features

**Main Dashboard** (`/`)
- **Fitness Trajectories** - Track mean/max/min fitness across generations
- **Operator Effectiveness** - See mutation/crossover/immigration counts per generation
- **Diversity Tracking** - Monitor tag diversity (unique GUIDs) across evolution

**Lineage Explorer** (`/lineage`)
- Interactive Sankey diagram showing complete prompt ancestry
- Trace parent-child relationships across all generations
- Color-coded by operation type (initial, mutation, crossover, immigrant)
- Click nodes to view full prompt details and tag text

**Phylogenetic Attribution Analysis** (`/phylo_attribution`)
*Requires single-tag mode: `--single-tag` flag*
- **Tag Metrics** - Mean fitness/quality/compression by individual tag variants
- **Tag Type Deltas** - Which tag types (role, fidelity, etc.) drive fitness improvements
- **Tag Lineage** - Trace evolutionary history of specific high-performing tags

**Tag Evolutionary Story** (`/tag_story`)
*Requires single-tag mode*
- **Survival Analysis** - Which Generation 0 tags made it to final elites
- **Breakthrough Moments** - When fitness jumped significantly, which tags changed
- **Elite Patterns** - Tag enrichment ratios (more common in elites vs general population)

### Single-Tag Mode

For phylogenetic attribution analysis, run experiments with `--single-tag` flag:

```bash
python scripts/run_experiment.py --era phylo-1 --population 50 --generations 20 \
    --model claude --single-tag
```

This mode restricts crossover to swap single tags at a time, enabling precise attribution of fitness improvements to specific tag changes.

---

## Troubleshooting

### Connection Issues

Test your Couchbase connection:

```python
from src.couchbase_client import CouchbaseClient

with CouchbaseClient() as cb:
    print("Connected to Couchbase successfully!")
```

### API Key Issues

Test that your LLM API keys work:

```python
from src.llm_clients import generate_with_random_model

response, model = generate_with_random_model(
    "Say hello in exactly one word",
    temperature=0.7
)
print(f"Model: {model}, Response: {response}")
```

### Empty Corpus

If you see "no suitable text found for evaluation", your `unstructured` collection is empty. Run Phase 1 first:

```bash
python scripts/populate_corpus.py --domain mixed --dir /path/to/documents/
```

### Collection Structure

The framework uses these Couchbase collections:
- **unstructured:** Text chunks for evaluation (created by populate_corpus.py)
- **generations:** All prompts with results (created automatically during first run)
- **generation_stats:** Summary statistics per generation (created automatically)
- **eras:** Configuration for each experiment (created automatically)

---

## Documentation

- **Fitness Function Detailed Explanation:** See `project_docs/FITNESS_FUNCTION.md`
- **Data Import & Corpus Preparation:** See `project_docs/DATA_IMPORT.md`
- **Different Execution Patterns:** See `project_docs/EXECUTION_PATTERNS.md`
- **Contributing & Architecture:** See `CLAUDE.md`

---

## Key Framework Principles

**Keep it Simple:** The framework prioritizes clarity over clever abstractions. Every component should be understandable.

**Fail Loudly:** If something critical breaks (database connection, API failure), the framework stops immediately with clear error messages rather than attempting to continue.

**Configurability:** You define your quality-compression tradeoff through the fitness function. The genetic algorithm finds solutions that match your requirements.

**Reproducibility:** Complete lineage tracking enables you to understand exactly how each prompt evolved and reproduce results.

---

## License

Open source framework for academic research and practical prompt optimization.

---

## Contributing

Contributions welcome! The framework is designed for extensibility:

- **New fitness functions:** Modify `fitness_evaluator.py` to test different quality-compression balances
- **New document types:** Extend `corpus_extractor.py` to support additional formats
- **New GA operators:** Add variation operators in `ga_operators.py`
- **New analysis tools:** Build on the lineage data for your own research

See `CLAUDE.md` for architecture guidance and contribution principles.

---

**Framework Status:** Production Ready
**Last Updated:** December 8, 2025
**Version:** 1.0
