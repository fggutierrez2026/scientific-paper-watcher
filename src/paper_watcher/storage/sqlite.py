from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from paper_watcher.models import Paper

from paper_watcher.normalization import (
    normalize_doi,
)

PAPERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    doi TEXT,
    title TEXT NOT NULL,
    abstract TEXT,
    authors TEXT NOT NULL,
    published TEXT,
    url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

WATCH_QUERIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS watch_queries (
    id INTEGER PRIMARY KEY,
    query TEXT NOT NULL
);
"""

WATCH_QUERIES_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS
    ux_watch_queries_query
ON watch_queries (
    query
);
"""


# A paper is uniquely identified inside a source by
# (source, external_id).
#
# DOI is intentionally not UNIQUE because the same
# scholarly work may appear in more than one source,
# for example PubMed and arXiv.
#
# Normalized titles are used only as a secondary
# matching signal and are not safe as a hard
# database uniqueness constraint.

PAPERS_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS
    ux_papers_source_external_id
ON papers (
    source,
    external_id
);
"""


@contextmanager
def database_connection(
    database_path: Path,
) -> Generator[sqlite3.Connection, None, None]:
    connection = connect_database(
        database_path
    )

    try:
        with connection:
            yield connection

    finally:
        connection.close()

def connect_database(
    database_path: Path,
) -> sqlite3.Connection:
    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        database_path
    )

    connection.row_factory = sqlite3.Row

    return connection

def initialize_database(
    database_path: Path,
) -> None:
    with database_connection(
        database_path
    ) as connection:

        connection.execute(
            PAPERS_SCHEMA
        )

        connection.execute(
            PAPERS_UNIQUE_INDEX
        )

        connection.execute(
            WATCH_QUERIES_SCHEMA
        )

        connection.execute(
            WATCH_QUERIES_UNIQUE_INDEX
        )

def insert_paper(
    connection: sqlite3.Connection,
    paper: Paper,
) -> int | None:
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO papers (
            source,
            external_id,
            doi,
            title,
            abstract,
            authors,
            published,
            url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            paper.source,
            paper.external_id,
            normalize_doi(
                paper.doi
            ),
            paper.title,
            paper.abstract,
            json.dumps(
                paper.authors,
                ensure_ascii=False,
            ),
            paper.published,
            paper.url,
        ),
    )

    if cursor.rowcount == 0:
        return None

    return cursor.lastrowid

def insert_papers(
    connection: sqlite3.Connection,
    papers: list[Paper],
) -> list[int]:
    inserted_ids: list[int] = []

    for paper in papers:
        paper_id = insert_paper(
            connection,
            paper,
        )

        if paper_id is not None:
            inserted_ids.append(
                paper_id
            )

    return inserted_ids

def count_papers(
    connection: sqlite3.Connection,
) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM papers
        """
    ).fetchone()

    return int(
        row["count"]
    )

def _row_to_paper(
    row: sqlite3.Row,
) -> Paper:
    return Paper(
        source=row["source"],
        external_id=row["external_id"],
        title=row["title"],
        authors=json.loads(
            row["authors"]
        ),
        abstract=row["abstract"],
        journal=None,
        publication_date=row["published"],
        electronic_date=None,
        pubmed_date=None,
        doi=row["doi"],
        url=row["url"],
    )

def get_paper_by_id(
    connection: sqlite3.Connection,
    paper_id: int,
) -> Paper | None:
    row = connection.execute(
        """
        SELECT
            source,
            external_id,
            doi,
            title,
            abstract,
            authors,
            published,
            url
        FROM papers
        WHERE id = ?
        """,
        (paper_id,),
    ).fetchone()

    if row is None:
        return None

    return _row_to_paper(row)

def add_watch_query(
    connection: sqlite3.Connection,
    query: str,
) -> int | None:
    cleaned_query = query.strip()

    if not cleaned_query:
        raise ValueError(
            "Watch query cannot be empty"
        )

    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO watch_queries (
            query
        )
        VALUES (?)
        """,
        (
            cleaned_query,
        ),
    )

    if cursor.rowcount == 0:
        return None

    return cursor.lastrowid

def list_watch_queries(
    connection: sqlite3.Connection,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT query
        FROM watch_queries
        ORDER BY id
        """
    ).fetchall()

    return [
        row["query"]
        for row in rows
    ]

def list_watch_query_rows(
    connection: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            id,
            query
        FROM watch_queries
        ORDER BY id
        """
    ).fetchall()