from __future__ import annotations

from pathlib import Path
import pytest
import sqlite3

from paper_watcher.models import Paper
from paper_watcher.storage.sqlite import initialize_database


@pytest.fixture
def sample_paper() -> Paper:
    return Paper(
        source="pubmed",
        external_id="12345678",
        title="Engineering of novel glucose biosensors",
        authors=["Alice Smith", "Bob Jones"],
        abstract="We describe an engineered glucose biosensor.",
        journal="Journal of Biosensors",
        publication_date="2026-01-15",
        electronic_date="2026-01-10",
        pubmed_date="2026-01-15",
        doi="10.1000/biosens.2026.01",
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
    )


@pytest.fixture
def sample_arxiv_paper() -> Paper:
    return Paper(
        source="arxiv",
        external_id="2608.12345v1",
        title="Deep learning models for protein dynamics",
        authors=["Charlie Brown", "Dana Scully"],
        abstract="A novel neural architecture for molecular simulation.",
        journal=None,
        publication_date="2026-08-20",
        electronic_date="2026-08-20",
        pubmed_date=None,
        doi=None,
        url="https://arxiv.org/abs/2608.12345v1",
    )


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_papers.db"
    initialize_database(db_path)
    return db_path


@pytest.fixture
def db_connection(temp_db_path: Path):
    connection = sqlite3.connect(temp_db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@pytest.fixture
def sample_pubmed_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2026//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_260101.dtd">
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>99887766</PMID>
      <Article>
        <Journal>
          <JournalIssue>
            <PubDate>
              <Year>2026</Year>
              <Month>02</Month>
              <Day>14</Day>
            </PubDate>
          </JournalIssue>
          <Title>Nature Biotechnology</Title>
        </Journal>
        <ArticleTitle>De novo protein design with deep generative priors</ArticleTitle>
        <AuthorList>
          <Author>
            <LastName>Curie</LastName>
            <ForeName>Marie</ForeName>
          </Author>
          <Author>
            <CollectiveName>OpenProtein Consortium</CollectiveName>
          </Author>
        </AuthorList>
        <Abstract>
          <AbstractText Label="BACKGROUND">Designing functional proteins remains challenging.</AbstractText>
          <AbstractText Label="RESULTS">We demonstrate zero-shot structural generation.</AbstractText>
        </Abstract>
        <ArticleDate DateType="Electronic">
          <Year>2026</Year>
          <Month>02</Month>
          <Day>10</Day>
        </ArticleDate>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">99887766</ArticleId>
        <ArticleId IdType="doi">10.1038/s41587-026-0001-x</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""


@pytest.fixture
def sample_arxiv_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2608.99999v1</id>
    <title> Accurate De Novo Design of Macrocyclic Peptides </title>
    <summary> We report a general computational pipeline for macrocycle conformation prediction. </summary>
    <author><name>Linus Pauling</name></author>
    <author><name>Dorothy Hodgkin</name></author>
    <published>2026-08-25T12:00:00Z</published>
    <arxiv:doi>10.48550/arXiv.2608.99999</arxiv:doi>
    <arxiv:journal_ref>Nature Chem 2026</arxiv:journal_ref>
  </entry>
</feed>"""

