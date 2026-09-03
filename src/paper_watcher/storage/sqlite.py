from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
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

PAPER_QUERY_MATCHES_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_query_matches (
    paper_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (paper_id, query),

    FOREIGN KEY (paper_id)
        REFERENCES papers(id)
        ON DELETE CASCADE
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

@dataclass(frozen=True)
class PaperReportRow:
    query: str | None
    title: str
    authors: list[str]
    source: str
    url: str | None

@dataclass
class InsertPapersResult:
    processed_count: int
    inserted_ids: list[int]
    new_papers: list[Paper]

    @property
    def inserted_count(self) -> int:
        return len(
            self.inserted_ids
        )

    @property
    def known_count(self) -> int:
        return (
            self.processed_count
            - self.inserted_count
        )

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

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

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

        connection.execute(
            PAPER_QUERY_MATCHES_SCHEMA
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

def get_paper_id_by_identity(
    connection: sqlite3.Connection,
    paper: Paper,
) -> int | None:
    row = connection.execute(
        """
        SELECT id
        FROM papers
        WHERE source = ?
          AND external_id = ?
        """,
        (
            paper.source,
            paper.external_id,
        ),
    ).fetchone()

    if row is None:
        return None

    return int(
        row["id"]
    )

def record_paper_query_match(
    connection: sqlite3.Connection,
    paper_id: int,
    query: str,
) -> bool:
    cleaned_query = query.strip()

    if not cleaned_query:
        raise ValueError(
            "Query cannot be empty"
        )

    cursor = connection.execute(
        """
        INSERT OR IGNORE
        INTO paper_query_matches (
            paper_id,
            query
        )
        VALUES (?, ?)
        """,
        (
            paper_id,
            cleaned_query,
        ),
    )

    return cursor.rowcount > 0

def insert_papers(
    connection: sqlite3.Connection,
    papers: list[Paper],
    query: str | None = None,
) -> InsertPapersResult:
    inserted_ids: list[int] = []
    new_papers: list[Paper] = []

    for paper in papers:
        paper_id = insert_paper(
            connection,
            paper,
        )

        if paper_id is not None:
            inserted_ids.append(
                paper_id
            )

            new_papers.append(
                paper
            )

        else:
            paper_id = get_paper_id_by_identity(
                connection,
                paper,
            )

        if paper_id is None:
            raise RuntimeError(
                "Paper could not be resolved "
                "after insertion"
            )

        if query is not None:
            record_paper_query_match(
                connection,
                paper_id,
                query,
            )

    return InsertPapersResult(
        processed_count=len(papers),
        inserted_ids=inserted_ids,
        new_papers=new_papers,
    )

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

def remove_watch_query(
    connection: sqlite3.Connection,
    query_id: int,
) -> str | None:
    row = connection.execute(
        """
        SELECT query
        FROM watch_queries
        WHERE id = ?
        """,
        (
            query_id,
        ),
    ).fetchone()

    if row is None:
        return None

    query = str(
        row["query"]
    )

    connection.execute(
        """
        DELETE FROM watch_queries
        WHERE id = ?
        """,
        (
            query_id,
        ),
    )

    return query

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

def get_all_paper_report_rows(
    connection: sqlite3.Connection,
) -> list[PaperReportRow]:
    rows = connection.execute(
        """
        SELECT
            pqm.query AS query,
            p.title AS title,
            p.authors AS authors,
            p.source AS source,
            p.url AS url
        FROM papers AS p
        LEFT JOIN paper_query_matches AS pqm
            ON pqm.paper_id = p.id
        ORDER BY
            CASE
                WHEN pqm.query IS NULL THEN 1
                ELSE 0
            END,
            pqm.query,
            p.title
        """
    ).fetchall()

    return [
        PaperReportRow(
            query=row["query"],
            title=row["title"],
            authors=json.loads(
                row["authors"]
            ),
            source=row["source"],
            url=row["url"],
        )
        for row in rows
    ]