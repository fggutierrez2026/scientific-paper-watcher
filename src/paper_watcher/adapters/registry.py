from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from paper_watcher.adapters.base import DocumentKind, SourceAdapter
from paper_watcher.exceptions import ConfigurationError


@dataclass
class AdapterRegistry:
    """Ordered registry for one canonical document kind."""

    kind: DocumentKind
    _adapters: dict[str, SourceAdapter] = field(default_factory=dict, init=False)

    def register(self, adapter: SourceAdapter) -> None:
        name = _normalize_name(adapter.name)
        if self.kind not in adapter.capabilities.document_kinds:
            raise ValueError(
                f"Adapter '{name}' does not support {self.kind.value} documents"
            )
        if name in self._adapters:
            raise ValueError(
                f"Adapter '{name}' is already registered for {self.kind.value}s"
            )
        self._adapters[name] = adapter

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._adapters)

    def select(self, names: Iterable[str]) -> tuple[SourceAdapter, ...]:
        selected: list[SourceAdapter] = []
        seen: set[str] = set()
        for raw_name in names:
            name = _normalize_name(raw_name)
            if not name or name in seen:
                continue
            seen.add(name)
            try:
                selected.append(self._adapters[name])
            except KeyError as exc:
                available = ", ".join(self.names) or "none"
                raise ConfigurationError(
                    f"Source '{name}' has no installed {self.kind.value} adapter. "
                    f"Available adapters: {available}"
                ) from exc
        return tuple(selected)


@dataclass
class ScopedAdapterRegistry:
    papers: AdapterRegistry = field(
        default_factory=lambda: AdapterRegistry(DocumentKind.PAPER)
    )
    patents: AdapterRegistry = field(
        default_factory=lambda: AdapterRegistry(DocumentKind.PATENT)
    )

    def register(self, adapter: SourceAdapter) -> None:
        if DocumentKind.PAPER in adapter.capabilities.document_kinds:
            self.papers.register(adapter)
        if DocumentKind.PATENT in adapter.capabilities.document_kinds:
            self.patents.register(adapter)


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("-", "_")
