from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from paper_watcher.models import Paper
from paper_watcher.normalization import (
    normalize_doi,
    normalize_title,
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

PAPER_SOURCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_sources (
    id INTEGER PRIMARY KEY,
    paper_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    url TEXT,
    doi TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);
"""

PAPER_SOURCES_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS
    ux_paper_sources_source_external_id
ON paper_sources (
    source,
    external_id
);
"""

PAPERS_DOI_INDEX = """
CREATE INDEX IF NOT EXISTS
    ix_papers_doi
ON papers (
    doi
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
    merged_ids: list[int] = field(default_factory=list)
    merged_papers: list[Paper] = field(default_factory=list)

    @property
    def inserted_count(self) -> int:
        return len(
            self.inserted_ids
        )

    @property
    def merged_count(self) -> int:
        return len(
            self.merged_ids
        )

    @property
    def known_count(self) -> int:
        return (
            self.processed_count
            - self.inserted_count
            - self.merged_count
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

        connection.execute(
            PAPER_SOURCES_SCHEMA
        )

        connection.execute(
            PAPER_SOURCES_UNIQUE_INDEX
        )

        connection.execute(
            PAPERS_DOI_INDEX
        )

        connection.execute(
            """
            INSERT OR IGNORE INTO paper_sources (
                paper_id,
                source,
                external_id,
                url,
                doi,
                created_at
            )
            SELECT
                id,
                source,
                external_id,
                url,
                doi,
                created_at
            FROM papers
            """
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

    paper_id = cursor.lastrowid
    if paper_id is not None:
        connection.execute(
            """
            INSERT OR IGNORE INTO paper_sources (
                paper_id,
                source,
                external_id,
                url,
                doi
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                paper.source,
                paper.external_id,
                paper.url,
                normalize_doi(paper.doi),
            ),
        )

    return paper_id

def get_paper_id_by_identity(
    connection: sqlite3.Connection,
    paper: Paper,
) -> int | None:
    return find_paper_id_by_source_identity(
        connection,
        paper.source,
        paper.external_id,
    )

def find_paper_id_by_source_identity(
    connection: sqlite3.Connection,
    source: str,
    external_id: str,
) -> int | None:
    row = connection.execute(
        """
        SELECT paper_id
        FROM paper_sources
        WHERE source = ?
          AND external_id = ?
        """,
        (
            source,
            external_id,
        ),
    ).fetchone()

    if row is not None:
        return int(row["paper_id"])

    fallback = connection.execute(
        """
        SELECT id
        FROM papers
        WHERE source = ?
          AND external_id = ?
        """,
        (
            source,
            external_id,
        ),
    ).fetchone()

    if fallback is not None:
        return int(fallback["id"])

    return None

def find_paper_id_by_doi(
    connection: sqlite3.Connection,
    doi: str | None,
) -> int | None:
    norm_doi = normalize_doi(doi)

    if not norm_doi:
        return None

    row = connection.execute(
        """
        SELECT id
        FROM papers
        WHERE lower(trim(doi)) = ?
        """,
        (norm_doi,),
    ).fetchone()

    if row is not None:
        return int(row["id"])

    source_row = connection.execute(
        """
        SELECT paper_id
        FROM paper_sources
        WHERE lower(trim(doi)) = ?
        """,
        (norm_doi,),
    ).fetchone()

    if source_row is not None:
        return int(source_row["paper_id"])

    return None

def _extract_surnames(
    authors: list[str],
) -> set[str]:
    surnames = set()
    for author in authors:
        parts = author.strip().split()
        if parts:
            surnames.add(
                parts[-1].lower().rstrip(",.")
            )
    return surnames

def find_paper_id_by_title_and_author(
    connection: sqlite3.Connection,
    title: str,
    authors: list[str],
) -> int | None:
    norm_title = normalize_title(title)

    if len(norm_title) < 20:
        return None

    incoming_surnames = _extract_surnames(authors)

    rows = connection.execute(
        """
        SELECT id, title, authors
        FROM papers
        """
    ).fetchall()

    for row in rows:
        existing_title = normalize_title(row["title"])
        if existing_title == norm_title:
            try:
                existing_authors = json.loads(row["authors"])
                existing_surnames = _extract_surnames(existing_authors)
            except Exception:
                existing_surnames = set()

            if incoming_surnames and existing_surnames:
                if incoming_surnames.intersection(existing_surnames):
                    return int(row["id"])
            else:
                return int(row["id"])

    return None

