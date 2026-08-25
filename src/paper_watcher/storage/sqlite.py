from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from paper_watcher.models import Paper

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

def insert_paper(
    connection: sqlite3.Connection,
    paper: Paper,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO papers (
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
            paper.doi,
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

    return cursor.lastrowid

def insert_papers(
    connection: sqlite3.Connection,
    papers: list[Paper],
) -> list[int]:
    paper_ids: list[int] = []

    for paper in papers:
        paper_id = insert_paper(
            connection,
            paper,
        )

        paper_ids.append(
            paper_id
        )

    return paper_ids

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

