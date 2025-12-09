# Visualization Dashboard

Flask-based web dashboard for analyzing genetic algorithm evolution results in real-time.

---

## Quick Start

```bash
cd viz
pip install -r requirements_viz.txt
python app.py
```

Open **http://localhost:8080** in your browser.

---

## Features

### 1. Main Dashboard (`/`)

**Fitness Trajectories**
- Line chart showing mean/max/min fitness over generations
- Visualize convergence patterns and evolutionary progress
- Identify which generations showed significant improvements

**Operator Effectiveness**
- Bar chart showing mutation/crossover/immigration counts per generation
- Track how genetic algorithm dynamics change over time
- See operator distribution (elite preserved, offspring created, immigrants added)

**Diversity Tracking**
- Tag diversity metrics per generation (unique GUIDs by tag type)
- Monitor genetic diversity to detect premature convergence
- Understand how tag variety evolves across generations

---

### 2. Lineage Explorer (`/lineage`)

**Interactive Sankey Diagram**
- Complete prompt lineage visualization from Gen 0 to final generation
- Trace parent-child relationships across all generations
- Color-coded flows by operation type:
  - **Blue** - Initial (Generation 0)
  - **Green** - Mutation
  - **Orange** - Crossover
  - **Purple** - Immigration

**Node Interactions**
- Click any node to see:
  - Full prompt details (all 5 tags)
  - Fitness metrics (fitness, compression ratio, quality score)
  - Parent IDs and generation number
  - Operation type that created this prompt

**Use Cases**
- Identify which Generation 0 prompts had the most successful descendants
- Trace the ancestry of your best-performing prompts
- Understand which operations (mutation/crossover) produced top performers

---

### 3. Phylogenetic Attribution Analysis (`/phylo_attribution`)

**⚠️ Requires Single-Tag Mode**

Run experiments with `--single-tag` flag to enable this analysis:
```bash
python scripts/run_experiment.py --era phylo-1 --population 50 --generations 20 \
    --model claude --single-tag
```

Single-tag mode restricts crossover to swap only one tag at a time, enabling precise attribution of fitness improvements to specific tag changes.

#### Three Analytical Views

**Tag Metrics Table**
- Mean fitness, quality score, and compression ratio for each unique tag variant
- Filter by tag type (role, compression_target, fidelity, constraints, output)
- Sort by fitness to identify high-performing tag texts
- See sample counts to understand which tags appear frequently

**Tag Type Delta Analysis**
- Compares mean fitness improvement when each tag type is mutated
- Answers: "Which tag type drives the most fitness improvement?"
- Bar chart showing average delta fitness by tag type
- Identifies which components of prompts matter most

**Tag Lineage Tracking**
- Trace the evolutionary history of specific high-performing tags
- See parent→child mutations for individual tags
- Understand how successful tag variants emerged over generations

**Use Cases**
- Identify which tag types (role, fidelity, etc.) are most critical for performance
- Find the best-performing text for each tag type to use in production prompts
- Understand tag mutation patterns that lead to fitness improvements

---

### 4. Tag Evolutionary Story (`/tag_story`)

**⚠️ Requires Single-Tag Mode**

Three complementary analyses that tell the complete evolutionary story:

#### Survival Analysis

**Question:** Which Generation 0 tags survived to the final elite population?

- Shows which initial tag variants made it through natural selection
- Tracks tag GUIDs from Gen 0 to final elite prompts
- Identifies "winners" from initial random generation
- **Insight:** Some Gen 0 tags are immediately good enough to survive 20+ generations

#### Breakthrough Moments

**Question:** When fitness jumped significantly, which tags changed?

- Detects fitness breakthroughs (>5% improvement over previous generation)
- Shows which tags were mutated in prompts that caused the breakthrough
- **Insight:** Reveals which tag mutations unlock fitness improvements

#### Elite Enrichment Patterns

**Question:** Which tags are overrepresented in elite vs general population?

- Calculates enrichment ratios: (% in elites) / (% in population)
- High ratio = tag is more common in high performers
- **Insight:** Identifies tag characteristics that correlate with success

**Use Cases**
- Understand what makes prompts successful (not just which prompts are successful)
- Identify early winners (Gen 0 tags that survive long-term)
- Find tag patterns that predict high fitness
- Guide manual prompt engineering based on evolutionary insights

---

## API Endpoints

All endpoints return JSON and support CORS for external analysis tools.

### Era & Generation Data

- `GET /api/eras` - List all experimental eras
  ```json
  [{"era": "test-1", "compression_model": "claude", ...}]
  ```

- `GET /api/generations/<era>` - Generation statistics for specific era
  ```json
  [{"generation": 0, "mean_fitness": 0.68, "max_fitness": 0.76, ...}]
  ```

