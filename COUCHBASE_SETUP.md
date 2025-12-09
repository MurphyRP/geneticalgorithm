# Couchbase Capella Setup Guide

Complete guide to setting up Couchbase Capella for the genetic prompt evolution framework.

---

## Quick Start (Automated Setup)

**If you already have a Couchbase Capella cluster with credentials configured:**

```bash
# Load environment variables
source ./set_env.sh

# Create database structure automatically
./scripts/setup_couchbase.sh
```

This script creates:
- Bucket: `genetic`
- Scope: `g_scope`
- Collections: `unstructured`, `generations`, `generation_stats`, `eras`

**Options:**
- `--verify` - Check existing structure
- `--dry-run` - Preview what would be created
- `--help` - Show all options

For first-time setup or manual configuration, continue with the detailed guide below.

---

## Overview

This framework uses **Couchbase Capella** (cloud-hosted Couchbase) to store:
- Your text corpus for compression experiments (`unstructured` collection)
- All evolved prompts with evaluation results (`generations` collection)
- Generation statistics (`generation_stats` collection)
- Experiment configurations (`eras` collection)

**Why Couchbase?**
- Native JSON document storage (perfect for prompt structures)
- SQL++ query language (familiar to SQL users)
- Excellent for phylogenetic analysis (recursive queries)
- Free tier available for getting started

---

## Step 1: Create Couchbase Capella Account

### 1.1 Sign Up (5 minutes)