def _enrich_paper_metadata(
    connection: sqlite3.Connection,
    paper_id: int,
    incoming: Paper,
) -> None:
    current = connection.execute(
        """
        SELECT doi, abstract, published, url
        FROM papers
        WHERE id = ?
        """,
        (paper_id,),
    ).fetchone()

    if current is None:
        return

    updates: list[str] = []
    values: list[str] = []

    if not current["doi"] and incoming.doi:
        norm = normalize_doi(incoming.doi)
        if norm:
            updates.append("doi = ?")
            values.append(norm)

    if not current["abstract"] and incoming.abstract:
        updates.append("abstract = ?")
        values.append(incoming.abstract)

    if not current["published"] and incoming.published:
        updates.append("published = ?")
        values.append(incoming.published)

    if updates:
        values.append(str(paper_id))
        sql = f"UPDATE papers SET {', '.join(updates)} WHERE id = ?"
        connection.execute(sql, tuple(values))

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
    merged_ids: list[int] = []
    merged_papers: list[Paper] = []

    for paper in papers:
        # 1. Ya conocido por id exacto de fuente
        existing_id = find_paper_id_by_source_identity(
            connection,
            paper.source,
            paper.external_id,
        )

        if existing_id is not None:
            if query is not None:
                record_paper_query_match(
                    connection,
                    existing_id,
                    query,
                )
            continue

        # 2. Coincidencia cross-source por DOI o Título+Autor
        matched_id = find_paper_id_by_doi(
            connection,
            paper.doi,
        )

        if matched_id is None:
            matched_id = find_paper_id_by_title_and_author(
                connection,
                paper.title,
                paper.authors,
            )

        if matched_id is not None:
            # Fusión cross-source con paper existente
            connection.execute(
                """
                INSERT OR IGNORE INTO paper_sources (
                    paper_id,
                    source,
                    external_id,
                    url,
                    doi
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    matched_id,
                    paper.source,
                    paper.external_id,
                    paper.url,
                    normalize_doi(paper.doi),
                ),
            )
            _enrich_paper_metadata(
                connection,
                matched_id,
                paper,
            )

            if query is not None:
                record_paper_query_match(
                    connection,
                    matched_id,
                    query,
                )

            merged_ids.append(matched_id)
            merged_p = get_paper_by_id(
                connection,
                matched_id,
            )
            if merged_p:
                merged_papers.append(merged_p)

        else:
            # 3. Artículo nuevo
            paper_id = insert_paper(
                connection,
                paper,
            )

            if paper_id is None:
                paper_id = get_paper_id_by_identity(
                    connection,
                    paper,
                )

            if paper_id is None:
                raise RuntimeError(
                    "Paper could not be resolved after insertion"
                )

            connection.execute(
                """
                INSERT OR IGNORE INTO paper_sources (
                    paper_id,
                    source,
                    external_id,
                    url,
                    doi
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    paper_id,
                    paper.source,
                    paper.external_id,
                    paper.url,
                    normalize_doi(paper.doi),
                ),
            )

            if query is not None:
                record_paper_query_match(
                    connection,
                    paper_id,
                    query,
                )

            inserted_ids.append(paper_id)
            new_p = get_paper_by_id(
                connection,
                paper_id,
            ) or paper
            new_papers.append(new_p)

    return InsertPapersResult(
        processed_count=len(papers),
        inserted_ids=inserted_ids,
        new_papers=new_papers,
        merged_ids=merged_ids,
        merged_papers=merged_papers,
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
    source_rows: list[sqlite3.Row] | None = None,
) -> Paper:
    if source_rows:
        sources = [
            s["source"]
            for s in source_rows
        ]
        external_ids = {
            s["source"]: s["external_id"]
            for s in source_rows
        }
        source_urls = {
            s["source"]: s["url"]
            for s in source_rows
            if s["url"]
        }
    else:
        sources = [row["source"]]
        external_ids = {
            row["source"]: row["external_id"]
        }
        source_urls = {
            row["source"]: row["url"]
        } if row["url"] else {}

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
        sources=sources,
        external_ids=external_ids,
        source_urls=source_urls,
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

    source_rows = connection.execute(
        """
        SELECT source, external_id, url, doi
        FROM paper_sources
        WHERE paper_id = ?
        ORDER BY id
        """,
        (paper_id,),
    ).fetchall()

    return _row_to_paper(
        row,
        source_rows,
    )

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
            COALESCE(
                (
                    SELECT GROUP_CONCAT(DISTINCT ps.source)
                    FROM paper_sources AS ps
                    WHERE ps.paper_id = p.id
                ),
                p.source
            ) AS sources,
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
            source=row["sources"].replace(",", ", "),
            url=row["url"],
        )
        for row in rows
    ]