- `GET /api/prompts/<era>?generation=N` - Prompts for era (optional generation filter)
  ```json
  [{"prompt_id": "uuid", "fitness": 0.82, "role": {...}, ...}]
  ```

### Visualization Data

- `GET /api/diversity/<era>` - Tag diversity metrics per generation
  ```json
  [{"generation": 0, "unique_role": 50, "unique_fidelity": 48, ...}]
  ```

- `GET /api/tree/<era>` - Complete lineage data for Sankey diagram
  ```json
  {
    "nodes": [{"name": "Gen 0-1", "generation": 0, ...}],
    "links": [{"source": 0, "target": 1, "value": 1, ...}]
  }
  ```

### Single-Tag Analysis (Requires --single-tag eras)

- `GET /api/phylo/tag_metrics/<era>` - Tag-level fitness attribution
- `GET /api/phylo/tag_deltas/<era>` - Tag type delta analysis
- `GET /api/phylo/tag_lineage/<era>` - Tag ancestry tracing
- `GET /api/phylo/tag_survival/<era>` - Gen 0 → Elite survival
- `GET /api/phylo/tag_breakthrough/<era>` - Breakthrough moment analysis
- `GET /api/phylo/tag_enrichment/<era>` - Elite vs population enrichment

---

## Requirements

**Python Packages:**
- Flask (`pip install flask`)
- Couchbase connection (uses same credentials as main framework)
- Python 3.13+

**Browser:**
- Modern browser with JavaScript enabled
- Plotly.js (loaded via CDN, no local install needed)

**Database:**
- Couchbase cluster with completed experiments
- Collections: `generations`, `generation_stats`, `eras`

---

## Configuration

The dashboard uses the same Couchbase credentials as the main framework:

**Environment Variables** (from `.env`):
```env
COUCHBASE_CONNECTION_STRING=couchbases://your-cluster.cloud.couchbase.com
COUCHBASE_USERNAME=your_username
COUCHBASE_PASSWORD=your_password
COUCHBASE_BUCKET=genetic
COUCHBASE_SCOPE=g_scope
```

Make sure to run `source ./set_env.sh` before starting the dashboard.

---

## Troubleshooting

### "No eras found"

**Cause:** No experiments have been run yet
**Fix:** Run an experiment first:
```bash
python scripts/run_experiment.py --era test-1 --population 5 --generations 5
```

### Connection Errors

**Cause:** Couchbase credentials not loaded
**Fix:** Load environment variables:
```bash
source ./set_env.sh
cd viz
python app.py
```

### Empty Charts / No Data

**Cause:** The `generation_stats` collection has no data
**Fix:** Ensure your experiment completed successfully and check Couchbase:
```sql
SELECT COUNT(*) FROM `genetic`.`g_scope`.`generation_stats`;
```

### Phylo Attribution Shows "No data"

**Cause:** Era was not run with `--single-tag` flag
**Fix:** Phylogenetic attribution requires single-tag mode:
```bash
python scripts/run_experiment.py --era phylo-test --population 20 --generations 10 \
    --model claude --single-tag
```

### Port 8080 Already in Use

**Fix:** Use a different port:
```python
# Edit viz/app.py line ~1280
app.run(host='0.0.0.0', port=8081)  # Change port
```

---

## Development

### Adding New Visualizations

1. Create new endpoint in `app.py`:
```python
@app.route('/api/my_analysis/<era>')
def my_analysis(era):
    # Query Couchbase
    # Process data
    return jsonify(results)
```

2. Create HTML template in `templates/my_page.html`
3. Add JavaScript chart in `static/js/my_chart.js`
4. Link from main dashboard

### Testing Locally

```bash
# Run with Flask debug mode
export FLASK_ENV=development
python app.py
```

---

## Architecture

**Tech Stack:**
- **Backend:** Flask (Python)
- **Frontend:** HTML + vanilla JavaScript
- **Charts:** Plotly.js
- **Database:** Couchbase (via Python SDK)

**Design Philosophy:**
- No build step (vanilla JS, no webpack/babel)
- CDN-loaded libraries (no npm)
- Server-side rendering for initial page load
- Client-side interactivity for charts

This makes the dashboard easy to modify and deploy without complex tooling.

---

## Related Documentation

- **Main README:** `../README.md` - Framework overview
- **Data Import:** `../project_docs/DATA_IMPORT.md` - Corpus preparation
- **Execution Patterns:** `../project_docs/runme.md` - Running experiments
- **Fitness Function:** `../project_docs/fitness_function.md` - How fitness is calculated

---

**Created:** December 2025
**Purpose:** Real-time analysis and visualization of genetic algorithm evolution
**Status:** Production ready
