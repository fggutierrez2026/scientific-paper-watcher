from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from paper_watcher.config import Config
from paper_watcher.exceptions import InvalidResponseError, ServiceUnavailableError
from paper_watcher.http import HttpClient, HttpPolicy
from paper_watcher.sources.arxiv import (
    parse_arxiv_xml,
    search_arxiv,
)
from paper_watcher.sources.biorxiv import (
    _get_biorxiv,
    parse_biorxiv_json,
    search_biorxiv,
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

    @patch("paper_watcher.sources.pubmed._get_pubmed")
    def test_search_pubmed_adds_entrez_date_window(self, mock_get_pubmed):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "esearchresult": {"count": "0", "idlist": []}
        }
        mock_get_pubmed.return_value = mock_response

        search_pubmed(
            "protein design",
            since=datetime(2026, 8, 1, 12, tzinfo=UTC),
            until=datetime(2026, 8, 9, 18, tzinfo=UTC),
        )

        params = mock_get_pubmed.call_args.args[1]
        assert params["datetype"] == "edat"
        assert params["mindate"] == "2026/08/01"
        assert params["maxdate"] == "2026/08/09"

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

    @patch("paper_watcher.sources.arxiv._get_arxiv")
    def test_search_arxiv_adds_submitted_date_window(
        self,
        mock_get_arxiv,
        sample_arxiv_xml: bytes,
    ):
        mock_resp = MagicMock(content=sample_arxiv_xml)
        mock_get_arxiv.return_value = mock_resp

        search_arxiv(
            "all:biosensor",
            since=datetime(2026, 8, 1, 12, 30, tzinfo=UTC),
            until=datetime(2026, 8, 9, 18, 45, tzinfo=UTC),
        )

        params = mock_get_arxiv.call_args.args[0]
        assert params["search_query"] == (
            "(all:biosensor) AND "
            "submittedDate:[202608011230 TO 202608091845]"
        )


