# Scientific Paper Watcher

A command-line scientific literature watcher for monitoring **PubMed** and **arXiv**, storing results in **SQLite**, detecting papers seen for the first time, and generating **Markdown reports**.

Scientific Paper Watcher is designed as a small, transparent, local-first project that can later be run automatically as a scheduled service.

Current version:

```text
0.2.0
```

---

## Features

- Search scientific literature in:
  - PubMed
  - arXiv
- Normalize results from different sources into a common `Paper` model.
- Store retrieved papers in SQLite.
- Prevent duplicate insertion using `(source, external_id)` identity.
- Normalize DOI values for comparison and storage.
- Persist scientific queries in SQLite.
- Run one ad hoc query from the CLI.
- Run all stored watch queries as a batch.
- Detect papers seen for the first time by the local database.
- Generate one Markdown report per query.
- Record source warnings in reports.
- Continue when one source is temporarily unavailable.
- Continue a batch when one stored query fails completely.
- Retry transient HTTP and rate-limit failures with exponential backoff.
- Respect arXiv request-rate constraints.
- Provide structured logging for searches, retries, failures, storage, and reports.

---

## Project status

### v0.1.0

Initial API consumer:

- PubMed integration
- arXiv integration
- common `Paper` model
- XML / Atom parsing
- logging
- custom exceptions
- retries and exponential backoff
- initial CLI

### v0.2.0

Persistence and watcher workflow:

- SQLite paper storage
- deduplication
- persistent watch queries
- Markdown reports
- detection of newly discovered papers
- source-level graceful degradation
- `run` CLI subcommand
- batch execution of stored queries

---

## Requirements

Recommended environment:

- Python 3.12+
- Linux, macOS, or another environment capable of running Python
- Internet connection for PubMed and arXiv queries

The project uses a Python virtual environment during development.

---

## Installation

Clone the repository:

```bash
git clone git@github.com:fggutierrez2026/scientific-paper-watcher.git
cd scientific-paper-watcher
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install the project in editable mode:

```bash
pip install -e .
```

Verify the installation:

```bash
paper-watcher --version
```

Expected output:

```text
paper-watcher 0.2.0
```

---

## Configuration

Scientific Paper Watcher reads its configuration from environment variables and/or a local `.env` file.

Create a `.env` file in the project root.

Example:

```env
PUBMED_EMAIL=your_email@example.com
PUBMED_TOOL=scientific-paper-watcher

PAPER_WATCHER_DB=data/papers.db
PAPER_WATCHER_REPORT_DIR=reports

REQUEST_TIMEOUT=15
```

Do not commit private or machine-specific environment configuration.

The `.env` file should remain ignored by Git.

---

## Command-line interface

The CLI follows the pattern:

```text
paper-watcher COMMAND [OPTIONS]
```

Available commands:

```text
run
add-query
list-queries
```

View the global help:

```bash
paper-watcher --help
```

View help for `run`:

```bash
paper-watcher run --help
```

---

## Run one query

To execute one ad hoc scientific query:

```bash
paper-watcher run \
    --query "protein language models" \
    --max-results 5
```

`--max-results` defines the maximum number of papers requested from **each source**.

For example:

```bash
paper-watcher run \
    --query "protein design" \
    --max-results 2
```

may retrieve up to:

```text
2 PubMed papers
+
2 arXiv papers
```

depending on source availability and returned results.

When `--query` is present, only that query is executed.

---

## Add a persistent watch query

Store a query in SQLite:

```bash
paper-watcher add-query \
    "protein design"
```

Another example:

```bash
paper-watcher add-query \
    "molecular dynamics"
```

Duplicate query insertion is ignored.

Example:

```text
Query already exists: protein design
```

Empty queries are rejected by the CLI.

---

## List stored queries

```bash
paper-watcher list-queries
```

Example:

```text
Stored queries:

1. protein design
2. molecular dynamics
3. protein language models
4. computational protein design
```

These queries are stored in SQLite and persist across program executions.

---

## Run all stored queries

Run the watcher without providing `--query`:

```bash
paper-watcher run \
    --max-results 5
```

Scientific Paper Watcher loads all stored watch queries from SQLite and executes them one by one.

Conceptually:

```text
SQLite watch_queries
        |
        v
paper-watcher run
        |
        +--> query 1
        |
        +--> query 2
        |
        +--> query 3
        |
        v
