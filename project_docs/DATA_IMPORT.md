# Data Import & Corpus Preparation Guide

This guide explains how to prepare your text corpus for compression experiments using the genetic algorithm framework. Corpus preparation is a one-time setup task that makes text available for the framework to evaluate compression prompts against.

---

## Overview: The Three-Step Process

1. **Gather Documents** - Collect text files in your domain (PDF, HTML, Markdown)
2. **Extract & Chunk** - Process documents into ~600-word segments
3. **Load to Couchbase** - Store chunks in the `unstructured` collection

Once your corpus is loaded, you can run unlimited experiments against it.

---

## Prerequisites

### Required Software

- **Python 3.13+** - Already installed if you completed the README Quick Start
- **Unstructured.io library** - Installed via `pip install -r requirements.txt`

### Supported Document Formats

The framework supports these file types:

| Format | Extension | Notes |
|--------|-----------|-------|
| PDF | `.pdf` | Text extraction from PDFs (scanned PDFs not supported) |
| HTML | `.html`, `.htm` | Converts HTML to text, strips markup |
| Markdown | `.md` | Preserves structure information |
| Plain Text | `.txt` | Simple text files |

### Couchbase Collections

The framework automatically creates this collection structure:

```
genetic (bucket)
└── g_scope (scope)
    └── unstructured (collection)
        ├── chunk_id (unique identifier)
        ├── text (the ~600-word chunk)
        ├── metadata (source file, domain, etc.)
        └── ...
```

You don't need to create collections manually. The framework creates them on first use.

---

## Step 1: Prepare Your Documents

Organize documents by domain in your file system:

```
documents/
├── academic/
│   ├── paper1.pdf
│   ├── paper2.pdf
│   └── textbook_chapter3.md
├── legal/
│   ├── contract_nda.pdf
│   ├── policy_document.md
│   └── regulations.html
├── technical/
│   ├── api_documentation.md
│   ├── tutorial.html
│   └── specification.pdf
└── conversational/
    ├── interview_transcript.txt
    ├── podcast_transcript.md
    └── dialogue.txt
```

**Document Quality Guidelines:**

- **Content Quality:** Use documents with good signal-to-noise ratio (minimal boilerplate, headers, footers)
- **Text Quality:** Plain text, minimal formatting issues
- **Diversity:** Mix documents of different types within each domain for robustness
- **File Size:** Individual files should be 5-100 pages (PDF) or 5,000-50,000 words for best results

---

## Step 2: Extract and Import Using the Command-Line Script

The `populate_corpus.py` script handles extraction and import in one command.

### Basic Usage

```bash
# Single file
python scripts/populate_corpus.py --domain academic --file papers/research.pdf

# Directory (all supported files)
python scripts/populate_corpus.py --domain legal --dir documents/legal/

# With custom chunk size
python scripts/populate_corpus.py --domain mixed --dir documents/ --target-words 500
```

### Available Domains

Specify the domain classification for your content:

- `academic` - Research papers, textbooks, scholarly articles
- `medical` - Medical research, clinical studies, health documentation
- `conversational` - Interviews, podcasts, dialogues, discussions
- `technical` - Documentation, API references, tutorials, specifications
- `narrative` - News articles, blog posts, stories, feature writing
- `legal` - Contracts, policies, regulations, legal documents
- `mixed` - Miscellaneous or uncategorized content

### Command-Line Options

```bash
--domain          Required. One of: academic, medical, conversational, technical,
                  narrative, legal, mixed
--file            Optional. Single file path. Use either --file or --dir, not both
--dir             Optional. Directory path. Imports all PDF/HTML/MD files recursively
--target-words    Optional. Target words per chunk (default: 600)
```

### Examples by Use Case

**Academic Papers:**
```bash
python scripts/populate_corpus.py --domain academic --dir papers/ --target-words 700
```

**Legal Documents:**
```bash
python scripts/populate_corpus.py --domain legal --dir contracts/
```

**Mixed Content from Multiple Domains:**
```bash
# Import multiple domains
python scripts/populate_corpus.py --domain academic --dir documents/academic/
python scripts/populate_corpus.py --domain technical --dir documents/technical/
python scripts/populate_corpus.py --domain conversational --dir documents/interviews/
```

**Custom Chunk Size for Dense Technical Content:**
```bash
python scripts/populate_corpus.py --domain technical --dir api_docs/ --target-words 500
```

---

## Step 3: Understand What the Script Does

When you run `populate_corpus.py`, here's what happens:

### 1. Document Discovery
- Scans specified file or directory
- Finds all `.pdf`, `.html`, `.htm`, and `.md` files
- Reports files found

### 2. Content Extraction
- Uses unstructured.io's `partition()` function
- Auto-detects file type
- Extracts text and preserves metadata (page numbers, element types, coordinates)
- Fails loudly if extraction fails (no silent fallbacks)

