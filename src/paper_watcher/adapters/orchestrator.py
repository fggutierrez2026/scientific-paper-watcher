from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from enum import StrEnum

from paper_watcher.adapters.base import (
    AdapterResult,
    DocumentKind,
    SearchRequest,
    SourceAdapter,
    SourceStatus,
)
from paper_watcher.adapters.registry import ScopedAdapterRegistry
from paper_watcher.exceptions import ConfigurationError, PaperWatcherError
from paper_watcher.models import Paper, Patent

logger = logging.getLogger(__name__)


class SearchScope(StrEnum):
    PAPERS = "papers"
    PATENTS = "patents"
    ALL = "all"


@dataclass(frozen=True)
class OrchestrationResult:
    source_results: tuple[AdapterResult, ...]

    @property
    def papers(self) -> tuple[Paper, ...]:
        return tuple(paper for result in self.source_results for paper in result.papers)

    @property
    def patents(self) -> tuple[Patent, ...]:
        return tuple(
            patent for result in self.source_results for patent in result.patents
        )

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(
            warning for result in self.source_results for warning in result.warnings
        )

    @property
    def completed_sources(self) -> int:
        return sum(
            result.status in {SourceStatus.SUCCESS, SourceStatus.PARTIAL}
            for result in self.source_results
        )

    @property
    def truncated_sources(self) -> tuple[str, ...]:
        return tuple(
            result.source for result in self.source_results if result.truncated
        )


class SearchOrchestrator:
    def __init__(self, registry: ScopedAdapterRegistry) -> None:
        self.registry = registry

    def search(
        self,
        request: SearchRequest,
        *,
        scope: SearchScope | str = SearchScope.PAPERS,
        paper_sources: tuple[str, ...] = (),
        patent_sources: tuple[str, ...] = (),
    ) -> OrchestrationResult:
        parsed_scope = SearchScope(scope)
        scheduled: list[tuple[SourceAdapter, set[DocumentKind]]] = []
        group_positions: dict[str, int] = {}

        if parsed_scope in {SearchScope.PAPERS, SearchScope.ALL}:
            self._schedule(
                scheduled,
                group_positions,
                self.registry.papers.select(paper_sources),
                DocumentKind.PAPER,
            )
        if parsed_scope in {SearchScope.PATENTS, SearchScope.ALL}:
            self._schedule(
                scheduled,
                group_positions,
                self.registry.patents.select(patent_sources),
                DocumentKind.PATENT,
            )

        results: list[AdapterResult] = []
        for adapter, kinds in scheduled:
            scoped_request = replace(request, document_kinds=frozenset(kinds))
            try:
                result = adapter.search(scoped_request)
            except PaperWatcherError as exc:
                warning = f"{adapter.name} unavailable: {exc}"
                logger.warning(warning)
                result = AdapterResult.failed(adapter.name, warning)
            else:
                self._validate_result(adapter, result, kinds)
            results.append(result)

        return OrchestrationResult(tuple(results))

    @staticmethod
    def _schedule(
        scheduled: list[tuple[SourceAdapter, set[DocumentKind]]],
        group_positions: dict[str, int],
        adapters: tuple[SourceAdapter, ...],
        kind: DocumentKind,
    ) -> None:
        for adapter in adapters:
            group = adapter.call_group.strip().lower()
            if not group:
                raise ConfigurationError(
                    f"Adapter '{adapter.name}' has an empty call group"
                )
            existing_position = group_positions.get(group)
            if existing_position is None:
                group_positions[group] = len(scheduled)
                scheduled.append((adapter, {kind}))
                continue

            existing_adapter, kinds = scheduled[existing_position]
            if existing_adapter is not adapter:
                raise ConfigurationError(
                    f"Adapters in call group '{group}' must share one instance"
                )
            kinds.add(kind)

    @staticmethod
    def _validate_result(
        adapter: SourceAdapter,
        result: AdapterResult,
        requested_kinds: set[DocumentKind],
    ) -> None:
        if result.source.strip().lower().replace("-", "_") != adapter.name:
            raise ConfigurationError(
                f"Adapter '{adapter.name}' returned result source "
                f"'{result.source}'"
            )
        for document in result.documents:
            kind = (
                DocumentKind.PAPER
                if isinstance(document, Paper)
                else DocumentKind.PATENT
            )
            if kind not in requested_kinds:
                raise ConfigurationError(
                    f"Adapter '{adapter.name}' returned an unrequested "
                    f"{kind.value} document"
                )
