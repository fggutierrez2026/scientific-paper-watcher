from dataclasses import dataclass

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

    @property
    def published(self) -> str | None:
        return (
            self.pubmed_date
            or self.electronic_date
            or self.publication_date
        )