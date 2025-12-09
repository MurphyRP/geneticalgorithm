# Fitness Function: Model-as-Judge Architecture

**Purpose:** This document provides a detailed explanation of the fitness evaluation system used in the genetic algorithm framework. The fitness function is the selection mechanism that determines which prompts survive and reproduce across generations.

**Location:** `src/fitness_evaluator.py`

---

## Overview

The framework uses a **model-as-judge** architecture where multiple LLMs evaluate compression quality. This provides more robust, unbiased quality assessments compared to single-model judging or rule-based metrics.

**Key Design Principles:**
1. **Multi-model judging** - All three models (OpenAI, Claude, Gemini) judge each compression
2. **Deterministic scoring** - Judges use temperature=0 for consistent evaluations
3. **Structured rubric** - Three-dimensional scoring system (0-10 scale)
4. **Survival filter** - Binary gate eliminates prompts that expand text
5. **Weighted fitness** - Quality prioritized (75%) over compression ratio (25%)

---

## The Three-Stage Pipeline

### Stage 1: Compression Execution

**Function:** `compress_text(prompt_object, paragraph_text, compression_model)`

**Process:**
1. Build full compression prompt from 5 tags:
   ```
   {role.text}

   {compression_target.text}

   {fidelity.text}

   {constraints.text}

   {output.text}

   Original Text:
   {paragraph_text}
   ```

2. Execute compression with specified model (claude, openai, gemini, gemini3)

3. Return compressed text (empty string if failure)

**Error Handling:**
- Compression failures return empty string (not crash)
- Empty string triggers survival_factor=0 downstream
- Prompt receives fitness=0 and is eliminated from evolution

**Model Selection:**
- ONE model per era (consistent across all prompts)
- Specified in era configuration as `compression_model`
- Example: All prompts in "phylo-2" use Claude for compression

---

### Stage 2: Multi-Model Quality Judging

**Function:** `judge_compression(original_text, compressed_text, judge_model)`

**Judge Prompt Structure:**

```
You are evaluating a text compression. Score the compressed text on three dimensions:

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
1 point: Readable but awkward or has minor grammar issues
0 points: Choppy, ungrammatical, or hard to read

IMPORTANT: Respond with ONLY a JSON object in this exact format:
{
  "faithfulness": <0-5>,
  "clarity": <0-3>,
  "readability": <0-2>,
  "score": <sum of above, 0-10>,
  "comments": "<brief 1-2 sentence explanation>"
}
```

**Scoring Dimensions:**

| Dimension | Range | Weight | Purpose |
|-----------|-------|--------|---------|
| Faithfulness | 0-5 | 50% | Core content preservation |
| Clarity | 0-3 | 30% | Understandability |
| Readability | 0-2 | 20% | Grammar and flow |
| **Total** | **0-10** | **100%** | **Overall quality** |

**Calibration Examples:**

The rubric includes calibration examples for each score level to reduce inter-model variance. This helps ensure:
- OpenAI, Claude, and Gemini use similar standards
- Scores are comparable across judges
- Consistent evaluation over time

**Judge Execution:**
- **Temperature:** 0 (deterministic scoring)
- **All three models judge EVERY compression**
- **Parallel judging:** Independent evaluations (no consensus)
- **JSON parsing:** Handles Claude's markdown code blocks (```json ... ```)

**Example Judge Response:**
```json
{
  "faithfulness": 4,
  "clarity": 3,
  "readability": 2,
  "score": 9,
  "comments": "All key concepts preserved with excellent clarity. Minor grammatical awkwardness in one phrase."
}
```

**Why Multi-Model Judging?**

1. **Reduces Model Bias:**
   - OpenAI may favor certain compression styles
   - Claude may prefer different structures
   - Gemini provides third perspective
   - Average reduces individual bias

2. **More Robust Signal:**
   - Outlier scores (one model significantly different) are averaged out
   - Consensus emerges naturally from three independent evaluations
   - Reduces noise in fitness signal

3. **Research Validity:**
   - Can analyze inter-model agreement
   - Can identify which models are harshest/most lenient
   - Can measure scoring consistency over generations

**Error Handling:**
- Judge failures exclude that model from averaging
- Remaining judges used (e.g., if Claude fails, average OpenAI + Gemini)
- If ALL judges fail, fitness=0 (prompt eliminated)
- Tracks duration for performance monitoring

---

### Stage 3: Fitness Calculation

**Function:** `calculate_fitness(original_text, compressed_text, quality_scores, use_token_metric)`

**Framework v2 Weighted Formula:**

