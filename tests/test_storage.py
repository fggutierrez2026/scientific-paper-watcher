from __future__ import annotations

import sqlite3
from pathlib import Path

from paper_watcher.models import Paper
from paper_watcher.storage.sqlite import (
    add_watch_query,
    count_papers,
    get_all_paper_report_rows,
    get_paper_by_id,
    insert_paper,
    insert_papers,
    list_watch_queries,
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

    def test_cross_source_merging_by_doi(self, db_connection: sqlite3.Connection):
        doi = "10.1038/s41586-026-0001"
        arxiv_paper = Paper(
            source="arxiv",
            external_id="2608.12345",
            title="Design of Novel Macrocyclic Peptides",
            authors=["Alice Smith", "Bob Johnson"],
            abstract="Preprint abstract on arXiv.",
            journal=None,
            publication_date="2026-08-01",
            electronic_date=None,
            pubmed_date=None,
            doi=doi,
            url="https://arxiv.org/abs/2608.12345",
        )

        pubmed_paper = Paper(
            source="pubmed",
            external_id="42999999",
            title="Design of Novel Macrocyclic Peptides",
            authors=["Alice Smith", "Bob Johnson"],
            abstract="Peer-reviewed full abstract on Nature.",
            journal="Nature",
            publication_date="2026-08-25",
            electronic_date=None,
            pubmed_date="2026-08-25",
            doi=f"https://doi.org/{doi}",
            url="https://pubmed.ncbi.nlm.nih.gov/42999999/",
        )

        # 1. Insert arXiv paper
        res1 = insert_papers(db_connection, [arxiv_paper], query="macrocycles")
        assert res1.inserted_count == 1
        assert res1.merged_count == 0
        assert count_papers(db_connection) == 1

        # 2. Insert PubMed paper with matching DOI
        res2 = insert_papers(db_connection, [pubmed_paper], query="macrocycles")
        assert res2.inserted_count == 0
        assert res2.merged_count == 1
        assert count_papers(db_connection) == 1

        # Retrieve canonical merged paper
        merged = get_paper_by_id(db_connection, res1.inserted_ids[0])
        assert merged is not None
        assert merged.is_cross_source is True
        assert merged.is_preprint_and_peer_reviewed is True
        assert set(merged.sources) == {"arxiv", "pubmed"}
        assert merged.external_ids["arxiv"] == "2608.12345"
        assert merged.external_ids["pubmed"] == "42999999"
        assert "arxiv" in merged.source_urls
        assert "pubmed" in merged.source_urls

        # Global report rows should show both sources
        rows = get_all_paper_report_rows(db_connection)
        assert len(rows) == 1
        assert "arxiv" in rows[0].source and "pubmed" in rows[0].source

    def test_cross_source_merging_by_title_and_author(self, db_connection: sqlite3.Connection):
        arxiv_paper = Paper(
            source="arxiv",
            external_id="2608.99999",
            title="De novo design of allosteric protein switches for biosensing",
            authors=["Alice Smith", "Bob Jones"],
            abstract="arXiv draft.",
            journal=None,
            publication_date="2026-08-01",
            electronic_date=None,
            pubmed_date=None,
            doi=None,
            url="https://arxiv.org/abs/2608.99999",
        )

        pubmed_paper = Paper(
            source="pubmed",
            external_id="43000000",
            title="De novo design of allosteric protein switches for biosensing",
            authors=["A. Smith", "C. Brown"],
            abstract="PubMed published.",
            journal="Science",
            publication_date="2026-08-20",
            electronic_date=None,
            pubmed_date="2026-08-20",
            doi=None,
            url="https://pubmed.ncbi.nlm.nih.gov/43000000/",
        )

        res1 = insert_papers(db_connection, [arxiv_paper])
        assert res1.inserted_count == 1
        assert count_papers(db_connection) == 1

        res2 = insert_papers(db_connection, [pubmed_paper])
        assert res2.inserted_count == 0
        assert res2.merged_count == 1
        assert count_papers(db_connection) == 1

        merged = get_paper_by_id(db_connection, res1.inserted_ids[0])
        assert merged is not None
        assert merged.is_cross_source is True
        assert set(merged.sources) == {"arxiv", "pubmed"}

    def test_cross_source_merging_biorxiv_and_pubmed(self, db_connection: sqlite3.Connection):
        doi = "10.1101/2026.08.15.555555"
        biorxiv_paper = Paper(
            source="biorxiv",
            external_id=doi,
            title="Deep generative protein biosensors",
            authors=["Alice Walker", "Bob Dylan"],
            abstract="bioRxiv preprint.",
            journal="bioengineering",
            publication_date="2026-08-15",
            electronic_date=None,
            pubmed_date=None,
            doi=doi,
            url=f"https://doi.org/{doi}",
        )

        pubmed_paper = Paper(
            source="pubmed",
            external_id="43555555",
            title="Deep generative protein biosensors",
            authors=["Alice Walker", "Bob Dylan"],
            abstract="Peer-reviewed version.",
            journal="Nature Biotechnology",
            publication_date="2026-09-01",
            electronic_date=None,
            pubmed_date="2026-09-01",
            doi=f"https://doi.org/{doi}",
            url="https://pubmed.ncbi.nlm.nih.gov/43555555/",
        )

        res1 = insert_papers(db_connection, [biorxiv_paper])
        assert res1.inserted_count == 1
        assert count_papers(db_connection) == 1

        res2 = insert_papers(db_connection, [pubmed_paper])
        assert res2.inserted_count == 0
        assert res2.merged_count == 1
        assert count_papers(db_connection) == 1

        merged = get_paper_by_id(db_connection, res1.inserted_ids[0])
        assert merged is not None
        assert merged.is_cross_source is True
        assert merged.is_preprint_and_peer_reviewed is True
        assert set(merged.sources) == {"biorxiv", "pubmed"}
