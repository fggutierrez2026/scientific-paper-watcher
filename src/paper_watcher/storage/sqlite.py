from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from paper_watcher.models import Paper, Patent
from paper_watcher.normalization import (
    normalize_doi,
    normalize_patent_jurisdiction,
    normalize_patent_number,
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
    openalex_id TEXT,
    citation_count INTEGER,
    topics TEXT NOT NULL DEFAULT '[]',
    pdf_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

WATCH_QUERIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS watch_queries (
    id INTEGER PRIMARY KEY,
    query TEXT NOT NULL,
    last_checked_at TEXT,
    scope TEXT NOT NULL DEFAULT 'papers'
        CHECK (scope IN ('papers', 'patents', 'all'))
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
    query,
    scope
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

PATENT_FAMILIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS patent_families (
    id INTEGER PRIMARY KEY,
    family_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

PATENT_FAMILIES_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS
    ux_patent_families_family_id
ON patent_families (
    family_id
);
"""

PATENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS patents (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    publication_number TEXT,
    application_number TEXT,
    title TEXT NOT NULL,
    abstract TEXT,
    inventors TEXT NOT NULL DEFAULT '[]',
    applicants TEXT NOT NULL DEFAULT '[]',
    priority_date TEXT,
    publication_date TEXT,
    cpc_codes TEXT NOT NULL DEFAULT '[]',
    ipc_codes TEXT NOT NULL DEFAULT '[]',
    family_id INTEGER,
    citations TEXT NOT NULL DEFAULT '[]',
    url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (publication_number IS NOT NULL OR application_number IS NOT NULL),
    FOREIGN KEY (family_id) REFERENCES patent_families(id) ON DELETE SET NULL
);
"""

PATENTS_PUBLICATION_IDENTITY_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS
    ux_patents_jurisdiction_publication
ON patents (
    jurisdiction,
    publication_number
)
WHERE publication_number IS NOT NULL;
"""

PATENTS_APPLICATION_INDEX = """
CREATE INDEX IF NOT EXISTS
    ix_patents_jurisdiction_application
ON patents (
    jurisdiction,
    application_number
);
"""

PATENT_SOURCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS patent_sources (
    id INTEGER PRIMARY KEY,
    patent_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    publication_number TEXT,
    application_number TEXT,
    url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patent_id) REFERENCES patents(id) ON DELETE CASCADE
);
"""

PATENT_SOURCES_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS
    ux_patent_sources_source_external_id
ON patent_sources (
    source,
    external_id
);
"""

PATENT_QUERY_MATCHES_SCHEMA = """
CREATE TABLE IF NOT EXISTS patent_query_matches (
    patent_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (patent_id, query),
    FOREIGN KEY (patent_id) REFERENCES patents(id) ON DELETE CASCADE
);
"""

PAPER_PATENT_LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_patent_links (
    id INTEGER PRIMARY KEY,
    paper_id INTEGER NOT NULL,
    patent_id INTEGER NOT NULL,
    relationship TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    FOREIGN KEY (patent_id) REFERENCES patents(id) ON DELETE CASCADE
);
"""

PAPER_PATENT_LINKS_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS
    ux_paper_patent_links_evidence
ON paper_patent_links (
    paper_id,
    patent_id,
    relationship,
    source
);
"""

@dataclass(frozen=True)
class PaperReportRow:
    query: str | None
    title: str
    authors: list[str]
    source: str
    url: str | None


@dataclass(frozen=True)
class DetailedPaperReportRow:
    paper: Paper
    queries: list[str]


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


@dataclass
class InsertPatentsResult:
    processed_count: int
    inserted_ids: list[int]
    new_patents: list[Patent]
    merged_ids: list[int] = field(default_factory=list)
    merged_patents: list[Patent] = field(default_factory=list)

    @property
    def inserted_count(self) -> int:
        return len(self.inserted_ids)

    @property
    def merged_count(self) -> int:
        return len(self.merged_ids)

    @property
    def known_count(self) -> int:
        return self.processed_count - self.inserted_count - self.merged_count

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

        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(papers)").fetchall()
        }
        enrichment_columns = {
            "openalex_id": "TEXT",
            "citation_count": "INTEGER",
            "topics": "TEXT NOT NULL DEFAULT '[]'",
            "pdf_url": "TEXT",
        }
        for column_name, column_type in enrichment_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE papers ADD COLUMN {column_name} {column_type}"
                )

        connection.execute(
            PAPERS_UNIQUE_INDEX
        )

        connection.execute(
            WATCH_QUERIES_SCHEMA
        )

        watch_query_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(watch_queries)"
            ).fetchall()
        }
        if "last_checked_at" not in watch_query_columns:
            connection.execute(
                "ALTER TABLE watch_queries ADD COLUMN last_checked_at TEXT"
            )
        if "scope" not in watch_query_columns:
            connection.execute(
                "ALTER TABLE watch_queries "
                "ADD COLUMN scope TEXT NOT NULL DEFAULT 'papers'"
            )

        connection.execute("DROP INDEX IF EXISTS ux_watch_queries_query")
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

        connection.execute(PATENT_FAMILIES_SCHEMA)
        connection.execute(PATENT_FAMILIES_UNIQUE_INDEX)
        connection.execute(PATENTS_SCHEMA)
        connection.execute(PATENTS_PUBLICATION_IDENTITY_INDEX)
        connection.execute(PATENTS_APPLICATION_INDEX)
        connection.execute(PATENT_SOURCES_SCHEMA)
        connection.execute(PATENT_SOURCES_UNIQUE_INDEX)
        connection.execute(PATENT_QUERY_MATCHES_SCHEMA)
        connection.execute(PAPER_PATENT_LINKS_SCHEMA)
        connection.execute(PAPER_PATENT_LINKS_UNIQUE_INDEX)

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
            url,
            openalex_id,
            citation_count,
            topics,
            pdf_url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            paper.openalex_id,
            paper.citation_count,
            json.dumps(paper.topics, ensure_ascii=False),
            paper.pdf_url,
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


def find_paper_id_by_external_identifiers(
    connection: sqlite3.Connection,
    paper: Paper,
) -> int | None:
    """Resolve cross-source IDs supplied by discovery aggregators."""
    identifiers = (
        ("pubmed", paper.external_ids.get("pmid")),
        ("arxiv", paper.external_ids.get("arxiv")),
    )
    for source, external_id in identifiers:
        if not external_id:
            continue
        if source == "arxiv":
            row = connection.execute(
                """
                SELECT paper_id
                FROM paper_sources
                WHERE source = ?
                  AND (external_id = ? OR external_id LIKE ?)
                ORDER BY id
                LIMIT 1
                """,
                (source, external_id, f"{external_id}v%"),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT paper_id
                FROM paper_sources
                WHERE source = ? AND external_id = ?
                ORDER BY id
                LIMIT 1
                """,
                (source, external_id),
            ).fetchone()
        if row is not None:
            return int(row["paper_id"])
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
        SELECT
            doi,
            abstract,
            published,
            url,
            openalex_id,
            citation_count,
            topics,
            pdf_url
        FROM papers
        WHERE id = ?
        """,
        (paper_id,),
    ).fetchone()

    if current is None:
        return

    updates: list[str] = []
    values: list[object] = []

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

    if incoming.openalex_id and current["openalex_id"] != incoming.openalex_id:
        updates.append("openalex_id = ?")
        values.append(incoming.openalex_id)

    if (
        incoming.citation_count is not None
        and current["citation_count"] != incoming.citation_count
    ):
        updates.append("citation_count = ?")
        values.append(incoming.citation_count)

    if incoming.topics:
        serialized_topics = json.dumps(incoming.topics, ensure_ascii=False)
        if current["topics"] != serialized_topics:
            updates.append("topics = ?")
            values.append(serialized_topics)

    if incoming.pdf_url and current["pdf_url"] != incoming.pdf_url:
        updates.append("pdf_url = ?")
        values.append(incoming.pdf_url)

    if updates:
        values.append(paper_id)
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
            _enrich_paper_metadata(connection, existing_id, paper)
            if query is not None:
                record_paper_query_match(
                    connection,
                    existing_id,
                    query,
                )
            continue

        # 2. Coincidencia cross-source por DOI o Título+Autor
        matched_id = find_paper_id_by_external_identifiers(connection, paper)

        if matched_id is None:
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
        openalex_id=row["openalex_id"],
        citation_count=row["citation_count"],
        topics=json.loads(row["topics"] or "[]"),
        pdf_url=row["pdf_url"],
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
            url,
            openalex_id,
            citation_count,
            topics,
            pdf_url
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
    scope: str = "papers",
) -> int | None:
    cleaned_query = query.strip()
    cleaned_scope = scope.strip().lower()

    if not cleaned_query:
        raise ValueError(
            "Watch query cannot be empty"
        )
    if cleaned_scope not in {"papers", "patents", "all"}:
        raise ValueError("Watch query scope must be papers, patents, or all")

    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO watch_queries (
            query,
            scope
        )
        VALUES (?, ?)
        """,
        (
            cleaned_query,
            cleaned_scope,
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
            query,
            last_checked_at,
            scope
        FROM watch_queries
        ORDER BY id
        """
    ).fetchall()


def update_watch_query_last_checked(
    connection: sqlite3.Connection,
    query_id: int,
    checked_at: datetime,
) -> bool:
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=UTC)
    else:
        checked_at = checked_at.astimezone(UTC)

    cursor = connection.execute(
        """
        UPDATE watch_queries
        SET last_checked_at = ?
        WHERE id = ?
        """,
        (
            checked_at.isoformat(timespec="seconds"),
            query_id,
        ),
    )
    return cursor.rowcount > 0

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


def get_all_detailed_paper_report_rows(
    connection: sqlite3.Connection,
) -> list[DetailedPaperReportRow]:
    paper_rows = connection.execute(
        """
        SELECT
            id,
            source,
            external_id,
            doi,
            title,
            abstract,
            authors,
            published,
            url,
            openalex_id,
            citation_count,
            topics,
            pdf_url
        FROM papers
        ORDER BY title
        """
    ).fetchall()
    source_rows = connection.execute(
        """
        SELECT paper_id, source, external_id, url, doi
        FROM paper_sources
        ORDER BY paper_id, id
        """
    ).fetchall()
    query_rows = connection.execute(
        """
        SELECT paper_id, query
        FROM paper_query_matches
        ORDER BY paper_id, query
        """
    ).fetchall()

    sources_by_paper: dict[int, list[sqlite3.Row]] = {}
    for row in source_rows:
        sources_by_paper.setdefault(row["paper_id"], []).append(row)

    queries_by_paper: dict[int, list[str]] = {}
    for row in query_rows:
        queries_by_paper.setdefault(row["paper_id"], []).append(row["query"])

    return [
        DetailedPaperReportRow(
            paper=_row_to_paper(
                row,
                sources_by_paper.get(row["id"]),
            ),
            queries=queries_by_paper.get(row["id"], []),
        )
        for row in paper_rows
    ]


def _get_or_create_patent_family(
    connection: sqlite3.Connection,
    family_id: str | None,
) -> int | None:
    if family_id is None or not family_id.strip():
        return None

    cleaned_family_id = family_id.strip()
    connection.execute(
        "INSERT OR IGNORE INTO patent_families (family_id) VALUES (?)",
        (cleaned_family_id,),
    )
    row = connection.execute(
        "SELECT id FROM patent_families WHERE family_id = ?",
        (cleaned_family_id,),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def find_patent_id_by_source_identity(
    connection: sqlite3.Connection,
    source: str,
    external_id: str,
) -> int | None:
    row = connection.execute(
        """
        SELECT patent_id
        FROM patent_sources
        WHERE source = ? AND external_id = ?
        """,
        (source, external_id),
    ).fetchone()
    if row is not None:
        return int(row["patent_id"])

    fallback = connection.execute(
        """
        SELECT id
        FROM patents
        WHERE source = ? AND external_id = ?
        """,
        (source, external_id),
    ).fetchone()
    return int(fallback["id"]) if fallback is not None else None


def find_patent_id_by_identity(
    connection: sqlite3.Connection,
    patent: Patent,
) -> int | None:
    jurisdiction = normalize_patent_jurisdiction(patent.jurisdiction)
    publication_number = normalize_patent_number(patent.publication_number)
    application_number = normalize_patent_number(patent.application_number)

    if publication_number is not None:
        row = connection.execute(
            """
            SELECT id
            FROM patents
            WHERE jurisdiction = ? AND publication_number = ?
            """,
            (jurisdiction, publication_number),
        ).fetchone()
        if row is not None:
            return int(row["id"])

    if application_number is None:
        return None

    # Application numbers are a fallback only. Two records that already have
    # different publication numbers remain distinct legal documents.
    row = connection.execute(
        """
        SELECT id
        FROM patents
        WHERE jurisdiction = ?
          AND application_number = ?
          AND (? IS NULL OR publication_number IS NULL)
        ORDER BY id
        LIMIT 1
        """,
        (jurisdiction, application_number, publication_number),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def _record_patent_source(
    connection: sqlite3.Connection,
    patent_id: int,
    patent: Patent,
) -> None:
    connection.execute(
        """
        INSERT INTO patent_sources (
            patent_id,
            source,
            external_id,
            publication_number,
            application_number,
            url
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, external_id) DO UPDATE SET
            publication_number = COALESCE(
                excluded.publication_number,
                patent_sources.publication_number
            ),
            application_number = COALESCE(
                excluded.application_number,
                patent_sources.application_number
            ),
            url = COALESCE(excluded.url, patent_sources.url),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            patent_id,
            patent.source,
            patent.external_id,
            normalize_patent_number(patent.publication_number),
            normalize_patent_number(patent.application_number),
            patent.url,
        ),
    )


def _merge_string_lists(current: str | None, incoming: list[str]) -> str:
    existing = json.loads(current or "[]")
    merged = list(existing)
    seen = {str(value).casefold() for value in existing}
    for value in incoming:
        cleaned = value.strip()
        if cleaned and cleaned.casefold() not in seen:
            merged.append(cleaned)
            seen.add(cleaned.casefold())
    return json.dumps(merged, ensure_ascii=False)


def _merge_patent_metadata(
    connection: sqlite3.Connection,
    patent_id: int,
    incoming: Patent,
) -> None:
    current = connection.execute(
        "SELECT * FROM patents WHERE id = ?",
        (patent_id,),
    ).fetchone()
    if current is None:
        return

    publication_number = normalize_patent_number(incoming.publication_number)
    application_number = normalize_patent_number(incoming.application_number)
    family_key = _get_or_create_patent_family(connection, incoming.family_id)
    updates: dict[str, object] = {}

    for column, value in (
        ("publication_number", publication_number),
        ("application_number", application_number),
        ("url", incoming.url),
    ):
        if not current[column] and value:
            updates[column] = value

    if incoming.abstract and (
        not current["abstract"] or len(incoming.abstract) > len(current["abstract"])
    ):
        updates["abstract"] = incoming.abstract

    if incoming.priority_date and (
        not current["priority_date"]
        or incoming.priority_date < current["priority_date"]
    ):
        updates["priority_date"] = incoming.priority_date

    if not current["publication_date"] and incoming.publication_date:
        updates["publication_date"] = incoming.publication_date

    if current["family_id"] is None and family_key is not None:
        updates["family_id"] = family_key

    for column, values in (
        ("inventors", incoming.inventors),
        ("applicants", incoming.applicants),
        ("cpc_codes", incoming.cpc_codes),
        ("ipc_codes", incoming.ipc_codes),
        ("citations", incoming.citations),
    ):
        merged = _merge_string_lists(current[column], values)
        if merged != current[column]:
            updates[column] = merged

    if updates:
        updates["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        assignments = ", ".join(f"{column} = ?" for column in updates)
        connection.execute(
            f"UPDATE patents SET {assignments} WHERE id = ?",
            (*updates.values(), patent_id),
        )


def _insert_new_patent(
    connection: sqlite3.Connection,
    patent: Patent,
) -> int:
    jurisdiction = normalize_patent_jurisdiction(patent.jurisdiction)
    publication_number = normalize_patent_number(patent.publication_number)
    application_number = normalize_patent_number(patent.application_number)
    family_key = _get_or_create_patent_family(connection, patent.family_id)
    cursor = connection.execute(
        """
        INSERT INTO patents (
            source,
            external_id,
            jurisdiction,
            publication_number,
            application_number,
            title,
            abstract,
            inventors,
            applicants,
            priority_date,
            publication_date,
            cpc_codes,
            ipc_codes,
            family_id,
            citations,
            url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            patent.source,
            patent.external_id,
            jurisdiction,
            publication_number,
            application_number,
            patent.title,
            patent.abstract,
            json.dumps(patent.inventors, ensure_ascii=False),
            json.dumps(patent.applicants, ensure_ascii=False),
            patent.priority_date,
            patent.publication_date,
            json.dumps(patent.cpc_codes, ensure_ascii=False),
            json.dumps(patent.ipc_codes, ensure_ascii=False),
            family_key,
            json.dumps(patent.citations, ensure_ascii=False),
            patent.url,
        ),
    )
    patent_id = cursor.lastrowid
    if patent_id is None:
        raise RuntimeError("Patent insertion did not return an id")
    _record_patent_source(connection, patent_id, patent)
    return patent_id


def record_patent_query_match(
    connection: sqlite3.Connection,
    patent_id: int,
    query: str,
) -> bool:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("Query cannot be empty")
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO patent_query_matches (patent_id, query)
        VALUES (?, ?)
        """,
        (patent_id, cleaned_query),
    )
    return cursor.rowcount > 0


def insert_patents(
    connection: sqlite3.Connection,
    patents: list[Patent],
    query: str | None = None,
) -> InsertPatentsResult:
    inserted_ids: list[int] = []
    new_patents: list[Patent] = []
    merged_ids: list[int] = []
    merged_patents: list[Patent] = []

    for patent in patents:
        source_id = find_patent_id_by_source_identity(
            connection, patent.source, patent.external_id
        )
        if source_id is not None:
            _merge_patent_metadata(connection, source_id, patent)
            _record_patent_source(connection, source_id, patent)
            if query is not None:
                record_patent_query_match(connection, source_id, query)
            continue

        matched_id = find_patent_id_by_identity(connection, patent)
        if matched_id is not None:
            _merge_patent_metadata(connection, matched_id, patent)
            _record_patent_source(connection, matched_id, patent)
            if query is not None:
                record_patent_query_match(connection, matched_id, query)
            merged_ids.append(matched_id)
            merged = get_patent_by_id(connection, matched_id)
            if merged is not None:
                merged_patents.append(merged)
            continue

        patent_id = _insert_new_patent(connection, patent)
        if query is not None:
            record_patent_query_match(connection, patent_id, query)
        inserted_ids.append(patent_id)
        new_patents.append(get_patent_by_id(connection, patent_id) or patent)

    return InsertPatentsResult(
        processed_count=len(patents),
        inserted_ids=inserted_ids,
        new_patents=new_patents,
        merged_ids=merged_ids,
        merged_patents=merged_patents,
    )


def insert_patent(
    connection: sqlite3.Connection,
    patent: Patent,
) -> int | None:
    result = insert_patents(connection, [patent])
    return result.inserted_ids[0] if result.inserted_ids else None


def _row_to_patent(
    row: sqlite3.Row,
    source_rows: list[sqlite3.Row],
) -> Patent:
    sources = [source_row["source"] for source_row in source_rows]
    external_ids = {
        source_row["source"]: source_row["external_id"]
        for source_row in source_rows
    }
    source_urls = {
        source_row["source"]: source_row["url"]
        for source_row in source_rows
        if source_row["url"]
    }
    return Patent(
        source=row["source"],
        external_id=row["external_id"],
        jurisdiction=row["jurisdiction"],
        publication_number=row["publication_number"],
        application_number=row["application_number"],
        title=row["title"],
        abstract=row["abstract"],
        inventors=json.loads(row["inventors"] or "[]"),
        applicants=json.loads(row["applicants"] or "[]"),
        priority_date=row["priority_date"],
        publication_date=row["publication_date"],
        cpc_codes=json.loads(row["cpc_codes"] or "[]"),
        ipc_codes=json.loads(row["ipc_codes"] or "[]"),
        family_id=row["family_identifier"],
        citations=json.loads(row["citations"] or "[]"),
        url=row["url"],
        sources=sources or [row["source"]],
        external_ids=external_ids or {row["source"]: row["external_id"]},
        source_urls=source_urls,
    )


def get_patent_by_id(
    connection: sqlite3.Connection,
    patent_id: int,
) -> Patent | None:
    row = connection.execute(
        """
        SELECT patents.*, patent_families.family_id AS family_identifier
        FROM patents
        LEFT JOIN patent_families ON patent_families.id = patents.family_id
        WHERE patents.id = ?
        """,
        (patent_id,),
    ).fetchone()
    if row is None:
        return None
    source_rows = connection.execute(
        """
        SELECT source, external_id, url
        FROM patent_sources
        WHERE patent_id = ?
        ORDER BY id
        """,
        (patent_id,),
    ).fetchall()
    return _row_to_patent(row, source_rows)


def count_patents(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) AS count FROM patents").fetchone()
    return int(row["count"])


def link_paper_to_patent(
    connection: sqlite3.Connection,
    paper_id: int,
    patent_id: int,
    relationship: str,
    source: str,
    source_url: str | None = None,
) -> int | None:
    cleaned_relationship = relationship.strip()
    cleaned_source = source.strip()
    if not cleaned_relationship or not cleaned_source:
        raise ValueError("Relationship and source cannot be empty")
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO paper_patent_links (
            paper_id, patent_id, relationship, source, source_url
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (paper_id, patent_id, cleaned_relationship, cleaned_source, source_url),
    )
    return cursor.lastrowid if cursor.rowcount > 0 else None