### 3. Smart Chunking
- Divides content into approximately 600-word chunks
- Respects element boundaries (doesn't split paragraphs mid-sentence)
- Tracks element types (NarrativeText, Title, Table, etc.)
- Preserves page numbers and source information

### 4. Metadata Attachment
Each chunk stored in Couchbase includes:

```json
{
  "chunk_id": "550e8400-e29b-41d4-a716-446655440000",
  "source_file": "research_paper.pdf",
  "source_type": "pdf",
  "domain": "academic",
  "text": "The complete 600-word chunk of text...",
  "word_count": 598,
  "element_types": {
    "NarrativeText": 8,
    "Title": 1,
    "Table": 2
  },
  "page_numbers": [5, 6, 7],
  "chunk_index": 0,
  "total_chunks": 45,
  "created_at": "2025-12-08T15:30:45Z"
}
```

### 5. Storage in Couchbase
- Connects to Couchbase using credentials from `.env`
- Creates `unstructured` collection if needed
- Stores chunks with unique IDs
- Reports import statistics

---

## Monitoring Import Progress

### During Import

The script provides real-time feedback:

```
Processing documents/academic/...
✓ Extracting paper1.pdf (85 pages)
  → Found 127 elements
  → Creating 23 chunks (~600 words each)
  → Stored chunks: chunk_001, chunk_002, ..., chunk_023

✓ Extracting paper2.pdf (42 pages)
  → Found 64 elements
  → Creating 12 chunks (~600 words each)
  → Stored chunks: chunk_024, chunk_025, ..., chunk_035

Summary:
  Total files processed: 2
  Total chunks created: 35
  Total words imported: 21,000
  Domain: academic
  Import complete!
```

### Verify Import in Couchbase

Query your imported data directly:

```sql
-- Count chunks by domain
SELECT domain, COUNT(*) as chunk_count
FROM unstructured
GROUP BY domain;

-- List all chunks from a file
SELECT chunk_id, word_count, element_types
FROM unstructured
WHERE source_file = 'research_paper.pdf'
ORDER BY chunk_index;

-- Find longest chunks
SELECT source_file, word_count, chunk_index
FROM unstructured
WHERE domain = 'academic'
ORDER BY word_count DESC
LIMIT 10;
```

---

## Understanding Chunk Size (Why ~600 Words?)

The default chunk size of 600 words is chosen deliberately:

**Word Count Context:**
- 600 words ≈ 800-1000 tokens in typical LLM tokenization
- This fits comfortably within most model context windows
- Large enough for meaningful compression opportunity
- Small enough for quick evaluation

**Compression Opportunity:**
- A 600-word chunk can typically compress to 200-400 words (33-67% reduction)
- Represents realistic compression scenarios
- Allows quality metrics to show meaningful variation

**Evaluation Speed:**
- Compression + judging takes 10-30 seconds per chunk
- Population of 20 prompts × 600-word chunk = 10-30 minutes per generation
- Allows rapid iteration during development

**Customization:**
If you have specific needs, you can adjust:

```bash
# Smaller chunks for dense technical content
python scripts/populate_corpus.py --domain technical --dir api_docs/ --target-words 400

# Larger chunks for narrative content
python scripts/populate_corpus.py --domain narrative --dir articles/ --target-words 800
```

---

## Alternative Import Methods

### Method 1: Bulk Import from JSON

If you have pre-chunked data, you can import from JSON:

```bash
python scripts/import_json_chunks.py --file chunks.json --domain mixed
```

**JSON Format Expected:**
```json
[
  {
    "chunk_id": "unique-id-1",
    "text": "The chunk content here...",
    "source_file": "original.pdf",
    "word_count": 598,
    "domain": "academic"
  },
  {
    "chunk_id": "unique-id-2",
    "text": "Another chunk...",
    "source_file": "original.pdf",
    "word_count": 602,
    "domain": "academic"
  }
]
```

### Method 2: Python API

Import programmatically in your own scripts:

```python
from src.corpus_extractor import extract_chunks, store_chunks
from src.couchbase_client import CouchbaseClient

# Extract chunks from a file
chunks = extract_chunks("papers/research.pdf", target_words=600)

# Store in Couchbase
with CouchbaseClient() as cb:
    store_chunks(chunks, domain="academic", couchbase_client=cb)
    print(f"Stored {len(chunks)} chunks")
```

---

## Common Issues & Troubleshooting

### Issue: "Failed to extract content from PDF"

**Causes:**
- PDF is scanned image only (no text layer)
- File is corrupted
- File format not actually PDF

**Solutions:**
- Use OCR to extract text from scanned PDFs first (outside this framework)
- Verify file with: `file your_document.pdf`
- Try opening in PDF reader to confirm readability

### Issue: "Connection refused" when storing to Couchbase

**Causes:**
- Couchbase cluster not running
- Credentials in `.env` are wrong
- Network connectivity issue

**Solutions:**
```bash
# Test connection before import
python -c "from src.couchbase_client import CouchbaseClient; \
           CouchbaseClient().cluster; print('Connected!')"

# Verify .env contains correct credentials
cat .env | grep COUCHBASE
```

### Issue: Chunks are too small or too large

**Diagnosis:**
```bash
# Check actual chunk distribution
python -c "
from src.couchbase_client import CouchbaseClient
with CouchbaseClient() as cb:
    result = cb.cluster.query(
        'SELECT AVG(word_count) as avg_words, \
                MIN(word_count) as min_words, \
                MAX(word_count) as max_words \
         FROM unstructured'
    )
    for row in result:
        print(f\"Average: {row['avg_words']:.0f} words\")
        print(f\"Range: {row['min_words']}-{row['max_words']} words\")
"
```

**Solution:** Re-import with different `--target-words` value:
```bash
python scripts/populate_corpus.py --domain academic --dir papers/ --target-words 500
```

### Issue: HTML markup appearing in chunks

**Cause:** HTML file not parsed correctly

**Solution:**
- Ensure file has proper HTML structure with `<html>` and `<body>` tags
- Unstructured.io uses `BeautifulSoup` which handles most HTML variations
- For problematic HTML, convert to plain text or Markdown first

### Issue: Import is slow

**Typical Performance:**
- PDF extraction: 1-2 pages per second
- Chunking: 10,000 words per second
- Couchbase storage: 100+ chunks per second

**For Large Corpus:**
```bash
# Monitor progress
watch -n 5 'echo "SELECT COUNT(*) FROM unstructured" | \
            cbq -u user -p pass -c couchbase://localhost'

# Import in batches if needed
python scripts/populate_corpus.py --domain academic --dir papers/batch1/
python scripts/populate_corpus.py --domain academic --dir papers/batch2/
```

---

## Data Quality Considerations

### Suitable for Compression Testing

Good candidates for your corpus:
- Technical documentation
- Research papers
- Business reports
- News articles
- Product descriptions
- Policy documents

### Characteristics of Useful Text

- Natural language (not highly formatted tables)
- Semantic content (information with meaning)
- Varied sentence structure
- Mix of concepts and details

### Text to Avoid

- Raw HTML/markup (will include tags in chunks)
- Scanned PDFs without OCR (extraction fails)
- Highly tabular data (loses structure in chunking)
- Single-sentence files (not enough content)

---

## After Import: What's Next?

Once corpus is loaded, you can:

1. **Run a Quick Test:**
   ```bash
   python scripts/run_experiment.py --era test-1 --population 20 --generations 5
   ```

2. **Check Corpus Statistics:**
   ```sql
   SELECT domain, COUNT(*) as chunks, AVG(word_count) as avg_words
   FROM unstructured
   GROUP BY domain;
   ```

3. **View Sample Chunks:**
   ```sql
   SELECT chunk_id, source_file, word_count, text
   FROM unstructured
   LIMIT 5;
   ```

4. **Run Production Experiments:**
   ```bash
   python scripts/run_experiment.py --era prod-1 --population 100 --generations 20
   ```

---

## Scaling to Large Corpora

For production use with thousands of documents:

**Recommended Approach:**
1. Import in batches by domain
2. Monitor Couchbase storage
3. Consider index creation for faster queries

**Estimated Storage:**
- ~600-word chunk = 4-5 KB in Couchbase
- 10,000 chunks = 40-50 MB
- 100,000 chunks = 400-500 MB

**Index Creation (optional):**
```sql
CREATE INDEX idx_unstructured_domain
ON unstructured(domain);

CREATE INDEX idx_unstructured_source
ON unstructured(source_file);
```

---

## Reference: Complete Data Model

When you import chunks, they're stored with this structure:

```python
{
    "chunk_id": str,                    # UUID for this chunk
    "source_file": str,                 # Original filename
    "source_type": str,                 # File extension (pdf, html, md, txt)
    "domain": str,                      # Classification domain
    "text": str,                        # The actual 600-word chunk
    "word_count": int,                  # Actual word count
    "element_types": dict,              # Distribution of element types
    "page_numbers": list,               # Page numbers (PDFs only)
    "elements": list,                   # Detailed element metadata
    "chunk_index": int,                 # Position in source document
    "total_chunks": int,                # Total chunks from this document
    "created_at": str,                  # ISO timestamp
}
```

This structure enables corpus queries, filtering, and analysis for Paper 2 research.

---

## Support & Questions

**Framework Documentation:**
- See `README.md` for general framework overview
- See `FITNESS_FUNCTION.md` for evaluation details
- See `CLAUDE.md` for architecture information

**Unstructured.io Documentation:**
- https://unstructured.io/
- Supports many additional document types beyond PDF/HTML/MD

---

**Last Updated:** December 8, 2025
**Framework Version:** 1.0
