from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
import requests
from adapter_contract import assert_adapter_contract

from paper_watcher.adapters.base import DocumentKind, SearchRequest, SourceStatus
from paper_watcher.adapters.builtin import SemanticScholarAdapter
from paper_watcher.adapters.orchestrator import SearchOrchestrator
from paper_watcher.adapters.registry import ScopedAdapterRegistry
from paper_watcher.config import Config
from paper_watcher.exceptions import APIError, InvalidResponseError
from paper_watcher.http import HttpClient, HttpPolicy
from paper_watcher.reports.markdown import render_paper_markdown
from paper_watcher.sources.semantic_scholar import (
    SEMANTIC_SCHOLAR_FIELDS,
    SEMANTIC_SCHOLAR_SEARCH_URL,
    parse_semantic_scholar_paper,
    search_semantic_scholar,
    to_semantic_scholar_query,
)


def _payload() -> dict[str, Any]:
    fixture = Path(__file__).parent / "fixtures" / "semantic_scholar_search.json"
    return cast(dict[str, Any], json.loads(fixture.read_text(encoding="utf-8")))


def _response(payload: dict[str, Any], status_code: int = 200) -> MagicMock:
    response = MagicMock(status_code=status_code, headers={})
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _config(tmp_path: Path, *, api_key: str | None = None) -> Config:
    return Config(
        database_path=tmp_path / "papers.db",
        report_dir=tmp_path / "reports",
        request_timeout=10,
        max_retries=1,
        ncbi_email="test@example.org",
        paper_sources=("semantic_scholar",),
        semantic_scholar_api_key=api_key,
    )


def test_plain_text_translation_removes_boolean_negation_and_hyphens():
    assert to_semantic_scholar_query(
        '("protein-design" OR biosensor) AND signal NOT (cancer OR tumor)'
    ) == "protein design biosensor signal"


def test_parser_maps_identifiers_dates_citations_topics_and_pdf():
    first, second = _payload()["data"]

    paper = parse_semantic_scholar_paper(first)
    fallback = parse_semantic_scholar_paper(second)

    assert paper.source == "semantic_scholar"
    assert paper.external_id == "s2-paper-001"
    assert paper.external_ids == {
        "semantic_scholar": "s2-paper-001",
        "doi": "10.1000/BIOSENSOR.1",
        "pmid": "12345678",
        "arxiv": "2608.12345",
        "corpus_id": "987654321",
    }
    assert paper.doi == "10.1000/biosensor.1"
    assert paper.authors == ["Alice Smith", "Bob Jones"]
    assert paper.publication_date == "2026-08-12"
    assert paper.citation_count == 42
    assert paper.topics == ["Biology", "Engineering"]
    assert paper.pdf_url == "https://example.test/paper.pdf"
    assert "**Citations (Semantic Scholar):** 42" in render_paper_markdown(paper)
    assert fallback.publication_date == "2025"
    assert fallback.url.endswith("/s2-paper-002")


def test_parser_rejects_missing_identity_or_title():
    with pytest.raises(InvalidResponseError, match="paperId"):
        parse_semantic_scholar_paper({"title": "Missing ID"})
    with pytest.raises(InvalidResponseError, match="title"):
        parse_semantic_scholar_paper({"paperId": "id"})


def test_search_paginates_filters_dates_and_sends_key():
    first_page = _payload()
    first_page["total"] = 150
    first_page["next"] = 100
    first_page["data"] = [first_page["data"][0]] * 100
    second_page = {
        "total": 150,
        "offset": 100,
        "data": [_payload()["data"][1]] * 20,
    }
    client = MagicMock(spec=HttpClient)
    client.request.side_effect = [_response(first_page), _response(second_page)]

    result = search_semantic_scholar(
        "protein AND biosensor",
        max_results=120,
        http_client=client,
        api_key="test-key",
        since=datetime(2026, 8, 1, tzinfo=UTC),
        until=datetime(2026, 8, 31, tzinfo=UTC),
    )

    assert len(result.papers) == 120
    assert result.total_count == 150
    assert result.truncated is True
    assert client.request.call_count == 2
    assert client.request.call_args_list[0].args[:2] == (
        "GET",
        SEMANTIC_SCHOLAR_SEARCH_URL,
    )
    first_params = client.request.call_args_list[0].kwargs["params"]
    second_params = client.request.call_args_list[1].kwargs["params"]
    assert first_params == {
        "query": "protein biosensor",
        "fields": SEMANTIC_SCHOLAR_FIELDS,
        "publicationDateOrYear": "2026-08-01:2026-08-31",
        "offset": 0,
        "limit": 100,
    }
    assert second_params["offset"] == 100
    assert second_params["limit"] == 20
    assert client.request.call_args_list[0].kwargs["headers"] == {
        "x-api-key": "test-key"
    }


def test_search_retries_429_using_shared_retry_after_policy():
    limited = MagicMock(status_code=429, headers={"Retry-After": "0"})
    session = MagicMock(spec=requests.Session)
    session.request.side_effect = [limited, _response(_payload())]
    client = HttpClient(HttpPolicy(timeout=5, max_retries=1), session=session)

    result = search_semantic_scholar(
        "biosensor", max_results=2, http_client=client
    )

    assert len(result.papers) == 2
    assert session.request.call_count == 2
    assert session.request.call_args.kwargs["headers"] is None


def test_search_rejects_invalid_payload_and_skips_partial_records():
    client = MagicMock(spec=HttpClient)
    client.request.return_value = _response({"total": 1, "data": [{}]})

    result = search_semantic_scholar(
        "biosensor", max_results=1, http_client=client
    )
    assert result.papers == []
    assert result.warnings == ("Semantic Scholar paper is missing paperId",)

    client.request.return_value = _response({"total": "bad", "data": []})
    with pytest.raises(InvalidResponseError, match="invalid total"):
        search_semantic_scholar("biosensor", max_results=1, http_client=client)


def test_adapter_contract_cursor_and_source_status(tmp_path: Path):
    config = _config(tmp_path)
    client = MagicMock(spec=HttpClient)
    payload = _payload()
    payload["total"] = 3
    client.request.return_value = _response(payload)
    adapter = SemanticScholarAdapter(config, client)

    assert_adapter_contract(adapter, DocumentKind.PAPER)
    result = adapter.search(SearchRequest("biosensor", max_results=2))

    assert len(result.papers) == 2
    assert result.cursor == "2"
    assert result.truncated is True
    assert result.status is SourceStatus.PARTIAL


def test_semantic_scholar_failure_is_isolated_by_orchestrator(tmp_path: Path):
    client = MagicMock(spec=HttpClient)
    client.request.side_effect = APIError("HTTP 401")
    registry = ScopedAdapterRegistry()
    registry.register(SemanticScholarAdapter(_config(tmp_path), client))

    result = SearchOrchestrator(registry).search(
        SearchRequest("biosensor"),
        paper_sources=("semantic_scholar",),
    )

    assert result.completed_sources == 0
    assert result.source_results[0].status is SourceStatus.FAILED
    assert result.warnings == (
        "semantic_scholar unavailable: HTTP 401",
    )
