from __future__ import annotations

from dataclasses import dataclass, field

from paper_watcher.adapters.base import (
    AdapterCapabilities,
    AdapterResult,
    DocumentKind,
    PaginationKind,
    SearchRequest,
    TemporalFilterKind,
)
from paper_watcher.adapters.registry import ScopedAdapterRegistry
from paper_watcher.config import Config
from paper_watcher.http import HttpClient, HttpPolicy
from paper_watcher.query_language import to_arxiv_query, to_pubmed_query
from paper_watcher.sources.arxiv import search_arxiv
from paper_watcher.sources.biorxiv import search_biorxiv
from paper_watcher.sources.pubmed import fetch_pubmed_articles, search_pubmed

PAPER_DISCOVERY_CAPABILITIES = AdapterCapabilities(
    document_kinds=frozenset({DocumentKind.PAPER}),
    discovery=True,
    enrichment=False,
    temporal_filter=TemporalFilterKind.NATIVE,
    pagination=PaginationKind.OFFSET,
)


@dataclass(frozen=True)
class PubMedAdapter:
    name: str = "pubmed"
    call_group: str = "pubmed"
    capabilities: AdapterCapabilities = PAPER_DISCOVERY_CAPABILITIES
    http_client: HttpClient | None = field(default=None, repr=False, compare=False)

    def search(self, request: SearchRequest) -> AdapterResult:
        result = search_pubmed(
            to_pubmed_query(request.query),
            max_results=request.max_results,
            since=request.since,
            until=request.until,
            http_client=self.http_client,
        )
        papers = tuple(
            fetch_pubmed_articles(result.pmids, http_client=self.http_client)
        )
        return AdapterResult(
            source=self.name,
            documents=papers,
            total_count=result.total_count,
            truncated=(
                request.since is not None and result.total_count > len(result.pmids)
            ),
        )


@dataclass(frozen=True)
class ArxivAdapter:
    name: str = "arxiv"
    call_group: str = "arxiv"
    capabilities: AdapterCapabilities = PAPER_DISCOVERY_CAPABILITIES
    http_client: HttpClient | None = field(default=None, repr=False, compare=False)

    def search(self, request: SearchRequest) -> AdapterResult:
        result = search_arxiv(
            to_arxiv_query(request.query),
            max_results=request.max_results,
            since=request.since,
            until=request.until,
            http_client=self.http_client,
        )
        return AdapterResult(
            source=self.name,
            documents=tuple(result.papers),
            total_count=result.total_count,
            truncated=(
                request.since is not None and result.total_count > len(result.papers)
            ),
        )


@dataclass(frozen=True)
class PreprintAdapter:
    name: str
    interval: str
    capabilities: AdapterCapabilities = PAPER_DISCOVERY_CAPABILITIES
    http_client: HttpClient | None = field(default=None, repr=False, compare=False)

    @property
    def call_group(self) -> str:
        return self.name

    def search(self, request: SearchRequest) -> AdapterResult:
        result = search_biorxiv(
            request.query,
            max_results=request.max_results,
            server=self.name,
            interval=self.interval,
            since=request.since,
            until=request.until,
            http_client=self.http_client,
        )
        return AdapterResult(
            source=self.name,
            documents=tuple(result.papers),
            total_count=result.total_found,
            truncated=request.since is not None and not result.exhaustive,
        )


def build_builtin_registry(config: Config) -> ScopedAdapterRegistry:
    """Return adapters implemented in the current release, in stable order."""
    http_client = HttpClient(
        HttpPolicy(config.request_timeout, config.max_retries)
    )
    registry = ScopedAdapterRegistry()
    registry.register(PubMedAdapter(http_client=http_client))
    registry.register(ArxivAdapter(http_client=http_client))
    registry.register(
        PreprintAdapter(
            "biorxiv", config.biorxiv_interval, http_client=http_client
        )
    )
    registry.register(
        PreprintAdapter(
            "medrxiv", config.biorxiv_interval, http_client=http_client
        )
    )
    return registry