```python
# Normalize quality score (0-10 scale → 0.0-1.0)
quality_norm = quality_score_avg / 10.0

# Normalize compression ratio (cap at 20x)
compression_norm = min(compression_ratio / 20.0, 1.0)

# Weighted combination (75% quality, 25% compression)
raw_fitness = (0.75 * quality_norm) + (0.25 * compression_norm)

# Apply survival filter
fitness = raw_fitness * survival_factor
```

**Components:**

1. **Compression Ratio:**
   - Word-based (default): `original_words / compressed_words`
   - Token-based (optional): `original_tokens / compressed_tokens`
   - Choice specified via `use_token_metric` flag
   - **Both metrics always computed and stored** (for analysis)

2. **Quality Score Average:**
   - Mean of valid judge scores (0-10)
   - Example: OpenAI=8, Claude=7, Gemini=9 → avg=8.0
   - Normalized to 0.0-1.0 range for fitness formula

3. **Survival Factor:**
   - Binary gate (0 or 1)
   - `0` if text expanded (compressed_words >= original_words)
   - `1` if text compressed (compressed_words < original_words)
   - **Always word-based** (even with token fitness metric)

4. **Normalization:**
   - Compression capped at 20x (prevents runaway scores)
   - Quality already on 0-10 scale (divide by 10 → 0.0-1.0)
   - Final fitness always in 0.0-1.0 range

**Weighting Rationale:**

**75% Quality / 25% Compression:**
- Prioritizes content preservation over aggressive compression
- Prevents prompts from "cheating" with excessive deletion
- Aligns with practical use case (lossy compression acceptable if quality high)
- Encourages intelligent summarization over naive truncation

**Example Fitness Calculations:**

| Scenario | Quality | Ratio | Quality Norm | Ratio Norm | Raw Fitness | Survival | Final Fitness |
|----------|---------|-------|--------------|------------|-------------|----------|---------------|
| Excellent compression | 9.0 | 3.5x | 0.90 | 0.175 | 0.719 | 1 | **0.719** |
| High quality, low compression | 8.5 | 1.8x | 0.85 | 0.09 | 0.660 | 1 | **0.660** |
| Aggressive but poor quality | 5.0 | 8.0x | 0.50 | 0.40 | 0.475 | 1 | **0.475** |
| Text expanded | 9.5 | 0.8x | 0.95 | 0.04 | 0.723 | 0 | **0.000** |
| Compression failed | 0.0 | 0.0x | 0.00 | 0.00 | 0.000 | 0 | **0.000** |

**Edge Cases:**

1. **Empty compressed text:**
   - compressed_words = 0
   - compression_ratio = 0
   - survival_factor = 0
   - fitness = 0

2. **All judges fail:**
   - quality_scores = []
   - quality_score_avg = 0
   - fitness = 0 (even if compression successful)

3. **Text expansion:**
   - compressed_words >= original_words
   - survival_factor = 0
   - fitness = 0 (regardless of quality)

4. **Perfect 20x compression:**
   - compression_norm capped at 1.0
   - Prevents infinite fitness scores
   - 20x chosen as realistic upper bound

---

## Complete Evaluation Pipeline

**Function:** `evaluate_prompt_fitness(prompt_object, paragraph_text, compression_model, judge_models, use_token_metric)`

**Orchestrates full pipeline:**

```
1. Compress text
   ├─ Build prompt from 5 tags
   ├─ Execute with compression_model
   └─ Return compressed_text

2. Judge compression (3 models)
   ├─ Judge with OpenAI (temp=0)
   ├─ Judge with Claude (temp=0)
   ├─ Judge with Gemini (temp=0)
   └─ Collect scores + details

3. Calculate fitness
   ├─ Count words/tokens
   ├─ Compute compression ratios
   ├─ Average quality scores
   ├─ Apply survival filter
   └─ Return fitness (0.0-1.0)

4. Package results
   └─ Return complete evaluation dict
```

**Output Structure:**

```python
{
    # Compression results
    "original_text": str,
    "compressed_text": str,

    # Word metrics
    "original_words": int,
    "compressed_words": int,
    "compression_ratio": float,  # Used for fitness (word or token)

    # Token metrics (always computed)
    "original_tokens": int,
    "compressed_tokens": int,
    "token_compression_ratio": float,

    # Quality assessment
    "quality_scores": {
        "openai": 8.5,
        "claude": 7.2,
        "gemini": 8.8
    },
    "quality_score_avg": 8.17,

    # Fitness components
    "survival_factor": 1,
    "fitness": 0.6543,

    # Full judge details (for debugging/analysis)
    "judge_details": {
        "openai": {
            "faithfulness": 4,
            "clarity": 3,
            "readability": 2,
            "score": 9,
            "comments": "...",
            "judge_model": "openai",
            "judge_duration_ms": 1234
        },
        "claude": {...},
        "gemini": {...}
    }
}
```

