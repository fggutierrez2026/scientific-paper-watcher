from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from paper_watcher.models import Paper, Patent

Document = Paper | Patent


class DocumentKind(StrEnum):
    PAPER = "paper"
    PATENT = "patent"


class PaginationKind(StrEnum):
    NONE = "none"
    OFFSET = "offset"
    CURSOR = "cursor"


class TemporalFilterKind(StrEnum):
    NONE = "none"
    LOCAL = "local"
    NATIVE = "native"


class SourceStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass(frozen=True)
class AdapterCapabilities:
    """Operations and document kinds supported by an adapter."""

    document_kinds: frozenset[DocumentKind]
    discovery: bool
    enrichment: bool
    temporal_filter: TemporalFilterKind = TemporalFilterKind.NONE
    pagination: PaginationKind = PaginationKind.NONE

    def __post_init__(self) -> None:
        if not self.document_kinds:
            raise ValueError("An adapter must support at least one document kind")
        if not self.discovery and not self.enrichment:
            raise ValueError("An adapter must support discovery or enrichment")


@dataclass(frozen=True)
class SearchRequest:
    query: str
    max_results: int = 5
    since: datetime | None = None
    until: datetime | None = None
    cursor: str | None = None
    document_kinds: frozenset[DocumentKind] = field(
        default_factory=lambda: frozenset({DocumentKind.PAPER})
    )

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("Search query cannot be empty")
        if self.max_results < 1:
            raise ValueError("max_results must be greater than or equal to 1")
        if not self.document_kinds:
            raise ValueError("At least one document kind must be requested")


@dataclass(frozen=True)
class AdapterResult:
    """Provider-independent response returned by every source adapter."""

    source: str
    documents: tuple[Document, ...] = ()
    total_count: int = 0
    cursor: str | None = None
    truncated: bool = False
    warnings: tuple[str, ...] = ()
    status: SourceStatus = SourceStatus.SUCCESS

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("Adapter result source cannot be empty")
        if self.total_count < 0:
            raise ValueError("Adapter result total_count cannot be negative")
        if self.total_count < len(self.documents):
            raise ValueError(
                "Adapter result total_count cannot be smaller than documents"
            )
        if self.status is SourceStatus.SUCCESS and (self.truncated or self.warnings):
            object.__setattr__(self, "status", SourceStatus.PARTIAL)

    @property
    def papers(self) -> tuple[Paper, ...]:
        return tuple(item for item in self.documents if isinstance(item, Paper))

    @property
    def patents(self) -> tuple[Patent, ...]:
        return tuple(item for item in self.documents if isinstance(item, Patent))

    @classmethod
    def failed(cls, source: str, warning: str) -> AdapterResult:
        return cls(
            source=source,
            warnings=(warning,),
            status=SourceStatus.FAILED,
        )


@runtime_checkable
class SourceAdapter(Protocol):
    """Contract implemented by discovery and enrichment providers."""

    @property
    def name(self) -> str: ...

    @property
    def call_group(self) -> str: ...

    @property
    def capabilities(self) -> AdapterCapabilities: ...

    def search(self, request: SearchRequest) -> AdapterResult:
        """Search or enrich documents and return canonical domain models."""
        ...
