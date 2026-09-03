from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest

from paper_watcher.models import Paper
from paper_watcher.storage.sqlite import (
    add_watch_query,
    count_papers,
    get_all_paper_report_rows,
    get_paper_by_id,
    initialize_database,
    insert_paper,
    insert_papers,
    list_watch_queries,
    list_watch_query_rows,
    record_paper_query_match,
    remove_watch_query,
)


class TestSqliteStorage:
    def test_database_initialization(self, temp_db_path: Path):
        con = sqlite3.connect(temp_db_path)
        cur = con.cursor()
        tables = {
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        con.close()
        assert "papers" in tables
        assert "watch_queries" in tables
        assert "paper_query_matches" in tables

    def test_insert_single_paper(self, db_connection: sqlite3.Connection, sample_paper: Paper):
        paper_id = insert_paper(db_connection, sample_paper)
        assert paper_id is not None
        assert count_papers(db_connection) == 1

        # Inserting duplicate should return None and not increment count
        dup_id = insert_paper(db_connection, sample_paper)
        assert dup_id is None
        assert count_papers(db_connection) == 1

    def test_get_paper_by_id(self, db_connection: sqlite3.Connection, sample_paper: Paper):
        paper_id = insert_paper(db_connection, sample_paper)
        assert paper_id is not None

        retrieved = get_paper_by_id(db_connection, paper_id)
        assert retrieved is not None
        assert retrieved.title == sample_paper.title
        assert retrieved.source == sample_paper.source
        assert retrieved.external_id == sample_paper.external_id
        assert retrieved.authors == sample_paper.authors
        assert retrieved.doi == sample_paper.doi

    def test_insert_papers_batch_with_provenance(
        self,
        db_connection: sqlite3.Connection,
        sample_paper: Paper,
        sample_arxiv_paper: Paper,
    ):
        query = "protein biosensors"
        res1 = insert_papers(
            db_connection,
            [sample_paper, sample_arxiv_paper],
            query=query,
        )
        assert res1.processed_count == 2
        assert res1.inserted_count == 2
        assert res1.known_count == 0
        assert len(res1.new_papers) == 2

        # Second run with same papers under a new query
        query2 = "molecular simulation"
        res2 = insert_papers(
            db_connection,
            [sample_paper, sample_arxiv_paper],
            query=query2,
        )
        assert res2.processed_count == 2
        assert res2.inserted_count == 0
        assert res2.known_count == 2
        assert len(res2.new_papers) == 0

        # Provenance should contain 4 records (2 papers x 2 queries)
        cur = db_connection.cursor()
        matches_count = cur.execute(
            "SELECT count(*) FROM paper_query_matches"
        ).fetchone()[0]
        assert matches_count == 4

    def test_watch_query_lifecycle_preserves_provenance(
        self,
        db_connection: sqlite3.Connection,
        sample_paper: Paper,
    ):
        # 1. Add watch query
        q_id = add_watch_query(db_connection, "protein engineering")
        assert q_id is not None

        # Duplicate watch query returns None
        assert add_watch_query(db_connection, "protein engineering") is None

        # Check list
        queries = list_watch_queries(db_connection)
        assert queries == ["protein engineering"]

        # 2. Match paper to query
        insert_papers(db_connection, [sample_paper], query="protein engineering")

        # 3. Remove watch query
        removed = remove_watch_query(db_connection, q_id)
        assert removed == "protein engineering"
        assert list_watch_queries(db_connection) == []

        # 4. Verify historical provenance is PRESERVED
        rows = get_all_paper_report_rows(db_connection)
        assert len(rows) == 1
        assert rows[0].query == "protein engineering"
        assert rows[0].title == sample_paper.title

