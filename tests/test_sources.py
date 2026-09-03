from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from paper_watcher.config import Config
from paper_watcher.exceptions import InvalidResponseError, RateLimitError
from paper_watcher.sources.arxiv import (
    parse_arxiv_xml,
    search_arxiv,
)
from paper_watcher.sources.pubmed import (
    fetch_pubmed_articles,
    parse_pubmed_xml,
    search_pubmed,
)


class TestPubmedSource:
    def test_parse_pubmed_xml(self, sample_pubmed_xml: bytes):
        papers = parse_pubmed_xml(sample_pubmed_xml)
        assert len(papers) == 1
        p = papers[0]
        assert p.source == "pubmed"
        assert p.external_id == "99887766"
        assert p.title == "De novo protein design with deep generative priors"
        assert p.authors == ["Marie Curie", "OpenProtein Consortium"]
        assert p.journal == "Nature Biotechnology"
        assert p.doi == "10.1038/s41587-026-0001-x"
        assert p.publication_date == "2026"
        assert p.electronic_date == "2026-02-10"
        assert p.published == "2026-02-10"
        assert p.abstract is not None
        assert "BACKGROUND: Designing functional proteins remains challenging." in p.abstract
        assert "RESULTS: We demonstrate zero-shot structural generation." in p.abstract

    def test_parse_pubmed_xml_invalid(self):
        with pytest.raises(InvalidResponseError):
            parse_pubmed_xml(b"<invalid-xml>")

    @patch("paper_watcher.sources.pubmed._get_pubmed")
    @patch("paper_watcher.sources.pubmed.load_config")
    def test_search_pubmed_passes_api_key_when_configured(
        self,
        mock_config,
        mock_get_pubmed,
    ):
        mock_config.return_value = Config(
            database_path=None,  # type: ignore
            report_dir=None,  # type: ignore
            request_timeout=10,
            max_retries=2,
            ncbi_email="test@example.com",
            ncbi_api_key="secret-key-xyz",
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "esearchresult": {
                "count": "42",
                "idlist": ["123", "456"],
            }
        }
        mock_get_pubmed.return_value = mock_response

        res = search_pubmed("protein design", max_results=2)
        assert res.total_count == 42
        assert res.pmids == ["123", "456"]

        call_params = mock_get_pubmed.call_args[0][1]
        assert call_params["api_key"] == "secret-key-xyz"
        assert call_params["email"] == "test@example.com"
        assert call_params["retmax"] == 2

    def test_fetch_pubmed_articles_empty(self):
        assert fetch_pubmed_articles([]) == []

    @patch("paper_watcher.sources.pubmed._get_pubmed")
    @patch("paper_watcher.sources.pubmed.load_config")
    def test_fetch_pubmed_articles_calls_get_pubmed(
        self,
        mock_config,
        mock_get_pubmed,
        sample_pubmed_xml: bytes,
    ):
        mock_config.return_value = Config(
            database_path=None,  # type: ignore
            report_dir=None,  # type: ignore
            request_timeout=10,
            max_retries=2,
            ncbi_email="test@example.com",
            ncbi_api_key=None,
        )
        mock_response = MagicMock()
        mock_response.content = sample_pubmed_xml
        mock_get_pubmed.return_value = mock_response

        papers = fetch_pubmed_articles(["99887766"])
        assert len(papers) == 1
        assert papers[0].external_id == "99887766"


class TestArxivSource:
    def test_parse_arxiv_xml(self, sample_arxiv_xml: bytes):
        papers = parse_arxiv_xml(sample_arxiv_xml)
        assert len(papers) == 1
        p = papers[0]
        assert p.source == "arxiv"
        assert p.external_id == "2608.99999v1"
        assert p.title == "Accurate De Novo Design of Macrocyclic Peptides"
        assert p.authors == ["Linus Pauling", "Dorothy Hodgkin"]
        assert p.abstract == "We report a general computational pipeline for macrocycle conformation prediction."
        assert p.doi == "10.48550/arXiv.2608.99999"
        assert p.journal == "Nature Chem 2026"
        assert p.publication_date == "2026-08-25"
        assert p.url == "https://arxiv.org/abs/2608.99999v1"

    def test_parse_arxiv_xml_invalid(self):
        with pytest.raises(InvalidResponseError):
            parse_arxiv_xml(b"<invalid-xml>")

    @patch("paper_watcher.sources.arxiv._get_arxiv")
    def test_search_arxiv_sends_exact_query(
        self,
        mock_get_arxiv,
        sample_arxiv_xml: bytes,
    ):
        mock_resp = MagicMock()
        mock_resp.content = sample_arxiv_xml
        mock_get_arxiv.return_value = mock_resp

        complex_query = '( all:"glucose binding protein" OR all:GGBP ) AND all:biosensor'
        result = search_arxiv(complex_query, max_results=5)

        assert result.total_count == 1
        assert len(result.papers) == 1

        call_params = mock_get_arxiv.call_args[0][0]
        assert call_params["search_query"] == complex_query
        assert call_params["max_results"] == 5
