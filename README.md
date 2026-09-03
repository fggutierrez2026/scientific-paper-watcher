# Scientific Paper Watcher

Scientific Paper Watcher is a Python command-line application for monitoring scientific literature from **PubMed** and **arXiv**.

It can search scientific papers, normalize results into a common model, store them in SQLite, detect new and known papers, preserve query-to-paper provenance, manage persistent watch queries, execute batch searches, and generate Markdown reports.

**Current version: `0.3.0`**

---

## Main features

### Scientific sources

- PubMed
- arXiv

Results from both sources are normalized into a common `Paper` model before being stored.

### Persistent storage

- SQLite database.
- Automatic database initialization.
- Persistent papers across runs.
- Persistent watch queries.
- Query-to-paper provenance.
- Duplicate protection.

### Query management

The CLI supports:

```text
add-query
list-queries
remove-query
```

Stored queries use their real SQLite IDs.

Removing an active query does **not** delete its historical query-to-paper provenance.

### Compound queries

Scientific Paper Watcher includes a small common query language supporting:

```text
AND
OR
NOT
+
(...)
"..."
```

`+` is treated as an alias for `AND`.

Example:

```text
"GBP protein" + "biological sensor"
```

is normalized to:

```text
"GBP protein" AND "biological sensor"
```

The normalized query is then translated independently for PubMed and arXiv.

### Reports

- Per-query Markdown reports.
- Global report with all stored papers.
- Query provenance.
- Source warnings.
- Legacy handling for papers that predate provenance tracking.

### Reliability

- Logging.
- Explicit application exceptions.
- HTTP timeouts.
- Retry logic.
- Exponential backoff.
- `Retry-After` support where applicable.
- Graceful degradation if one source fails.
- Batch isolation between stored queries.
- arXiv request throttling.
- SQLite uniqueness constraints.

---

# Installation

## Requirements

Recommended:

```text
Python 3.12+
Git
Linux/macOS
```

Clone the repository:

```bash
git clone git@github.com:fggutierrez2026/scientific-paper-watcher.git
cd scientific-paper-watcher
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install the project in editable mode:

```bash
pip install -e .
```

Check the installation:

```bash
paper-watcher --version
```

Expected:

```text
paper-watcher 0.3.0
```

---

# Configuration

The application loads configuration from environment variables.

A local `.env` file can be used during development.

Example:

```env
# Database and output paths
PAPER_WATCHER_DB=data/papers.db
PAPER_WATCHER_REPORT_DIR=reports

# Network settings
REQUEST_TIMEOUT=15
MAX_RETRIES=3

# NCBI E-utilities (PubMed)
NCBI_EMAIL=your-email@example.com
NCBI_API_KEY=your-optional-ncbi-api-key

