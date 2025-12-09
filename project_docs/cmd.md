# Command Line Quick Reference

**Script:** `scripts/run_experiment.py` (complete workflow: Gen 0 + Evolution)

## Essential Options

### Required Parameters
- `--era` - Unique experiment identifier (e.g., "test-1", "phylo-1")
- `--population` - Number of prompts per generation (20 for testing, 50-100 for production)
- `--generations` - Number of generations to evolve (5 for testing, 20+ for production)

### Key Optional Parameters
- `--model` - Compression model: `claude` (default), `openai`, `gemini`, `gemini3`
- `--token-eval` - Use token-based fitness instead of word-based (recommended for research)
- `--single-tag` - Enable single-tag mode for phylogenetic tracking (required for Paper 2)
- `--no-convergence-stop` - Continue evolution even if fitness plateaus

### GA Parameters (Optional)
- `--elite 0.2` - Elite fraction (default: 0.2 = 20%)
- `--mutation-fraction 0.2` - Mutation rate (default: 0.2 = 20%)
- `--immigration-fraction 0.08` - Immigration rate on odd gens (default: 0.08 = 8%)
- `--prompt-temp 1.0` - Temperature for prompt generation (default: 1.0)

### Convergence Settings (Optional)
- `--convergence-window 3` - Generations to check for plateau (default: 3)
- `--convergence-threshold 0.05` - Max fitness change to converge (default: 0.05 = 5%)

---

## Example Usage

### Quick Test (20-30 minutes)
```bash
python scripts/run_experiment.py \
  --era quicktest \
  --population 20 \
  --generations 5 \
  --model claude
```

### Production Phylogenetic Run (4-6 hours)
```bash
python scripts/run_experiment.py \
  --era phylo-3 \
  --population 50 \
  --generations 20 \
  --model claude \
  --token-eval \
  --single-tag
```

### Background Execution (EC2/Server)
```bash
nohup python scripts/run_experiment.py \
  --era phylo-3 \
  --population 50 \
  --generations 20 \
  --model claude \
  --token-eval \
  --single-tag \
  > tmp/phylo-3.log 2>&1 < /dev/null &
```

---

## Complete Example with All Research Settings

```bash
python scripts/run_experiment.py \
  --era phylo-production-1 \
  --population 50 \
  --generations 20 \
  --model claude \
  --token-eval \
  --single-tag \
  --elite 0.2 \
  --mutation-fraction 0.2 \
  --immigration-fraction 0.08 \
  --convergence-window 3 \
  --convergence-threshold 0.05 \
  --prompt-temp 1.0
```

**Expected Results:**
- Runtime: ~6-8 hours
- Generations: Up to 20 (may stop early if converged)
- Output: `tmp/experiment_phylo-production-1_<timestamp>.json`

---

## Viewing Results

### Web Dashboard
```bash
cd viz
python app.py
# Open http://localhost:8080
```

### Database Queries
```sql
-- View all eras
SELECT era, max_generation, total_prompts FROM eras ORDER BY era;

-- View generation stats for an era
SELECT generation, mean_fitness, max_fitness
FROM generation_stats
WHERE era = 'phylo-3'
ORDER BY generation;

-- View best prompts in an era
SELECT generation, fitness, quality_score_avg, compression_ratio
FROM generations
WHERE era = 'phylo-3'
ORDER BY fitness DESC
LIMIT 10;
```

---

**See Also:**
- `project_docs/architecture_overview.md` - System architecture
- `project_docs/ga_implementation_plan_final.md` - GA details
- `project_docs/fitness_function.md` - Fitness calculation
- `project_docs/gen_stats.md` - Statistical tests and convergence
