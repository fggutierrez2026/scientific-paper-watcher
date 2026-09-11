from __future__ import annotations

from paper_watcher.adapters.base import DocumentKind, SourceAdapter


def assert_adapter_contract(adapter: SourceAdapter, kind: DocumentKind) -> None:
    """Reusable baseline that every concrete adapter must satisfy."""
    assert adapter.name == adapter.name.strip().lower().replace("-", "_")
    assert adapter.call_group.strip()
    assert kind in adapter.capabilities.document_kinds
    assert adapter.capabilities.discovery or adapter.capabilities.enrichment
    assert callable(adapter.search)
