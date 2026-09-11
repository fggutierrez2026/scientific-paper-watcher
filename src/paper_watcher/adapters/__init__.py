"""Common contracts and registries for external source adapters."""

from paper_watcher.adapters.base import (
    AdapterCapabilities,
    AdapterResult,
    Document,
    DocumentKind,
    PaginationKind,
    SearchRequest,
    SourceAdapter,
    SourceStatus,
    TemporalFilterKind,
)
from paper_watcher.adapters.builtin import build_builtin_registry
from paper_watcher.adapters.orchestrator import (
    OrchestrationResult,
    SearchOrchestrator,
    SearchScope,
)
from paper_watcher.adapters.registry import AdapterRegistry, ScopedAdapterRegistry

__all__ = [
    "AdapterCapabilities",
    "AdapterRegistry",
    "AdapterResult",
    "Document",
    "DocumentKind",
    "OrchestrationResult",
    "PaginationKind",
    "ScopedAdapterRegistry",
    "SearchOrchestrator",
    "SearchRequest",
    "SearchScope",
    "SourceAdapter",
    "SourceStatus",
    "TemporalFilterKind",
    "build_builtin_registry",
]
