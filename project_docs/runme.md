# Execution Patterns Guide

Comprehensive guide to running genetic algorithm experiments. Based on real timing data from phylo-1 (1.1 hours, 5 gens) and phylo-2 (4.4 hours, 23 gens).

---

## Quick Reference

| Use Case | Population | Generations | Time | Command |
|----------|------------|-------------|------|---------|
| Quick Validation | 5 | 3-5 | 15-25 min | `--era quicktest` |
| Standard Test | 20 | 5-10 | 30-90 min | `--era test-1` |
| Short Production | 50 | 5 | 1.1 hrs | `--era pilot-1` |
| Full Production | 50 | 20+ | 4-6 hrs | `--era phylo-2` |
| Large Scale | 100 | 20+ | 8-12 hrs | `--era production-1` |

**Real Timing:**
- phylo-1: 50 prompts × 5 gens = 66.2 min (1.1 hours)
- phylo-2: 50 prompts × 23 gens = 264.9 min (4.4 hours)

---

## Pattern 1: Quick Validation (15-25 minutes)

**Purpose:** Verify setup, validate configuration

```bash
python scripts/run_experiment.py \
  --era quicktest \
  --population 5 \
  --generations 3 \
  --model claude
```

**Expected:** Fitness improvement by Gen 3, all systems working

---

## Pattern 2: Standard Test (30-90 minutes)

**Purpose:** Validate GA dynamics, test operators

```bash
python scripts/run_experiment.py \
  --era test-1 \
  --population 20 \
  --generations 10 \
  --model claude
```

**Expected:** 5-15% fitness improvement, convergence around Gen 5-7

---

## Pattern 3: Short Production (1-2 hours)

**Purpose:** Real research data, abbreviated timeline

```bash
python scripts/run_experiment.py \
  --era pilot-1 \
  --population 50 \
  --generations 5 \
  --model claude \
  --token-eval
```

**Real Timing (phylo-1):**
- Gen 0: 17.1 min (50 prompts from scratch)
- Gen 1-4: ~12 min each (40 new prompts)
- Total: 66.2 minutes

---

## Pattern 4: Full Production (4-6 hours)

**Purpose:** Complete research-grade evolutionary run

```bash
python scripts/run_experiment.py \
  --era phylo-2 \
  --population 50 \
  --generations 20 \
  --model claude \
  --token-eval \
  --single-tag
```

**Real Timing (phylo-2):**
- Gen 0: 17.7 min
- Gen 1-22: ~11.3 min each
- Total: 264.9 minutes (4.4 hours)

**Key for Paper 2:** Use `--single-tag` for phylogenetic tracking

---

## Pattern 5: Large Scale Research (8-12 hours)

**Purpose:** Maximum diversity, extended evolution

```bash
python scripts/run_experiment.py \
  --era production-1 \
  --population 100 \
  --generations 25 \
  --model claude \
  --token-eval \
  --single-tag \
  --no-convergence-stop
```

**Estimated:** ~10 hours for 100 prompts × 25 generations

---

## Pattern 6: Model Comparison

**Purpose:** Compare Claude, OpenAI, Gemini as compression executors

```bash
# Run 1: Claude
python scripts/run_experiment.py --era compare-claude \
  --population 50 --generations 20 --model claude --token-eval

# Run 2: OpenAI
python scripts/run_experiment.py --era compare-openai \
  --population 50 --generations 20 --model openai --token-eval

# Run 3: Gemini
python scripts/run_experiment.py --era compare-gemini \
  --population 50 --generations 20 --model gemini --token-eval
```

**Analysis:**
```sql
SELECT era, MAX(max_fitness), AVG(mean_fitness)
FROM generation_stats
WHERE era LIKE 'compare-%'
GROUP BY era;
```

---

## Pattern 7: Parameter Sweep

**Purpose:** Optimize GA hyperparameters