---

## Token vs Word Metrics

**Both metrics always computed and stored.** The `use_token_metric` flag controls which is used for fitness calculation.

### Word-Based Fitness (Default)

**Advantages:**
- Faster computation (simple whitespace split)
- Human-intuitive (people think in words)
- Sufficient precision for GA selection (<5% difference vs tokens)

**When to Use:**
- Quick test runs (5-10 generations)
- Initial framework validation
- Cost-sensitive experiments

### Token-Based Fitness (Optional)

**Advantages:**
- More precise (matches LLM tokenization)
- Reflects actual API costs/limits
- Closer to "true" compression ratio

**When to Use:**
- Production experiments (20+ generations)
- Research papers (more rigorous)
- Token cost optimization studies

**Relationship:**
- Token count ≥ Word count (English text ~1.3 tokens per word)
- Token ratio typically slightly lower than word ratio
- Selection gradient similar (GA works with both)

**Example Comparison:**

| Text | Words | Tokens | Word Ratio | Token Ratio | Difference |
|------|-------|--------|------------|-------------|------------|
| Original | 150 | 195 | - | - | - |
| Compressed | 50 | 68 | 3.0x | 2.87x | -4.3% |

**Survival Factor:**
- Always word-based (even with token fitness)
- Simplifies implementation
- Word expansion rare when token expansion occurs

---

## Model-as-Judge vs Alternatives

### Why Model-as-Judge?

**Compared to BLEU/ROUGE:**
- Captures semantic similarity (not just n-gram overlap)
- Evaluates readability and coherence
- Handles paraphrasing and restructuring
- More aligned with human quality perception

**Compared to Human Evaluation:**
- Scalable (3 judges per prompt, ~40 prompts per generation)
- Consistent (deterministic with temp=0)
- Fast (~2-3 seconds per judge)
- Cost-effective (~$0.01 per evaluation)

**Compared to Single-Model Judging:**
- Reduces model-specific bias
- More robust signal (outliers averaged)
- Research validity (cross-model agreement)

### Limitations

1. **Model Alignment:**
   - Judges may favor their own compression style
   - Cross-model evaluation mitigates this

2. **Rubric Adherence:**
   - Models may interpret rubric differently
   - Calibration examples reduce variance

3. **Score Inflation:**
   - Models may be lenient judges
   - Relative ranking matters more than absolute scores

4. **Cost:**
   - 3 judge calls per compression (~$0.03 total)
   - Generation: ~40 compressions = ~$1.20 in judging
   - Per era (20 gens): ~$24 in judging costs

### Research Validation

**Inter-Judge Agreement Analysis:**
- Calculate correlation between judge pairs (OpenAI-Claude, OpenAI-Gemini, Claude-Gemini)
- High correlation (r > 0.7) indicates consistent rubric interpretation
- Low correlation suggests model-specific biases

**Score Distribution Analysis:**
- Track mean/std of scores per judge over generations
- Identify which models are harshest/most lenient
- Detect score drift over time

**Ablation Studies:**
- Compare single-judge vs multi-judge fitness gradients
- Test if GA converges to same solutions with different judge combinations
- Measure impact of judge temperature (0 vs 0.5 vs 1.0)

---

## Integration with GA Framework

### Fitness Role in Evolution

**Selection (Elite):**
- Top 20% by fitness preserved unchanged
- Example: Population 50 → 10 elite prompts
- Elite skip re-evaluation (fitness already known)

**Selection (Crossover Parents):**
- Parent selection probability proportional to fitness
- Higher fitness → more likely to reproduce
- Roulette wheel selection algorithm

**Selection (Mutation Parents):**
- Same fitness-proportional selection
- Mutated offspring compete with original

**Immigration:**
- Fresh prompts start with fitness=None
- Must be evaluated before next generation
- Inject genetic diversity on odd generations

### Fitness Tracking

**Per-Prompt:**
- Stored in `generations` collection
- Fields: `fitness`, `compression_ratio`, `quality_score_avg`, `quality_scores`, `survival_factor`
- Enables lineage analysis and phylogenetic trees