# bioRxiv / medRxiv settings
BIORXIV_SERVER=biorxiv
BIORXIV_INTERVAL=30d
```

*(Note: legacy aliases `DATABASE_PATH`, `REPORT_DIR`, and `PUBMED_EMAIL` are also supported for backwards compatibility).*

Do not commit secrets or personal configuration.

Recommended `.gitignore` entries:

```text
.env
.venv/
__pycache__/
*.pyc
data/*.db
reports/*.md
```

---

# Command-line interface

Show help:

```bash
paper-watcher --help
```

Current commands:

```text
run
add-query
list-queries
remove-query
report-all
```

Show version:

```bash
paper-watcher --version
```

---

# Run a single query

Example:

```bash
paper-watcher run \
    --query "protein design" \
    --max-results 5
```

The watcher queries PubMed and arXiv independently.

The high-level flow is:

```text
query
  |
  v
query validation
  |
  v
normalization
  |
  +-----------------------+
  |                       |
  v                       v
PubMed translation     arXiv translation
  |                       |
  v                       v
PubMed                 arXiv
  |                       |
  +-----------+-----------+
              |
              v
            Paper
              |
              v
            SQLite
              |
              +--> provenance
              |
              +--> Markdown report
```

---

# Compound queries

## Boolean operators

Supported operators:

```text
AND
OR
NOT
```

Example:

```bash
paper-watcher run \
    --query '("protein design" OR "protein engineering") AND biosensor' \
    --max-results 5
```

## Quoted phrases

Use quotes when a concept should be treated as a phrase:

```text
"protein language models"
```

## Parentheses

Use parentheses to group concepts:

```text
("glucose binding protein" OR GGBP)
AND
(biosensor OR "biological sensor")
```

Example:

```bash
paper-watcher run \
    --query '("glucose binding protein" OR GGBP) AND (biosensor OR "biological sensor")' \
    --max-results 5
```

## `+` alias

`+` is accepted as a convenience alias for `AND`.

Example:

```bash
paper-watcher run \
    --query '"GBP protein" + "biological sensor"' \
    --max-results 5
```

Normalized representation:

```text
"GBP protein" AND "biological sensor"
```

---

# Query translation

Scientific Paper Watcher stores a **common query representation** and translates it at runtime for each scientific source.

This separates:

```text
user intent
```

from:

```text
API-specific syntax
```

Example common query:

```text
("glucose binding protein" OR GGBP)
AND
(biosensor OR "biological sensor")
```

PubMed representation:

```text
("glucose binding protein" OR GGBP)
AND
(biosensor OR "biological sensor")
```

arXiv representation:

```text
(
    all:"glucose binding protein"
    OR
    all:GGBP
)
AND
(
    all:biosensor
    OR
    all:"biological sensor"
)
```

Source-specific arXiv syntax such as `all:` is not stored in SQLite provenance.

---

# Persistent watch queries

Add a query:

```bash
paper-watcher add-query \
    "protein design"
```

List stored queries:

```bash
paper-watcher list-queries
```

Example:

```text
Stored queries:

ID    Query
--    ----------------------------------------
1     protein design
2     molecular dynamics
4     computational protein design
5     protein language models
```

Remove a stored query:

```bash
paper-watcher remove-query 5
```

Historical provenance remains preserved.

Run all stored queries:

```bash
paper-watcher run \
    --max-results 5
```

---

# SQLite database

Default location:

```text
data/papers.db
```

Core tables:

```text
papers
watch_queries
paper_query_matches
```

## `papers`

A paper is uniquely identified inside a source by:

```text
(source, external_id)
```

## `watch_queries`

Stores active queries used in future batch runs.

Represents:

```text
current configuration
```

## `paper_query_matches`

Stores query-to-paper provenance.

Represents:

```text
historical provenance
```

Simplified schema:

```sql
CREATE TABLE paper_query_matches (
    paper_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (paper_id, query),

    FOREIGN KEY (paper_id)
        REFERENCES papers(id)
        ON DELETE CASCADE
);
```

---

# Provenance

Provenance answers:

```text
Which query found this paper?
```

Example:

```text
Paper A
  |
  +--> protein design
  |
  +--> computational protein design
```

A paper exists only once in `papers`, but can have multiple rows in `paper_query_matches`.

This is a many-to-many relationship:

```text
queries N <----> N papers
```

---

# Global report

Generate a global Markdown report:

```bash
paper-watcher report-all
```

Output:

```text
reports/all-papers_YYYY-MM-DD_HHMMSS.md
```

Columns:

```text
Query
Title
Authors
Source
URL
```

A paper may appear more than once if multiple queries matched it.

---

# Legacy papers

Papers inserted before provenance tracking was implemented may not have a historical query association.

These are shown as:

```text
legacy / unknown
```

The application does not invent historical provenance.

---

# Source failure handling

PubMed and arXiv are executed independently.

If one source fails and the other succeeds, the watcher continues with the successful source.

Only if all configured sources fail does the watcher raise a fatal application error.

---

# Retry and backoff

Transient failures are retried using exponential backoff.

The retry implementation can honor `Retry-After` when returned by a service.

---

# arXiv rate limiting

The arXiv source includes local throttling between API requests.

The limiter prevents rapid consecutive calls.

---

# Logging

The application uses Python logging for operational diagnostics.

Example:

```text
INFO    paper_watcher.sources.pubmed: Searching PubMed...
INFO    paper_watcher.sources.arxiv: Requesting arXiv API
WARNING paper_watcher.main: arXiv unavailable...
```

---

# Error model

Expected application failures inherit from:

```text
PaperWatcherError
```

Compound-query syntax errors use:

```text
QuerySyntaxError
```

Malformed queries therefore fail cleanly without exposing implementation tracebacks.

---

# Project structure

```text
scientific-paper-watcher/
|
+-- pyproject.toml
+-- README.md
+-- LICENSE
+-- .gitignore
|
+-- data/
|   +-- papers.db
|
+-- reports/
|   +-- *.md
|
+-- src/
    +-- paper_watcher/
        |
        +-- __init__.py
        +-- __main__.py
        +-- main.py
        +-- config.py
        +-- exceptions.py
        +-- logging_config.py
        +-- models.py
        +-- normalization.py
        +-- query_language.py
        |
        +-- reports/
        |   +-- __init__.py
        |   +-- markdown.py
        |
        +-- sources/
        |   +-- __init__.py
        |   +-- pubmed.py
        |   +-- arxiv.py
        |
        +-- storage/
            +-- __init__.py
            +-- sqlite.py
```

---

# Architecture

```text
                             CLI
                              |
              +---------------+----------------+
              |               |                |
              v               v                v
             run           queries         report-all
              |               |                |
              |         add/list/remove         |
              |               |                |
              v               v                |
       query_language      SQLite              |
              |               |                |
         +----+----+          |                |
         |         |          |                |
         v         v          |                |
       PubMed     arXiv       |                |
         |         |          |                |
         +----+----+          |                |
              |               |                |
              v               |                |
            Paper             |                |
              |               |                |
         +----+---------------+----+           |
         |                         |           |
         v                         v           |
       papers             paper_query_matches |
         |                         |           |
         +------------+------------+-----------+
                      |
                      v
                   reports
```

---

# Development checks

Compile the full package:

```bash
python -m compileall -q \
    src/paper_watcher
```

Check the exit code:

```bash
echo $?
```

Expected:

```text
0
```

Before committing:

```bash
git status
git diff
git diff --check
```

---

# Release history

## v0.1.0

Initial multi-source API consumer.

Highlights:

- PubMed integration.
- arXiv integration.
- normalized `Paper` model.
- logging.
- retries and exponential backoff.
- CLI package installation.

## v0.2.0

Persistent literature watcher.

Highlights:

- SQLite persistence.
- paper deduplication.
- persistent watch queries.
- Markdown reports.
- new-vs-known detection.
- graceful source failure handling.
- batch query execution.

## v0.3.0

Query-aware literature watcher.

Highlights:

- query-to-paper provenance;
- `paper_query_matches`;
- many-to-many query/paper model;
- global `report-all`;
- `legacy / unknown`;
- real SQLite IDs in `list-queries`;
- `remove-query ID`;
- removal without deleting provenance;
- compound query language;
- `AND`, `OR`, `NOT`;
- `+` alias for `AND`;
- quoted phrases;
- parentheses;
- syntax validation;
- PubMed query translation;
- arXiv query translation;
- canonical query persistence.

---

# Design principles

- Preserve user intent.
- Keep source adapters isolated.
- Preserve historical provenance.
- Prefer deterministic paper identity.
- Degrade gracefully when one source fails.
- Avoid silent data loss.
- Normalize common queries before persistence.

---

# Current limitations

Scientific Paper Watcher currently does not:

- automatically merge PubMed and arXiv records by DOI;
- perform fuzzy cross-source paper merging;
- support portable source-specific field expressions;
- provide a GUI or web interface;
- run automatically as a Linux service;
- send notifications;
- summarize papers with an LLM;
- use a formal migration framework such as Alembic.

---

# Roadmap

Possible future work:

```text
systemd service
systemd timer
automatic restart
journalctl-based operations
scheduled literature monitoring
CSV/TSV export
statistics by query
papers shared across queries
date-based reporting
query editing
field-aware common queries
cross-source DOI analysis
automated tests
CI with GitHub Actions
notifications
local-LLM summarization
```

---

# Example workflow

Add queries:

```bash
paper-watcher add-query \
    "protein design"

paper-watcher add-query \
    "molecular dynamics"

paper-watcher add-query \
    '"protein language models"'

paper-watcher add-query \
    '("glucose binding protein" OR GGBP) AND (biosensor OR "biological sensor")'
```

List them:

```bash
paper-watcher list-queries
```

Run all stored queries:

```bash
paper-watcher run \
    --max-results 5
```

Generate the global report:

```bash
paper-watcher report-all
```

Remove an obsolete query:

```bash
paper-watcher remove-query 2
```

Historical provenance remains available.

---

# License

This project is distributed under the MIT License.

See `LICENSE` for details.