class TestBiorxivSource:
    @pytest.mark.parametrize(
        ("server", "provider"),
        (("biorxiv", "bioRxiv"), ("medrxiv", "medRxiv")),
    )
    def test_empty_success_response_is_retried_with_clear_error(
        self,
        server: str,
        provider: str,
    ):
        empty = MagicMock(status_code=200, headers={}, content=b"")
        session = MagicMock(spec=requests.Session)
        session.request.return_value = empty
        client = HttpClient(
            HttpPolicy(
                timeout=5,
                max_retries=2,
                backoff_min=0,
                backoff_max=0,
            ),
            session=session,
        )

        with pytest.raises(
            ServiceUnavailableError,
            match=rf"^{provider} returned an empty response$",
        ):
            _get_biorxiv(
                f"https://api.biorxiv.org/details/{server}/30d/0",
                http_client=client,
            )

        assert session.request.call_count == 3

    def test_request_recovers_when_retry_returns_content(self):
        empty = MagicMock(status_code=200, headers={}, content=b" \n")
        successful = MagicMock(
            status_code=200,
            headers={},
            content=b'{"messages": [], "collection": []}',
        )
        successful.raise_for_status.return_value = None
        session = MagicMock(spec=requests.Session)
        session.request.side_effect = [empty, successful]
        client = HttpClient(
            HttpPolicy(
                timeout=5,
                max_retries=1,
                backoff_min=0,
                backoff_max=0,
            ),
            session=session,
        )

        response = _get_biorxiv(
            "https://api.biorxiv.org/details/biorxiv/30d/0",
            http_client=client,
        )

        assert response is successful
        assert session.request.call_count == 2

    @pytest.fixture
    def sample_biorxiv_payload(self) -> dict:
        return {
            "messages": [{"status": "ok", "count": 2, "total_posts": 2}],
            "collection": [
                {
                    "doi": "10.1101/2026.08.10.123456",
                    "title": "Machine learning for allosteric biosensor engineering",
                    "authors": "Alice Walker; Bob Dylan",
                    "date": "2026-08-10",
                    "version": "1",
                    "type": "new results",
                    "category": "bioengineering",
                    "abstract": "We develop deep generative models for biosensing.",
                    "server": "biorxiv",
                },
                {
                    "doi": "10.1101/2026.08.11.654321",
                    "title": "Photosynthetic Rates in Forest Canopies",
                    "authors": "Charlie Green",
                    "date": "2026-08-11",
                    "version": "1",
                    "type": "new results",
                    "category": "ecology",
                    "abstract": "Analysis of canopy carbon exchange.",
                    "server": "biorxiv",
                },
            ],
        }

    def test_parse_biorxiv_json_unfiltered(self, sample_biorxiv_payload: dict):
        papers = parse_biorxiv_json(sample_biorxiv_payload)
        assert len(papers) == 2
        p1 = papers[0]
        assert p1.source == "biorxiv"
        assert p1.doi == "10.1101/2026.08.10.123456"
        assert p1.title == "Machine learning for allosteric biosensor engineering"
        assert p1.authors == ["Alice Walker", "Bob Dylan"]
        assert p1.journal == "bioengineering"
        assert p1.publication_date == "2026-08-10"
        assert p1.url == "https://doi.org/10.1101/2026.08.10.123456"

    def test_parse_biorxiv_json_with_query_filter(self, sample_biorxiv_payload: dict):
        papers = parse_biorxiv_json(sample_biorxiv_payload, query="biosensor AND learning")
        assert len(papers) == 1
        assert papers[0].doi == "10.1101/2026.08.10.123456"

        # Query that matches none
        empty = parse_biorxiv_json(sample_biorxiv_payload, query="crispr")
        assert len(empty) == 0

    def test_parse_biorxiv_json_invalid(self):
        with pytest.raises(InvalidResponseError):
            parse_biorxiv_json({"invalid": "data"})

    @patch("paper_watcher.sources.biorxiv._get_biorxiv")
    def test_search_biorxiv_calls_api(self, mock_get, sample_biorxiv_payload: dict):
        mock_resp = MagicMock()
        mock_resp.json.return_value = sample_biorxiv_payload
        mock_get.return_value = mock_resp

        result = search_biorxiv(
            query="biosensor",
            max_results=5,
            server="biorxiv",
            interval="30d",
        )

        assert result.total_found == 1
        assert result.server == "biorxiv"
        assert len(result.papers) == 1
        assert result.papers[0].title == "Machine learning for allosteric biosensor engineering"
        mock_get.assert_called_once_with(
            "https://api.biorxiv.org/details/biorxiv/30d/0"
        )

    @patch("paper_watcher.sources.biorxiv._get_biorxiv")
    def test_search_medrxiv_calls_its_api_and_maps_source(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "messages": [{"status": "ok", "count": 1, "total_posts": 1}],
            "collection": [
                {
                    "doi": "10.1101/2026.08.12.111111",
                    "title": "Clinical evaluation of a wearable biosensor",
                    "authors": "Ada Lovelace; Grace Hopper",
                    "date": "2026-08-12",
                    "version": "2",
                    "category": "infectious diseases",
                    "abstract": "A biosensor study in a clinical cohort.",
                }
            ],
        }
        mock_get.return_value = mock_resp

        result = search_biorxiv(
            query="biosensor",
            max_results=5,
            server="medrxiv",
            interval="7d",
        )

        assert result.server == "medrxiv"
        assert len(result.papers) == 1
        assert result.papers[0].source == "medrxiv"
        mock_get.assert_called_once_with(
            "https://api.biorxiv.org/details/medrxiv/7d/0"
        )

    @patch("paper_watcher.sources.biorxiv._get_biorxiv")
    def test_search_biorxiv_uses_explicit_date_window(
        self,
        mock_get,
        sample_biorxiv_payload: dict,
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = sample_biorxiv_payload
        mock_get.return_value = mock_resp

        search_biorxiv(
            query="biosensor",
            server="biorxiv",
            interval="30d",
            since=datetime(2026, 8, 1, 12, tzinfo=UTC),
            until=datetime(2026, 8, 9, 18, tzinfo=UTC),
        )

        mock_get.assert_called_once_with(
            "https://api.biorxiv.org/details/"
            "biorxiv/2026-08-01/2026-08-09/0"
        )

    @patch("paper_watcher.sources.biorxiv._get_biorxiv")
    def test_search_biorxiv_marks_limited_window_as_not_exhaustive(
        self,
        mock_get,
        sample_biorxiv_payload: dict,
    ):
        item = sample_biorxiv_payload["collection"][0]
        payload = {
            "messages": [{"status": "ok", "count": 30, "total_posts": 60}],
            "collection": [
                {**item, "doi": f"10.1101/2026.08.10.{index:06d}"}
                for index in range(30)
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_get.return_value = mock_resp

        result = search_biorxiv(
            query="biosensor",
            max_results=1,
            server="biorxiv",
            since=datetime(2026, 8, 1, tzinfo=UTC),
            until=datetime(2026, 8, 9, tzinfo=UTC),
        )

        assert result.exhaustive is False


    def test_search_rejects_unknown_server(self):
        with pytest.raises(ValueError, match="Unsupported preprint server"):
            search_biorxiv("biosensor", server="unknown")
