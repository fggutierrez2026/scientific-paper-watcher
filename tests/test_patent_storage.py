from __future__ import annotations

import sqlite3
from pathlib import Path

from paper_watcher.models import Paper, Patent
from paper_watcher.storage.sqlite import (
    count_patents,
    get_patent_by_id,
    initialize_database,
    insert_paper,
    insert_patent,
    insert_patents,
    link_paper_to_patent,
)


def test_patent_tables_are_created(temp_db_path: Path) -> None:
    connection = sqlite3.connect(temp_db_path)
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    connection.close()

    assert {
        "patents",
        "patent_sources",
        "patent_query_matches",
        "patent_families",
        "paper_patent_links",
    } <= tables


def test_patent_insert_is_idempotent(
    db_connection: sqlite3.Connection,
    sample_patent: Patent,
) -> None:
    patent_id = insert_patent(db_connection, sample_patent)
    assert patent_id is not None
    assert insert_patent(db_connection, sample_patent) is None
    assert count_patents(db_connection) == 1


def test_patent_identity_is_normalized_and_merges_source_metadata(
    db_connection: sqlite3.Connection,
    sample_patent: Patent,
) -> None:
    first = Patent(
        **{
            **sample_patent.__dict__,
            "abstract": None,
            "applicants": [],
            "citations": [],
            "family_id": None,
        }
    )
    first_result = insert_patents(db_connection, [first], query="protein sensor")

    second = Patent(
        **{
            **sample_patent.__dict__,
            "source": "epo",
            "external_id": "epo-US20260123456-A1",
            "publication_number": "us-2026-0123456-a1",
            "url": "https://example.org/epo/US20260123456A1",
        }
    )
    second_result = insert_patents(db_connection, [second], query="biosensor")

    assert first_result.inserted_count == 1
    assert second_result.merged_count == 1
    assert count_patents(db_connection) == 1

    stored = get_patent_by_id(db_connection, first_result.inserted_ids[0])
    assert stored is not None
    assert stored.publication_number == "US20260123456A1"
    assert stored.application_number == "US18123456"
    assert stored.abstract == sample_patent.abstract
    assert stored.applicants == sample_patent.applicants
    assert stored.family_id == sample_patent.family_id
    assert set(stored.sources) == {"lens", "epo"}
    assert stored.external_ids["epo"] == "epo-US20260123456-A1"

    matches = db_connection.execute(
        "SELECT query FROM patent_query_matches ORDER BY query"
    ).fetchall()
    assert [row["query"] for row in matches] == ["biosensor", "protein sensor"]


def test_application_number_is_used_as_identity_fallback(
    db_connection: sqlite3.Connection,
    sample_patent: Patent,
) -> None:
    application_only = Patent(
        **{
            **sample_patent.__dict__,
            "publication_number": None,
            "family_id": None,
        }
    )
    patent_id = insert_patent(db_connection, application_only)
    assert patent_id is not None

    result = insert_patents(
        db_connection,
        [
            Patent(
                **{
                    **sample_patent.__dict__,
                    "source": "uspto",
                    "external_id": "uspto-18123456",
                }
            )
        ],
    )
    assert result.merged_ids == [patent_id]
    assert count_patents(db_connection) == 1
    stored = get_patent_by_id(db_connection, patent_id)
    assert stored is not None
    assert stored.publication_number == "US20260123456A1"


def test_family_members_are_linked_without_being_merged(
    db_connection: sqlite3.Connection,
    sample_patent: Patent,
) -> None:
    european_member = Patent(
        **{
            **sample_patent.__dict__,
            "source": "epo",
            "external_id": "EP-456789-A1",
            "jurisdiction": "EP",
            "publication_number": "EP456789A1",
            "application_number": "EP25123456",
        }
    )
    result = insert_patents(db_connection, [sample_patent, european_member])

    assert result.inserted_count == 2
    assert count_patents(db_connection) == 2
    family_rows = db_connection.execute(
        """
        SELECT patent_families.family_id, COUNT(patents.id) AS members
        FROM patent_families
        JOIN patents ON patents.family_id = patent_families.id
        GROUP BY patent_families.family_id
        """
    ).fetchall()
    assert [(row["family_id"], row["members"]) for row in family_rows] == [
        ("DOCDB-123456", 2)
    ]


def test_verified_paper_patent_links_are_idempotent(
    db_connection: sqlite3.Connection,
    sample_paper: Paper,
    sample_patent: Patent,
) -> None:
    paper_id = insert_paper(db_connection, sample_paper)
    patent_id = insert_patent(db_connection, sample_patent)
    assert paper_id is not None
    assert patent_id is not None

    link_id = link_paper_to_patent(
        db_connection,
        paper_id,
        patent_id,
        relationship="cites",
        source="lens",
        source_url="https://example.org/evidence/1",
    )
    duplicate_id = link_paper_to_patent(
        db_connection,
        paper_id,
        patent_id,
        relationship="cites",
        source="lens",
    )

    assert link_id is not None
    assert duplicate_id is None
    assert db_connection.execute(
        "SELECT COUNT(*) FROM paper_patent_links"
    ).fetchone()[0] == 1


def test_v040_database_is_migrated_additively(tmp_path: Path) -> None:
    database_path = tmp_path / "v040.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE papers (
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
        CREATE TABLE watch_queries (
            id INTEGER PRIMARY KEY,
            query TEXT NOT NULL,
            last_checked_at TEXT
        );
        INSERT INTO papers (
            source, external_id, title, authors, topics
        ) VALUES ('pubmed', '42', 'Existing paper', '[]', '[]');
        """
    )
    connection.commit()
    connection.close()

    initialize_database(database_path)

    connection = sqlite3.connect(database_path)
    assert connection.execute("SELECT title FROM papers").fetchone()[0] == (
        "Existing paper"
    )
    assert connection.execute("SELECT COUNT(*) FROM patents").fetchone()[0] == 0
    connection.close()
