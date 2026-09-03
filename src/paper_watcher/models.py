from dataclasses import dataclass, field


@dataclass(frozen=True)
class Paper:
    source: str
    external_id: str
    title: str
    authors: list[str]
    abstract: str | None
    journal: str | None
    publication_date: str | None
    electronic_date: str | None
    pubmed_date: str | None
    doi: str | None
    url: str | None
    sources: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    source_urls: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sources and self.source:
            object.__setattr__(self, "sources", [self.source])
        if not self.external_ids and self.source and self.external_id:
            object.__setattr__(self, "external_ids", {self.source: self.external_id})
        if not self.source_urls and self.source and self.url:
            object.__setattr__(self, "source_urls", {self.source: self.url})

    @property
    def published(self) -> str | None:
        return (
            self.pubmed_date
            or self.electronic_date
            or self.publication_date
        )

    @property
    def is_cross_source(self) -> bool:
        return len(set(self.sources)) > 1

    @property
    def is_preprint_and_peer_reviewed(self) -> bool:
        norm_sources = {s.lower() for s in self.sources}
        preprints = {"arxiv", "biorxiv", "medrxiv"}
        return bool(norm_sources.intersection(preprints)) and "pubmed" in norm_sources