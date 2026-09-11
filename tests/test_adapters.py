from __future__ import annotations

from dataclasses import dataclass

import pytest
from adapter_contract import assert_adapter_contract

from paper_watcher.adapters.base import (
    AdapterCapabilities,
    AdapterResult,
    DocumentKind,
    SearchRequest,
    SourceStatus,
)
from paper_watcher.adapters.builtin import build_builtin_registry
from paper_watcher.adapters.orchestrator import SearchOrchestrator, SearchScope
from paper_watcher.adapters.registry import ScopedAdapterRegistry
from paper_watcher.config import Config
from paper_watcher.exceptions import APIError, ConfigurationError
from paper_watcher.models import Paper, Patent

CAPABILITIES = AdapterCapabilities(
    document_kinds=frozenset({DocumentKind.PAPER, DocumentKind.PATENT}),
    discovery=True,
    enrichment=False,
)


def _paper(source: str = "fake") -> Paper:
    return Paper(
        source=source,
        external_id="paper-1",
        title="A paper",
        authors=[],
        abstract=None,
        journal=None,
        publication_date=None,
        electronic_date=None,
        pubmed_date=None,
        doi=None,
        url=None,
    )


def _patent(source: str = "fake") -> Patent:
    return Patent(
        source=source,
        external_id="patent-1",
        publication_number="US123A1",
        application_number=None,
        jurisdiction="US",
        title="A patent",
        abstract=None,
        inventors=[],
        applicants=[],
        priority_date=None,
        publication_date=None,
        cpc_codes=[],
        ipc_codes=[],
        family_id=None,
        citations=[],
        url=None,
    )


@dataclass
class FakeAdapter:
    name: str
    result_documents: tuple[Paper | Patent, ...]
    call_group: str = ""
    capabilities: AdapterCapabilities = CAPABILITIES
    error: APIError | None = None
    calls: int = 0
    requested_kinds: frozenset[DocumentKind] = frozenset()

    def __post_init__(self) -> None:
        if not self.call_group:
            self.call_group = self.name

    def search(self, request: SearchRequest) -> AdapterResult:
        self.calls += 1
        self.requested_kinds = request.document_kinds
        if self.error is not None:
            raise self.error
        documents = tuple(
            document
            for document in self.result_documents
            if (
                DocumentKind.PAPER
                if isinstance(document, Paper)
                else DocumentKind.PATENT
            )
            in request.document_kinds
        )
        return AdapterResult(
            source=self.name,
            documents=documents,
            total_count=len(documents),
        )


def test_builtin_adapters_pass_reusable_contract(tmp_path):
    config = Config(
        database_path=tmp_path / "papers.db",
        report_dir=tmp_path / "reports",
        request_timeout=10,
        max_retries=2,
        ncbi_email="test@example.org",
    )
    registry = build_builtin_registry(config)

    assert registry.papers.names == (
        "pubmed",
        "arxiv",
        "biorxiv",
        "medrxiv",
        "semantic_scholar",
    )
    for adapter in registry.papers.select(registry.papers.names):
        assert_adapter_contract(adapter, DocumentKind.PAPER)

    adapters = registry.papers.select(registry.papers.names)
    shared_clients = {
        id(adapter.http_client)  # type: ignore[attr-defined]
        for adapter in adapters
    }
    assert len(shared_clients) == 1


def test_registry_selection_is_configurable_and_stable():
    registry = ScopedAdapterRegistry()
    first = FakeAdapter("first", (_paper("first"),))
    second = FakeAdapter("second", (_paper("second"),))
    registry.register(first)
    registry.register(second)

    assert registry.papers.select(("second", "first", "second")) == (
        second,
        first,
    )
    with pytest.raises(ConfigurationError, match="no installed paper adapter"):
        registry.papers.select(("missing",))


def test_orchestrator_routes_scopes_and_normalizes_documents():
    registry = ScopedAdapterRegistry()
    papers = FakeAdapter("papers", (_paper("papers"),))
    patents = FakeAdapter("patents", (_patent("patents"),))
    registry.papers.register(papers)
    registry.patents.register(patents)
    orchestrator = SearchOrchestrator(registry)

    result = orchestrator.search(
        SearchRequest("biosensor"),
        scope=SearchScope.ALL,
        paper_sources=("papers",),
        patent_sources=("patents",),
    )

    assert result.papers == (_paper("papers"),)
    assert result.patents == (_patent("patents"),)
    assert papers.requested_kinds == frozenset({DocumentKind.PAPER})
    assert patents.requested_kinds == frozenset({DocumentKind.PATENT})


def test_orchestrator_calls_multi_scope_lens_adapter_once():
    registry = ScopedAdapterRegistry()
    lens = FakeAdapter("lens", (_paper("lens"), _patent("lens")))
    registry.register(lens)

    result = SearchOrchestrator(registry).search(
        SearchRequest("biosensor"),
        scope="all",
        paper_sources=("lens",),
        patent_sources=("lens",),
    )

    assert lens.calls == 1
    assert lens.requested_kinds == frozenset({DocumentKind.PAPER, DocumentKind.PATENT})
    assert len(result.papers) == 1
    assert len(result.patents) == 1


def test_orchestrator_isolates_adapter_failure():
    registry = ScopedAdapterRegistry()
    failed = FakeAdapter("failed", (), error=APIError("temporary outage"))
    healthy = FakeAdapter("healthy", (_paper("healthy"),))
    registry.papers.register(failed)
    registry.papers.register(healthy)

    result = SearchOrchestrator(registry).search(
        SearchRequest("biosensor"),
        paper_sources=("failed", "healthy"),
    )

    assert result.source_results[0].status is SourceStatus.FAILED
    assert result.source_results[1].status is SourceStatus.SUCCESS
    assert result.papers == (_paper("healthy"),)
    assert result.warnings == ("failed unavailable: temporary outage",)
