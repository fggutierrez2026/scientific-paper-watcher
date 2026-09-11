# Scientific Paper Watcher

Scientific Paper Watcher is a Python command-line application for monitoring scientific literature from **PubMed**, **arXiv**, **bioRxiv**, and **medRxiv**.

It can search scientific papers and patents through scoped source registries,
normalize results into canonical models, store them in SQLite, preserve query
provenance, manage persistent watch queries, execute batch searches, and
generate Markdown reports.

**Current version: `0.4.0`**

---

## Main features

### Scientific sources

- PubMed
- arXiv
- bioRxiv
- medRxiv

Results from all four sources are normalized into a common `Paper` model before being stored.

### Persistent storage

- SQLite database.
- Automatic database initialization.
- Persistent papers across runs.
- Canonical patent records ready for upcoming patent source adapters.
- Patent families that link legal documents without collapsing them.
- Multi-source patent provenance and verified paper-to-patent citation links.
- Persistent, scoped watch queries.
- Query-to-paper and query-to-patent provenance.
- Duplicate protection.

Patent identity is based on the normalized jurisdiction and publication number.
The application number is used only as a fallback when a publication identity is
not yet available. Existing databases are upgraded additively during normal
initialization; paper records and their provenance remain unchanged.

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

- Per-query Markdown reports with separate paper and patent sections.
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

### Adapter architecture (v0.5.0 foundation)

Source integrations expose a common, typed adapter contract. Capabilities state
whether an adapter discovers or enriches papers, patents, or both, together with
its temporal-filter and pagination behavior. Every adapter returns canonical
`Paper`/`Patent` records plus provider-independent counts, cursors, truncation,
warnings, and source status.

Paper and patent adapters live in separate ordered registries. The search
orchestrator selects them from `PAPER_SOURCES` and `PATENT_SOURCES`, isolates an
operational failure to its source, and coalesces a multi-domain adapter into one
call when the requested scope is `all`. The CLI exposes this routing through the
`papers`, `patents`, and `all` search scopes.

A shared HTTP client is available for adapters added or migrated during task
2.3. It centralizes timeouts, retries, `Retry-After`, safe HTTP errors, and
credential redaction while allowing each provider to retain custom response
validation. PubMed, arXiv, bioRxiv/medRxiv, and OpenAlex use this client;
arXiv keeps its provider-specific request throttling and OpenAlex keeps its
valid not-found behavior.

### Semantic Scholar

Semantic Scholar relevance search is available as an opt-in paper source:

```env
PAPER_SOURCES=pubmed,arxiv,biorxiv,medrxiv,semantic_scholar
SEMANTIC_SCHOLAR_API_KEY=
```

The key is optional and, when configured, is sent only in the `x-api-key`
header. The adapter requests explicit bibliographic, identifier, citation,
field-of-study, and open-access PDF fields; paginates in relevance order; and
uses the native `publicationDateOrYear` filter for incremental windows.

The relevance endpoint does not support the watcher's Boolean syntax. Its
translation removes `AND`, `OR`, and grouping, omits terms governed by `NOT`,
and replaces hyphens with spaces. For example,
`("protein-design" OR biosensor) NOT cancer` becomes
`protein design biosensor`. The original normalized query remains attached to
stored provenance. The endpoint is capped at 1,000 relevance-ranked results.

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
paper-watcher 0.4.0
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

# bioRxiv / medRxiv settings (both sources run independently)
BIORXIV_INTERVAL=30d

# Optional OpenAlex enrichment
OPENALEX_ENABLED=false
OPENALEX_API_KEY=your-optional-openalex-api-key

# Enabled sources (new adapters remain opt-in until implemented)
PAPER_SOURCES=pubmed,arxiv,biorxiv,medrxiv
PATENT_SOURCES=

# Additional scholarly API access
SEMANTIC_SCHOLAR_API_KEY=
CROSSREF_EMAIL=your-email@example.com
CORE_API_KEY=
UNPAYWALL_EMAIL=your-email@example.com
LENS_API_TOKEN=