**Per-Generation:**
- Stored in `generation_stats` collection
- Fields: `mean_fitness`, `std_fitness`, `median_fitness`, `min_fitness`, `max_fitness`
- Enables gradient visualization and convergence detection

**Per-Era:**
- Stored in `eras` collection
- Fields: `final_mean_fitness`, `final_max_fitness`, `total_generations`
- Enables cross-era comparisons

---

## Performance Considerations

### API Call Efficiency

**Per Prompt Evaluation:**
- 1 compression call (compression_model)
- 3 judge calls (openai, claude, gemini)
- **Total: 4 API calls per prompt**

**Per Generation:**
- Elite: 10 prompts × 0 calls = 0 (skip re-evaluation)
- New prompts: 40 prompts × 4 calls = 160
- **Total: ~160 API calls per generation**

**Per Era (20 generations):**
- Gen 0: 50 prompts × 4 = 200 calls
- Gen 1-20: 20 × 160 = 3,200 calls
- **Total: ~3,400 API calls per era**

### Cost Estimation

**API Costs (approximate):**
- Compression: $0.02 per call
- Judge: $0.01 per call
- **Total per prompt: $0.02 + (3 × $0.01) = $0.05**

**Per Generation:**
- 40 new prompts × $0.05 = $2.00

**Per Era (20 generations):**
- Gen 0: 50 × $0.05 = $2.50
- Gen 1-20: 20 × $2.00 = $40.00
- **Total: ~$42.50 per era**

### Runtime Performance

**Typical Timings:**
- Compression: 3-5 seconds
- Judge (each): 2-3 seconds
- **Total per prompt: ~12-15 seconds**

**Per Generation:**
- 40 prompts × 12-15s = 480-600 seconds (8-10 minutes)
- Plus overhead (DB writes, stats calculation): ~2 minutes
- **Total: ~10-12 minutes per generation**

**Per Era (20 generations):**
- Gen 0: ~15 minutes (50 prompts)
- Gen 1-20: 20 × 12 = 240 minutes (4 hours)
- **Total: ~4-5 hours per era**

### Optimization Opportunities

1. **Parallel Judging:**
   - Current: Sequential (OpenAI → Claude → Gemini)
   - Potential: Parallel (all 3 simultaneously)
   - Savings: ~4-6 seconds per prompt (~3 minutes per generation)

2. **Batch Compression:**
   - Current: One prompt at a time
   - Potential: Batch API requests (if supported)
   - Savings: Reduces API overhead

3. **Caching:**
   - Elite prompts skip re-evaluation (already implemented)
   - Could cache identical prompts across generations (rare occurrence)

4. **Judge Subset:**
   - Current: 3 judges per compression
   - Alternative: 2 judges (OpenAI + Claude)
   - Savings: 33% reduction in judge calls (~$0.33 per generation)
   - Trade-off: Less robust signal

---

## Configuration and Tuning

### Fitness Formula Parameters

**Current (Framework v2):**
```python
quality_weight = 0.75
compression_weight = 0.25
compression_cap = 20.0
```

**Alternative Configurations:**

| Profile | Quality % | Compression % | Compression Cap | Use Case |
|---------|-----------|---------------|-----------------|----------|
| Quality-First | 90 | 10 | 10.0 | Maximize faithfulness |
| Balanced | 75 | 25 | 20.0 | **Current default** |
| Aggressive | 60 | 40 | 30.0 | Maximize compression |
| Equal | 50 | 50 | 20.0 | Research baseline |

**To Change:**
Modify `calculate_fitness()` in `src/fitness_evaluator.py`:
```python
raw_fitness = (0.75 * quality_norm) + (0.25 * compression_norm)
                ^^^^                   ^^^^
              quality_weight       compression_weight
```

### Judge Rubric Tuning

**Current Weights:**
- Faithfulness: 50% (0-5 points)
- Clarity: 30% (0-3 points)
- Readability: 20% (0-2 points)

**Alternative Rubrics:**

1. **Faithfulness-Heavy:**
   - Faithfulness: 0-7 (70%)
   - Clarity: 0-2 (20%)
   - Readability: 0-1 (10%)

2. **Balanced:**
   - All three: 0-3.33 (33% each)

3. **Compression-Specific:**
   - Faithfulness: 0-6 (60%)
   - Conciseness: 0-3 (30%)
   - Readability: 0-1 (10%)

**To Change:**
Modify `judge_compression()` in `src/fitness_evaluator.py` (lines 208-248)

### Judge Model Selection

**Current: All Three Models**
```python
judge_models = ["openai", "claude", "gemini"]
```

**Alternatives:**