BATCH SUMMARY
```

Example summary:

```text
======================================================================
BATCH SUMMARY
======================================================================
Queries processed: 4
Queries successful: 4
Queries failed: 0
```

If no queries have been stored:

```text
No stored queries.
```

---

## What does "new paper" mean?

Scientific Paper Watcher uses **local discovery state**, not publication date alone.

A paper is considered **new** when it is successfully retrieved and has **not previously been stored in the local SQLite database**.

Therefore:

```text
new paper
```

means:

```text
first time seen by this local Scientific Paper Watcher database
```

It does **not** necessarily mean:

```text
published today
```

or:

```text
published recently
```

A paper published weeks or months ago can still be reported as new if the local watcher has never seen it before.

---

## Deduplication

The primary paper identity is:

```text
(source, external_id)
```

Examples:

```text
(pubmed, 42420197)
(arxiv, 2608.18597v1)
```

SQLite enforces this identity through a unique index.

Paper insertion uses:

```sql
INSERT OR IGNORE
```

so repeated searches do not duplicate already known papers.

The storage workflow distinguishes:

```text
Papers retrieved
New papers
Known papers
Total papers stored
```

For example:

```text
Papers retrieved: 2
New papers: 0
Known papers: 2
Total papers stored: 14
```

---

## DOI normalization

DOIs are normalized before storage/comparison.

Equivalent forms such as:

```text
10.1000/ABC
doi:10.1000/ABC
https://doi.org/10.1000/ABC
```

are normalized toward:

```text
10.1000/abc
```

A normalized DOI is treated as a strong cross-source signal, but it is not currently used as the database primary identity.

---

## Reports

Scientific Paper Watcher writes Markdown reports to the configured report directory.

Default example:

```text
reports/
```

A generated filename follows the pattern:

```text
<query-slug>_YYYY-MM-DD_HHMMSS.md
```

For example:

```text
reports/protein-language-models_2026-08-26_143815.md
```

Each report contains:

```text
query
generation time
number of new papers
source warnings, if any
paper metadata
authors
abstract
DOI
URL
```

---

## Example report

```markdown
# Scientific Paper Watcher Report

**Query:** protein language models

**Generated:** 2026-08-26 14:38:15

**New papers:** 1

## Example paper title

**Source:** ARXIV

**External ID:** 2608.18597v1

**Published:** 2026-08-19

**Authors:** Example Author, Another Author

**URL:** https://...

Paper abstract...
```

If no newly discovered papers are found:

```markdown
**New papers:** 0

_No new papers found._
```

---

## Source warnings

PubMed and arXiv are handled independently.

If one source fails and the other succeeds, the query continues.

For example:

```text
PubMed: success
arXiv: failure
```

is still treated as a usable query execution.

The warning is recorded in the generated Markdown report:

```markdown
## Source warnings

- arXiv unavailable: ...
```

When warnings exist and no new papers were found among successful sources, the report states:

```markdown
_No new papers found among sources that completed successfully._
```

---

## Failure model

Scientific Paper Watcher contains two levels of fault isolation.

### Source-level isolation

Inside one query:

```text
query
 |
 +--> PubMed
 |
 +--> arXiv
```

If one source fails:

```text
PubMed OK
arXiv FAIL
```

the query can still complete.

A query fails completely only when all configured sources fail.

### Query-level isolation

During batch mode:

```text
query 1 -> success
query 2 -> complete failure
query 3 -> success
query 4 -> success
```

a failed query does not prevent later stored queries from running.

The batch records the failure and continues.

---

## Retries and backoff

Transient source failures are retried.

Examples include:

- request timeouts
- rate limiting
- retryable HTTP failures

The retry schedule uses exponential backoff.

An example sequence is:

```text
3 seconds
6 seconds
12 seconds
```

Expected permanent or non-retryable errors are not retried indefinitely.

---

## arXiv rate limiting

Scientific Paper Watcher applies local request spacing before arXiv API calls.

Example log:

```text
Waiting 0.88 seconds to respect arXiv rate limit
```

The wait reflects the remaining time required to satisfy the configured interval rather than always sleeping a complete fixed duration.

---

## Logging

The application emits structured logs for important operations.

Example:

```text
INFO    Searching PubMed for query='protein design' max_results=1
INFO    PubMed search completed: total_count=... returned=1
INFO    Searching arXiv for query='protein design' max_results=1
WARNING arXiv unavailable: ...
```

Logging is used for:

- API searches
- parsing
- retries
- timeouts
- rate limits
- source failures
- batch failures

---

## Database

Default database:

```text
data/papers.db
```

The database currently contains two main tables:

```text
papers
watch_queries
```

### `papers`

Stores normalized paper data.

Conceptual fields:

```text
id
source
external_id
doi
title
abstract
authors
published
url
created_at
```

### `watch_queries`

Stores persistent scientific search queries.

Conceptual fields:

```text
id
query
```

---

## Data flow

A single query follows approximately:

```text
query
 |
 +------------------+
 |                  |
 v                  v