1. Go to [https://cloud.couchbase.com/sign-up](https://cloud.couchbase.com/sign-up)
2. Click **"Start Free Trial"** or **"Sign Up"**
3. Choose sign-up method:
   - Email/password
   - Google account
   - GitHub account
4. Verify your email address
5. Complete profile information

**Free Tier:**
- 50GB storage
- 3 nodes
- No credit card required initially
- Perfect for this framework

### 1.2 Create Organization

After sign-up, you'll be prompted to:
1. **Organization name**: Choose any name (e.g., "Genetic Prompts", "Research Lab")
2. **Cloud provider**: AWS, Azure, or GCP (AWS recommended for lowest latency)
3. **Region**: Choose closest to your location

---

## Step 2: Create Database Cluster

### 2.1 Create New Cluster

1. From Capella dashboard, click **"Create Cluster"**
2. Choose deployment:
   - **Free Trial/Developer** - Use this for framework testing
   - **Production** - Only if you need high availability
3. Configure cluster:
   - **Cluster name**: `genetic-evolution` (or any name you prefer)
   - **Cloud provider**: AWS (recommended)
   - **Region**: Choose closest region
   - **Availability Zone**: Single (for free tier)

### 2.2 Cluster Configuration

**For Free Tier:**
```
Cluster Name: genetic-evolution
Services: Data (required), Query (required), Index (required)
Node Count: 1
Memory: 2GB RAM (free tier)
Storage: 50GB
```

**For Production (if needed):**
```
Node Count: 3+ (high availability)
Memory: 8GB+ per node
Storage: 100GB+
```

Click **"Create"** - Cluster creation takes 5-10 minutes.

### 2.3 Wait for Cluster Ready

Watch the status indicator:
- ⏳ **Creating** - Cluster is being provisioned
- ✅ **Healthy** - Cluster is ready to use

---

## Step 3: Create Database User

### 3.1 Access Control

1. From cluster page, click **"Settings"** → **"Database Access"**
2. Click **"Create Database Credentials"**
3. Configure user:
   - **Username**: `genetic_admin` (or your preference)
   - **Password**: Choose a strong password (save this!)
   - **Bucket Access**: Select "All Buckets" or specific bucket later
   - **Permissions**: Read/Write

**Save these credentials immediately!**
```
Username: genetic_admin
Password: [your password]
```

You'll need these for the `.env` file.

---

## Step 4: Create Bucket and Collections

### 4.1 Create Bucket

1. From cluster page, click **"Data Tools"** → **"Buckets"**
2. Click **"Create Bucket"**
3. Configure bucket:
   - **Bucket name**: `genetic` (must match framework config)
   - **Memory quota**: 512MB (minimum) or 1GB (recommended)
   - **Bucket type**: Couchbase
   - **Replicas**: 0 (free tier) or 1+ (production)
   - **Flush**: Disabled (recommended)
4. Click **"Create"**

### 4.2 Create Scope

Scopes organize collections within a bucket.

1. Click on `genetic` bucket
2. Go to **"Scopes & Collections"** tab
3. Click **"Add Scope"**
4. Configure scope:
   - **Scope name**: `g_scope` (must match framework config)
5. Click **"Save"**

### 4.3 Create Collections

Collections store different types of documents.

**Required Collections:**

1. **unstructured** - Corpus text chunks
   - Click **"Add Collection"** in `g_scope`
   - Name: `unstructured`
   - Click **"Save"**

2. **generations** - All evolved prompts
   - Click **"Add Collection"** in `g_scope`
   - Name: `generations`
   - Click **"Save"**

3. **generation_stats** - Summary statistics
   - Click **"Add Collection"** in `g_scope`
   - Name: `generation_stats`
   - Click **"Save"**

4. **eras** - Experiment configurations
   - Click **"Add Collection"** in `g_scope`
   - Name: `eras`
   - Click **"Save"**

**Final Structure:**
```
genetic (bucket)
└── g_scope (scope)
    ├── unstructured (collection)
    ├── generations (collection)
    ├── generation_stats (collection)
    └── eras (collection)
```

---

## Step 5: Get Connection String

### 5.1 Find Connection Details

1. From cluster page, click **"Connect"**
2. You'll see connection information:
   - **Connection string**: `couchbases://cb.xxxxxx.cloud.couchbase.com`
   - **SDK examples**: Python, Node.js, Java, etc.

**Your connection string format:**
```
couchbases://cb.[cluster-id].cloud.couchbase.com
```

**Save this!** You'll need it for `.env` configuration.

### 5.2 Allowed IP Addresses (Important!)

Capella restricts access by IP address for security.

1. Go to **"Settings"** → **"Allowed IP Addresses"**
2. Click **"Add Allowed IP"**
3. Options:
   - **Your current IP**: Click "Add My IP" (for development)
   - **Specific IP**: Enter IP address
   - **CIDR range**: For broader access (e.g., `0.0.0.0/0` for any IP - NOT recommended for production)
4. Click **"Add"**

**Development tip:** If your IP changes frequently (home internet), use:
- VPN with static IP
- Or temporarily allow broad range for testing (then restrict later)

---

## Step 6: Configure Framework

### 6.1 Create .env File

In your project root, create `.env`:

```bash
# Copy example file
cp .env.example .env

# Edit with your actual values
nano .env  # or use your preferred editor
```

### 6.2 Add Couchbase Credentials

Update `.env` with values from Steps 3 and 5:

```env
# Couchbase Capella Configuration
COUCHBASE_CONNECTION_STRING=couchbases://cb.xxxxxx.cloud.couchbase.com
COUCHBASE_USERNAME=genetic_admin
COUCHBASE_PASSWORD=your_password_here
COUCHBASE_BUCKET=genetic
COUCHBASE_SCOPE=g_scope

# LLM API Keys (add these separately)
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
GOOGLE_API_KEY=your-google-api-key-here
```

**Replace:**
- `cb.xxxxxx.cloud.couchbase.com` with your actual connection string
- `your_password_here` with your database user password

### 6.3 Load Environment Variables

```bash
source ./set_env.sh
```

This exports all `.env` variables to your shell session.

---

## Step 7: Verify Connection

### 7.1 Test Connection

Run this Python test to verify everything works:

```python
from src.couchbase_client import CouchbaseClient

with CouchbaseClient() as cb:
    print("✓ Connected to Couchbase Capella!")
    print(f"✓ Bucket: {cb.bucket_name}")
    print(f"✓ Scope: {cb.scope_name}")
```

**Expected output:**
```
✓ Connected to Couchbase Capella!
✓ Bucket: genetic
✓ Scope: g_scope
```

### 7.2 Test Collection Access

```python
from src.couchbase_client import CouchbaseClient

with CouchbaseClient() as cb:
    # Test query on each collection
    query = f"""
        SELECT COUNT(*) as count
        FROM `{cb.bucket_name}`.`{cb.scope_name}`.`unstructured`
    """
    result = list(cb.cluster.query(query))
    print(f"✓ unstructured collection accessible (currently {result[0]['count']} documents)")
```

---

## Step 8: Load Initial Data

Now that Couchbase is configured, load your text corpus:

### 8.1 Prepare Corpus

See [`DATA_IMPORT.md`](project_docs/DATA_IMPORT.md) for complete corpus preparation guide.

**Quick start:**
```bash
python scripts/populate_corpus.py \
  --domain mixed \
  --dir /path/to/your/documents/ \
  --target-words 600
```

### 8.2 Verify Data Loaded

```python
from src.couchbase_client import CouchbaseClient

with CouchbaseClient() as cb:
    query = f"""
        SELECT COUNT(*) as count
        FROM `{cb.bucket_name}`.`{cb.scope_name}`.`unstructured`
    """
    result = list(cb.cluster.query(query))
    print(f"Corpus size: {result[0]['count']} text chunks")
```

**Expected:** At least 100-200 chunks for meaningful experiments.

---

## Understanding the Data Model

### Collection Purposes

#### 1. `unstructured` - Text Corpus
**Purpose:** Stores your text chunks for compression evaluation

**Document structure:**
```json
{
  "chunk_id": "uuid-xxxx",
  "text": "The actual text content here...",
  "word_count": 623,
  "source_file": "article.pdf",
  "source_type": "pdf",
  "domain": "medical",
  "suitable_for_compression_testing": true,
  "created_at": "2025-01-15T10:30:00Z"
}
```

**Query examples:**
```sql
-- Get random suitable chunk
SELECT * FROM `genetic`.`g_scope`.`unstructured`
WHERE suitable_for_compression_testing = true
AND word_count BETWEEN 550 AND 650
ORDER BY RANDOM()
LIMIT 1;

-- Count by domain
SELECT domain, COUNT(*) as count
FROM `genetic`.`g_scope`.`unstructured`
GROUP BY domain;
```

#### 2. `generations` - All Evolved Prompts
**Purpose:** Stores every prompt from every generation with results

**Document structure:**
```json
{
  "prompt_id": "uuid-xxxx",
  "era": "test-1",
  "generation": 5,
  "type": "mutation",
  "parents": ["parent-uuid-1"],
  "model_used": "claude",
  "role": {
    "text": "You are a semantic compression expert...",
    "guid": "tag-uuid-1",
    "source": "mutation",
    "parent_tag_guid": "parent-tag-uuid"
  },
  "fitness": 0.82,
  "quality_score_avg": 8.5,
  "compression_ratio": 3.2,
  "created_at": "2025-01-15T11:00:00Z"
}
```

**Query examples:**
```sql
-- Get top 10 prompts from generation 10
SELECT prompt_id, fitness, compression_ratio, quality_score_avg
FROM `genetic`.`g_scope`.`generations`
WHERE era = 'test-1' AND generation = 10
ORDER BY fitness DESC
LIMIT 10;

-- Trace lineage of a prompt
SELECT generation, prompt_id, parents, fitness
FROM `genetic`.`g_scope`.`generations`
WHERE era = 'test-1'
START WITH prompt_id = 'target-prompt-id';
```

#### 3. `generation_stats` - Summary Statistics
**Purpose:** Pre-aggregated statistics for fast visualization

**Document structure:**
```json
{
  "era": "test-1",
  "generation": 10,
  "mean_fitness": 0.75,
  "median_fitness": 0.74,
  "std_fitness": 0.08,
  "max_fitness": 0.88,
  "elite_count": 10,
  "mutation_count": 5,
  "crossover_count": 30,
  "immigrant_count": 5,
  "elapsed_seconds": 245.3
}
```

**Query examples:**
```sql
-- Plot fitness over time
SELECT generation, mean_fitness, max_fitness
FROM `genetic`.`g_scope`.`generation_stats`
WHERE era = 'test-1'
ORDER BY generation;

-- Check convergence
SELECT generation, mean_fitness
FROM `genetic`.`g_scope`.`generation_stats`
WHERE era = 'test-1'
ORDER BY generation DESC
LIMIT 5;
```

#### 4. `eras` - Experiment Configurations
**Purpose:** Metadata and configuration for each experimental run

**Document structure:**
```json
{
  "era": "test-1",
  "compression_model": "claude",
  "population_size": 50,
  "elite_fraction": 0.2,
  "mutation_fraction": 0.2,
  "immigration_fraction": 0.08,
  "started_at": "2025-01-15T10:00:00Z",
  "completed_at": "2025-01-15T14:30:00Z",
  "final_max_fitness": 0.88,
  "total_generations": 20
}
```

---

## Capella UI Navigation

### Key Pages

1. **Clusters** - View all your clusters, create new ones
2. **Data Tools** - Browse documents, run queries
3. **Query Workbench** - SQL++ query interface
4. **Indexes** - View and create indexes for performance
5. **Settings** - Database access, allowed IPs, backups

### Query Workbench (Most Useful)

Access: Cluster page → **"Data Tools"** → **"Query"**

**Features:**
- Write SQL++ queries
- View results in table or JSON format
- Save queries for later
- Export results to CSV

**Example session:**
```sql
-- Check corpus size
SELECT COUNT(*) FROM `genetic`.`g_scope`.`unstructured`;

-- Sample a few chunks
SELECT chunk_id, LEFT(text, 100) as preview, word_count
FROM `genetic`.`g_scope`.`unstructured`
LIMIT 5;

-- View latest generation stats
SELECT * FROM `genetic`.`g_scope`.`generation_stats`
WHERE era = 'test-1'
ORDER BY generation DESC
LIMIT 1;
```

---

## Troubleshooting

### Connection Timeout

**Symptom:** `TimeoutError` or connection refused

**Causes:**
1. IP not in allowed list
2. Wrong connection string
3. Cluster not healthy

**Fixes:**
1. Add your IP: Settings → Allowed IP Addresses → Add My IP
2. Verify connection string: Cluster → Connect
3. Check cluster status: Should show "Healthy"

### Authentication Failed

**Symptom:** `AuthenticationError` or 401 status

**Causes:**
1. Wrong username/password
2. User doesn't have bucket access

**Fixes:**
1. Re-check credentials in `.env`
2. Verify user permissions: Settings → Database Access → Edit user
3. Ensure user has "All Buckets" or specific `genetic` bucket access

### Bucket Not Found

**Symptom:** `BucketNotFoundException`

**Causes:**
1. Bucket name mismatch
2. Bucket not created yet

**Fixes:**
1. Verify `COUCHBASE_BUCKET=genetic` in `.env` matches bucket name
2. Check bucket exists: Data Tools → Buckets
3. Create bucket if missing (Step 4.1)

### Collection Not Found

**Symptom:** Error querying collection

**Causes:**
1. Collection not created
2. Wrong scope/collection name

**Fixes:**
1. Verify collections exist: Bucket → Scopes & Collections
2. Check names: Must be `g_scope` (scope) and `unstructured`, `generations`, etc. (collections)
3. Create missing collections (Step 4.3)

### Query Timeout

**Symptom:** Query takes too long or times out

**Causes:**
1. No indexes on frequently queried fields
2. Large collection without LIMIT

**Fixes:**
1. Add indexes: See "Creating Indexes" below
2. Use LIMIT in queries
3. Filter on indexed fields (era, generation)

---

## Creating Indexes (Performance Optimization)

For large datasets (10,000+ prompts), create indexes:

### In Query Workbench:

```sql
-- Index for querying by era and generation
CREATE INDEX idx_era_generation
ON `genetic`.`g_scope`.`generations`(era, generation);

-- Index for fitness-based sorting
CREATE INDEX idx_fitness
ON `genetic`.`g_scope`.`generations`(fitness);

-- Index for corpus queries
CREATE INDEX idx_suitable_wordcount
ON `genetic`.`g_scope`.`unstructured`(suitable_for_compression_testing, word_count);
```

**When to create indexes:**
- After loading 1,000+ documents
- When queries become slow (>1 second)
- Before running large experiments (100+ population)

---

## Cost Management

### Free Tier Limits

**Capella Free Tier:**
- 50GB storage
- 3 nodes maximum
- Single availability zone
- No time limit

**This is sufficient for:**
- 100,000+ text chunks (500 words each)
- 50,000+ evolved prompts with full lineage
- Multiple experimental runs
- Research and development

### Monitoring Usage

1. Go to cluster page
2. Check **"Metrics"** tab
3. Watch:
   - **Data size**: Should stay under 50GB
   - **Operations/sec**: No limit on free tier
   - **Memory usage**: 2GB RAM available

**Cleanup strategy:**
```sql
-- Delete old experiments (if needed)
DELETE FROM `genetic`.`g_scope`.`generations`
WHERE era = 'old-test-1';

DELETE FROM `genetic`.`g_scope`.`generation_stats`
WHERE era = 'old-test-1';
```

### Upgrade to Paid (Optional)

If you need:
- More storage (>50GB)
- High availability (3+ nodes)
- Production workloads
- Dedicated support

Go to: Cluster → Settings → Upgrade

**Typical production costs:**
- $0.25/hour per node (3 nodes = $0.75/hour)
- ~$540/month for 3-node cluster
- Only needed for large-scale production use

---

## Next Steps

After completing this setup:

1. ✓ **Verify connection works** (Step 7)
2. ✓ **Load text corpus** (Step 8, see [`DATA_IMPORT.md`](project_docs/DATA_IMPORT.md))
3. ✓ **Run first experiment** (see [`README.md`](README.md) Quick Start)

**First experiment command:**
```bash
python scripts/run_experiment.py \
  --era quicktest \
  --population 5 \
  --generations 5 \
  --model claude
```

Expected time: 15-25 minutes
Expected result: Fitness improvement visible by Generation 3-5

---

## Reference Links

- **Couchbase Capella**: [https://cloud.couchbase.com](https://cloud.couchbase.com)
- **Capella Documentation**: [https://docs.couchbase.com/cloud/](https://docs.couchbase.com/cloud/)
- **SQL++ Reference**: [https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/)
- **Python SDK**: [https://docs.couchbase.com/python-sdk/current/](https://docs.couchbase.com/python-sdk/current/)

---

**Created:** December 2025
**Purpose:** Complete Couchbase Capella setup for genetic prompt evolution framework
**Audience:** New users with no prior Couchbase experience