# Patent API access
USPTO_API_KEY=
EPO_CONSUMER_KEY=
EPO_CONSUMER_SECRET=
WIPO_USERNAME=
WIPO_PASSWORD=
```

*(Note: legacy aliases `DATABASE_PATH`, `REPORT_DIR`, and `PUBMED_EMAIL` are also supported for backwards compatibility).*

Do not commit secrets or personal configuration.

The source lists are comma-separated. Missing credentials are checked only when
their source is activated, so a restricted API does not prevent independent
public sources from being configured. See the
[external API access matrix](docs/api-access.md) for accepted source names,
registration links, access restrictions, and secret-handling rules.

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
search
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

# Search papers and patents

`search` is the preferred command for a direct query. Its default scope is
`papers`:

```bash
paper-watcher search --query "protein design"
paper-watcher search --query "protein design" --scope patents
paper-watcher search --query "protein design" --scope all --max-results 10
```

Results are persisted in their separate paper and patent tables. Console and
Markdown output use separate sections and show counts for both document types.
Patent source adapters are introduced in phase 4, so the default configuration
currently reports an empty patent section with an explanatory warning.

## Compatible `run` command

`run --query` remains a compatibility alias for at least the v0.5 release and
accepts the same `--scope` values. New scripts should use `search`; `run` remains
the command for executing all stored watch queries when `--query` is omitted.

```bash
paper-watcher run \
    --query "protein design" \
    --scope papers \
    --max-results 5
```

The watcher queries PubMed, arXiv, bioRxiv, and medRxiv independently.
OpenAlex enrichment is disabled by default. Enable it for one run with:

```bash
paper-watcher run \
    --query "protein design" \
    --max-results 5 \
    --openalex
```

Use `--no-openalex` to override an enabled `OPENALEX_ENABLED` setting. When
enabled, OpenAlex looks up each collected paper by DOI, falling back to an exact
normalized-title match when no DOI is available. Citation counts, up to three
topics, the OpenAlex identifier, and the best direct open-access PDF link are
stored in SQLite and included in new-paper reports. An API key is optional for
casual use and recommended for a larger request budget.

## Time windows and incremental runs

Limit a run to an explicit UTC date or a rolling number of days:

```bash
paper-watcher run --query "protein design" --since 2026-08-01
paper-watcher run --query "protein design" --days 7
```

`--since` and `--days` are mutually exclusive. The date window is translated to
each provider's native filtering syntax: Entrez dates for PubMed,
`submittedDate` for arXiv, and date-range endpoints for bioRxiv and medRxiv.
Overlapping boundary dates are safe because SQLite identity resolution removes
already-known papers from the new-paper report.

Stored watch queries are incremental automatically. Their first successful run
performs the normally configured search and records `last_checked_at`; later
runs use that checkpoint as their lower bound. A checkpoint advances only when
all selected sources complete, so a temporary source failure cannot create a
gap. Explicit `--since` or `--days` values override the stored checkpoint for
that execution. The checkpoint also remains unchanged if `--max-results`
truncates an incremental window; increase the limit and rerun to avoid skipping
documents.

Each stored query retains its scope. Existing databases are migrated to
`scope='papers'`. Add and inspect scoped queries with:

```bash
paper-watcher add-query "protein biosensor" --scope all
paper-watcher list-queries
paper-watcher run
```

Passing `--scope` to `paper-watcher run` overrides the saved scope for that
execution; without it, every stored query uses its persisted scope.

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
PubMed / arXiv / bioRxiv / medRxiv
              |
              v
     OpenAlex (optional)
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

Stores active queries used in future batch runs together with the UTC
`last_checked_at` checkpoint used for incremental retrieval. `list-queries`
shows the checkpoint or `never` before the first complete run.

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

## v0.4.0

Cross-source and incremental literature watcher.

Highlights:

- DOI/title-based cross-source deduplication and metadata fusion;
- bioRxiv and medRxiv integration;
- optional OpenAlex enrichment with citations, topics, and open-access PDFs;
- persistent `last_checked_at` checkpoints for watch queries;
- `--since YYYY-MM-DD` and `--days N` time windows;
- native date filters for PubMed, arXiv, bioRxiv, and medRxiv;
- conservative checkpoint handling after partial or truncated runs.

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