PubMed            arXiv
 |                  |
 v                  v
Paper[]           Paper[]
 |                  |
 +--------+---------+
          |
          v
      all_papers
          |
          v
       SQLite
          |
      +---+---+
      |       |
      v       v
     NEW     KNOWN
      |
      v
Markdown report
```

Batch execution adds an outer loop:

```text
watch_queries
     |
     v
for query
     |
     v
run(query)
```

---

## Project structure

The project is organized approximately as:

```text
scientific-paper-watcher/
|
+-- src/
|   |
|   +-- paper_watcher/
|       |
|       +-- __init__.py
|       +-- __main__.py
|       +-- main.py
|       +-- config.py
|       +-- exceptions.py
|       +-- logging_config.py
|       +-- models.py
|       +-- normalization.py
|       |
|       +-- sources/
|       |   +-- pubmed.py
|       |   +-- arxiv.py
|       |
|       +-- storage/
|       |   +-- sqlite.py
|       |
|       +-- reports/
|           +-- markdown.py
|
+-- data/
|   +-- papers.db
|
+-- reports/
|
+-- .env
+-- .gitignore
+-- LICENSE
+-- pyproject.toml
+-- README.md
```

Generated database and report files should generally remain outside version control.

---

## Development checks

Compile one module:

```bash
python -m py_compile \
    src/paper_watcher/main.py
```

Compile the full package:

```bash
python -m compileall -q \
    src/paper_watcher
```

Check the exit status:

```bash
echo $?
```

Expected result:

```text
0
```

---

## Useful CLI regression checks

Global help:

```bash
paper-watcher --help
```

Run help:

```bash
paper-watcher run --help
```

Version:

```bash
paper-watcher --version
```

List queries:

```bash
paper-watcher list-queries
```

Run one query:

```bash
paper-watcher run \
    --query "protein language models" \
    --max-results 1
```

Run all queries:

```bash
paper-watcher run \
    --max-results 1
```

Running without a command:

```bash
paper-watcher
```

should produce an `argparse` usage error because a subcommand is required.

---

## Git workflow

Inspect repository status:

```bash
git status
```

Inspect changes:

```bash
git diff
```

Stage selected changes:

```bash
git add \
    README.md \
    src/paper_watcher/__init__.py
```

Review staged changes:

```bash
git diff --staged
```

Commit:

```bash
git commit -m \
    "release: prepare v0.2.0"
```

Push:

```bash
git push
```

---

## Release `v0.2.0`

After final acceptance checks and a clean working tree:

```bash
git tag -a v0.2.0 \
    -m "Scientific Paper Watcher v0.2.0"
```

Push the tag:

```bash
git push origin v0.2.0
```

Verify:

```bash
git tag --list
```

---

## Current limitations

The current project deliberately remains small and understandable.

Not yet implemented:

- automatic scheduling with systemd
- e-mail or messaging notifications
- web UI
- full-text retrieval
- citation graph analysis
- DOI-based cross-source merging
- semantic similarity deduplication
- automated test suite with broad coverage
- CI release pipeline
- LLM summarization

These are potential future improvements rather than requirements for `v0.2.0`.

---

## Roadmap

### Next milestone

Run Scientific Paper Watcher automatically as a Linux service.

Potential next topics:

```text
systemd service
systemd timer
automatic restart
logs with journalctl
scheduled watcher execution
```

Future project improvements may include:

```text
automated tests
GitHub Actions
notifications
additional literature sources
better query management
report formats beyond Markdown
semantic analysis
```

---

## Design principles

Scientific Paper Watcher currently follows several principles that are useful beyond this project:

1. **Normalize external data early.**
2. **Keep storage identity explicit.**
3. **Persist state locally.**
4. **Separate CLI parsing from command handlers.**
5. **Isolate failures at the smallest useful level.**
6. **Make batch execution resilient.**
7. **Record operational warnings instead of silently hiding them.**
8. **Generate human-readable artifacts.**
9. **Prefer simple, inspectable components before adding complexity.**
10. **Treat a release as something that must be tested, documented, and reproducible.**

---

## License

This project is licensed under the MIT License.

See:

```text
LICENSE
```

for details.