```bash
# Baseline
python scripts/run_experiment.py --era sweep-baseline \
  --population 50 --generations 10 \
  --mutation-fraction 0.2 --immigration-fraction 0.08

# Low mutation
python scripts/run_experiment.py --era sweep-lowmut \
  --population 50 --generations 10 \
  --mutation-fraction 0.1

# High mutation
python scripts/run_experiment.py --era sweep-highmut \
  --population 50 --generations 10 \
  --mutation-fraction 0.3
```

---

## Pattern 8: Corpus Testing

**Purpose:** Validate framework on different text domains

```bash
python scripts/run_experiment.py \
  --era corpus-legal-test \
  --population 20 \
  --generations 5 \
  --model claude
```

**Success Criteria:**
- Fitness ≥ 0.50 by Gen 5
- Quality scores ≥ 6.0
- Compression ratios 1.5x-4.0x

---

## Pattern 9: Convergence Testing

**Purpose:** Test convergence detection logic

```bash
# With early stopping
python scripts/run_experiment.py \
  --era converge-test-stop \
  --population 50 \
  --generations 20 \
  --convergence-window 3 \
  --convergence-threshold 0.05

# Without stopping
python scripts/run_experiment.py \
  --era converge-test-continue \
  --population 50 \
  --generations 20 \
  --no-convergence-stop
```

---

## Pattern 10: Background Production (EC2/Server)

**Purpose:** Run long experiments on cloud servers

```bash
# Setup
ssh user@ec2-instance
cd /home/user/genprompt
source venv/bin/activate
source ./set_env.sh

# Run in background
nohup python scripts/run_full_experiment.py \
  --era phylo-server-1 \
  --population 50 \
  --generations 25 \
  --model claude \
  --token-eval \
  --single-tag \
  > tmp/phylo-server-1.log 2>&1 < /dev/null &

# Monitor
tail -f tmp/phylo-server-1.log
ps aux | grep run_full_experiment
```

---

## Time Estimation Formula

```python
def estimate_time_hours(population, generations):
    # Based on phylo-1 and phylo-2 data
    gen0_time = (population / 50) * 17  # minutes
    evolved_time_per_gen = (population / 50) * 11
    total_minutes = gen0_time + (generations * evolved_time_per_gen)
    return total_minutes / 60

# Examples:
estimate_time_hours(50, 5)   # 1.1 hours (matches phylo-1)
estimate_time_hours(50, 23)  # 4.4 hours (matches phylo-2)
estimate_time_hours(100, 25) # 9.6 hours
```

---

## Common Flags Reference

```bash
--population 50              # Prompts per generation
--generations 20             # Max generations
--model claude               # claude, openai, gemini, gemini3
--token-eval                 # Token-based fitness (recommended)
--single-tag                 # For phylogenetic tracking
--elite 0.2                  # Elite fraction (20%)
--mutation-fraction 0.2      # Mutation rate (20%)
--immigration-fraction 0.08  # Immigration on odd gens (8%)
--convergence-window 3       # Gens to check for plateau
--convergence-threshold 0.05 # Max fitness change (5%)
--no-convergence-stop        # Continue past convergence
--prompt-temp 1.0            # Temperature for prompt generation
```

---

## Troubleshooting

### Fitness Not Improving
```bash
# Increase mutation rate
--mutation-fraction 0.3

# Add more immigration
--immigration-fraction 0.15
```

### Experiment Too Long
```sql
-- Check progress
SELECT MAX(generation) FROM generation_stats WHERE era = 'your-era';
```

### All Prompts Failing
```sql
-- Check for text expansion
SELECT COUNT(*) FROM generations 
WHERE era = 'your-era' AND survival_factor = 0;
```

---

## Related Documentation

- **README.md** - Quick start and setup
- **generalized_to_targeted.md** - Domain adaptation
- **fitness_function.md** - Fitness calculation details
- **cmd.md** - Command line reference

---

**Created:** December 2025
**Based on:** Real timing data from phylo-1 and phylo-2 experiments