1. **Two Models (Cost Reduction):**
   ```python
   judge_models = ["openai", "claude"]  # Skip Gemini
   ```

2. **Single Model (Fast Iteration):**
   ```python
   judge_models = ["claude"]  # Claude only
   ```

3. **Custom Judges:**
   ```python
   judge_models = ["claude", "gemini3"]  # Test newer models
   ```

**To Change:**
Pass `judge_models` parameter to `evaluate_prompt_fitness()` in evolution loop

---

## Debugging and Troubleshooting

### Common Issues

**1. All Judges Fail:**
```
Error: All judges failed - fitness will be 0
```
**Causes:**
- API keys invalid/expired
- Rate limits exceeded
- Network connectivity issues

**Solution:**
- Check `.env` file for valid API keys
- Add retry logic with exponential backoff
- Verify network connection

**2. JSON Parse Errors:**
```
Error: Expecting property name enclosed in double quotes
```
**Causes:**
- Judge returned invalid JSON
- Judge included markdown code blocks

**Solution:**
- Already handled: Strips ```json and ``` from response
- If persists, check judge prompt for JSON format instruction

**3. Fitness Always 0:**
```
Warning: Fitness = 0.0 for all prompts
```
**Causes:**
- All compressions expanding text (survival_factor=0)
- All judges returning score=0
- Quality scores averaging to 0

**Solution:**
- Check compressed text samples (are they actually compressed?)
- Review judge comments (why low scores?)
- Verify compression_model is working correctly

**4. Fitness Not Converging:**
```
Generation 20: Mean fitness still improving significantly
```
**Causes:**
- Population too small (insufficient exploration)
- Mutation rate too high (destroying good solutions)
- Immigration too frequent (disrupting convergence)

**Solution:**
- Increase population size (50 → 100)
- Reduce mutation fraction (0.2 → 0.15)
- Reduce immigration fraction (0.08 → 0.05)

### Diagnostic Queries

**Check judge score distributions:**
```sql
SELECT
  generation,
  AVG(quality_scores.openai) as openai_avg,
  AVG(quality_scores.claude) as claude_avg,
  AVG(quality_scores.gemini) as gemini_avg
FROM generations
WHERE era = 'phylo-2'
GROUP BY generation
ORDER BY generation;
```

**Find prompts with low quality but high compression:**
```sql
SELECT
  prompt_id,
  generation,
  fitness,
  quality_score_avg,
  compression_ratio
FROM generations
WHERE era = 'phylo-2'
  AND quality_score_avg < 6.0
  AND compression_ratio > 3.0
ORDER BY fitness DESC;
```

**Identify text expansions:**
```sql
SELECT
  generation,
  COUNT(*) as expansion_count
FROM generations
WHERE era = 'phylo-2'
  AND survival_factor = 0
GROUP BY generation
ORDER BY generation;
```

---

## Future Enhancements

### 1. Dynamic Weighting

Adapt quality/compression weights based on generation:
- Early generations: Higher compression weight (explore space)
- Later generations: Higher quality weight (fine-tune)

```python
# Adaptive weighting
generation_progress = current_gen / max_generations
quality_weight = 0.6 + (0.2 * generation_progress)  # 0.6 → 0.8
compression_weight = 1.0 - quality_weight           # 0.4 → 0.2
```

### 2. Multi-Objective Optimization

Track Pareto frontier of quality vs compression:
- Don't collapse to single fitness score
- Maintain population diversity across trade-off curve
- Select from Pareto set based on user preference

### 3. Learned Judge Weights

Train weights for each judge based on human evaluation:
- Collect human scores on sample compressions
- Fit linear model: `human_score = w1*openai + w2*claude + w3*gemini`
- Use learned weights instead of simple average

### 4. Context-Aware Judging

Provide judges with domain context:
- "This is medical text"
- "This is legal text"
- Adjust expectations for domain-specific terminology

### 5. Ensemble Compression Models

Test multiple compression models per prompt:
- Claude, OpenAI, Gemini all compress same text
- Take best compression by quality score
- Judge best compression only

---

## Related Documentation

- **Implementation:** `src/fitness_evaluator.py`
- **Architecture:** `project_docs/architecture_overview.md`
- **GA Framework:** `project_docs/ga_implementation_plan_final.md`
- **Statistics:** `project_docs/gen_stats.md`
- **Era Analysis:** `project_docs/GA_Era_Analysis_Complete.md`

**File:** `project_docs/fitness_function.md`
**Created:** 2025-12-02
**Purpose:** Detailed reference for model-as-judge fitness evaluation architecture
