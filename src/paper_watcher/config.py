from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from paper_watcher.exceptions import ConfigurationError

# Ruta raíz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Cargar variables desde .env
load_dotenv(PROJECT_ROOT / ".env")

SourceKind = Literal["paper", "patent"]

PAPER_SOURCE_NAMES = frozenset(
    {
        "pubmed",
        "arxiv",
        "biorxiv",
        "medrxiv",
        "openalex",
        "semantic_scholar",
        "crossref",
        "core",
        "unpaywall",
        "lens",
    }
)
PATENT_SOURCE_NAMES = frozenset({"uspto", "epo", "wipo", "lens"})

# Only adapters that already exist are enabled by default. New integrations are
# opt-in as they are implemented, and restricted APIs never block public ones.
DEFAULT_PAPER_SOURCES = ("pubmed", "arxiv", "biorxiv", "medrxiv")
DEFAULT_PATENT_SOURCES: tuple[str, ...] = ()

SOURCE_ACCESS_URLS = {
    "core": "https://core.ac.uk/services/api",
    "crossref": "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
    "epo": "https://www.epo.org/en/searching-for-patents/data/web-services/ops",
    "lens": "https://docs.api.lens.org/",
    "semantic_scholar": "https://api.semanticscholar.org/api-docs",
    "unpaywall": "https://unpaywall.org/products/api",
    "uspto": "https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/",
    "wipo": "https://www.wipo.int/en/web/patentscope/data/index",
}

SOURCE_REQUIRED_SETTINGS: dict[str, tuple[str, ...]] = {
    "core": ("CORE_API_KEY",),
    "crossref": ("CROSSREF_EMAIL",),
    "epo": ("EPO_CONSUMER_KEY", "EPO_CONSUMER_SECRET"),
    "lens": ("LENS_API_TOKEN",),
    "unpaywall": ("UNPAYWALL_EMAIL",),
    "uspto": ("USPTO_API_KEY",),
    "wipo": ("WIPO_USERNAME", "WIPO_PASSWORD"),
}


@dataclass(frozen=True)
class Config:
    database_path: Path
    report_dir: Path
    request_timeout: int
    max_retries: int
    ncbi_email: str = field(repr=False)
    ncbi_api_key: str | None = field(default=None, repr=False)
    biorxiv_interval: str = "30d"
    openalex_enabled: bool = False
    openalex_api_key: str | None = field(default=None, repr=False)
    paper_sources: tuple[str, ...] = DEFAULT_PAPER_SOURCES
    patent_sources: tuple[str, ...] = DEFAULT_PATENT_SOURCES
    semantic_scholar_api_key: str | None = field(default=None, repr=False)
    crossref_email: str | None = field(default=None, repr=False)
    core_api_key: str | None = field(default=None, repr=False)
    unpaywall_email: str | None = field(default=None, repr=False)
    lens_api_token: str | None = field(default=None, repr=False)
    uspto_api_key: str | None = field(default=None, repr=False)
    epo_consumer_key: str | None = field(default=None, repr=False)
    epo_consumer_secret: str | None = field(default=None, repr=False)
    wipo_username: str | None = field(default=None, repr=False)
    wipo_password: str | None = field(default=None, repr=False)


def _get_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False

    raise ValueError(
        f"{name} must be one of: true, false, 1, 0, yes, no, on, off"
    )


def _get_optional(name: str) -> str | None:
    """Return a trimmed secret/contact setting without logging its value."""
    return os.getenv(name, "").strip() or None


def _get_source_list(
    name: str,
    default: tuple[str, ...],
    allowed: frozenset[str],
) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    sources: list[str] = []
    for item in raw_value.split(","):
        source = item.strip().lower().replace("-", "_")
        if not source or source in sources:
            continue
        if source not in allowed:
            valid = ", ".join(sorted(allowed))
            raise ConfigurationError(
                f"Unknown source '{source}' in {name}. Valid values: {valid}"
            )
        sources.append(source)
    return tuple(sources)


def source_is_enabled(config: Config, source: str, kind: SourceKind) -> bool:
    """Return whether a source is selected, without validating credentials."""
    normalized = source.strip().lower().replace("-", "_")
    enabled = config.paper_sources if kind == "paper" else config.patent_sources
    return normalized in enabled


def validate_source_access(config: Config, source: str, kind: SourceKind) -> None:
    """Validate access only when an adapter is about to be activated.

    Error messages name missing environment variables and official registration
    pages, but deliberately never interpolate credential values.
    """
    normalized = source.strip().lower().replace("-", "_")
    allowed = PAPER_SOURCE_NAMES if kind == "paper" else PATENT_SOURCE_NAMES
    if normalized not in allowed:
        valid = ", ".join(sorted(allowed))
        raise ConfigurationError(
            f"Unknown {kind} source '{normalized}'. Valid values: {valid}"
        )

    if not source_is_enabled(config, normalized, kind):
        setting = "PAPER_SOURCES" if kind == "paper" else "PATENT_SOURCES"
        raise ConfigurationError(
            f"Source '{normalized}' is disabled. Add it to {setting} to enable it."
        )

    setting_values = {
        "CORE_API_KEY": config.core_api_key,
        "CROSSREF_EMAIL": config.crossref_email,
        "EPO_CONSUMER_KEY": config.epo_consumer_key,
        "EPO_CONSUMER_SECRET": config.epo_consumer_secret,
        "LENS_API_TOKEN": config.lens_api_token,
        "UNPAYWALL_EMAIL": config.unpaywall_email,
        "USPTO_API_KEY": config.uspto_api_key,
        "WIPO_USERNAME": config.wipo_username,
        "WIPO_PASSWORD": config.wipo_password,
    }
    missing = [
        name
        for name in SOURCE_REQUIRED_SETTINGS.get(normalized, ())
        if not setting_values[name]
    ]
    if not missing:
        return

    access_url = SOURCE_ACCESS_URLS[normalized]
    raise ConfigurationError(
        f"Source '{normalized}' is enabled but missing required settings: "
        f"{', '.join(missing)}. Obtain access and configure them following "
        f"{access_url}"
    )


def load_config() -> Config:
    database_path = PROJECT_ROOT / (
        os.getenv("PAPER_WATCHER_DB")
        or os.getenv("DATABASE_PATH")
        or "data/papers.db"
    )

    report_dir = PROJECT_ROOT / (
        os.getenv("PAPER_WATCHER_REPORT_DIR")
        or os.getenv("REPORT_DIR")
        or "reports"
    )

    request_timeout = int(os.getenv("REQUEST_TIMEOUT", "15"))
    max_retries = int(os.getenv("MAX_RETRIES", "3"))

    ncbi_email = os.getenv("NCBI_EMAIL") or os.getenv("PUBMED_EMAIL") or ""
    ncbi_api_key = _get_optional("NCBI_API_KEY") or _get_optional("PUBMED_API_KEY")

    biorxiv_interval = os.getenv("BIORXIV_INTERVAL", "30d").strip() or "30d"
    openalex_enabled = _get_bool("OPENALEX_ENABLED")
    openalex_api_key = _get_optional("OPENALEX_API_KEY")
    paper_sources = _get_source_list(
        "PAPER_SOURCES", DEFAULT_PAPER_SOURCES, PAPER_SOURCE_NAMES
    )
    patent_sources = _get_source_list(
        "PATENT_SOURCES", DEFAULT_PATENT_SOURCES, PATENT_SOURCE_NAMES
    )

    return Config(
        database_path=database_path,
        report_dir=report_dir,
        request_timeout=request_timeout,
        max_retries=max_retries,
        ncbi_email=ncbi_email,
        ncbi_api_key=ncbi_api_key,
        biorxiv_interval=biorxiv_interval,
        openalex_enabled=openalex_enabled,
        openalex_api_key=openalex_api_key,
        paper_sources=paper_sources,
        patent_sources=patent_sources,
        semantic_scholar_api_key=_get_optional("SEMANTIC_SCHOLAR_API_KEY"),
        crossref_email=_get_optional("CROSSREF_EMAIL"),
        core_api_key=_get_optional("CORE_API_KEY"),
        unpaywall_email=_get_optional("UNPAYWALL_EMAIL"),
        lens_api_token=_get_optional("LENS_API_TOKEN"),
        uspto_api_key=_get_optional("USPTO_API_KEY"),
        epo_consumer_key=_get_optional("EPO_CONSUMER_KEY"),
        epo_consumer_secret=_get_optional("EPO_CONSUMER_SECRET"),
        wipo_username=_get_optional("WIPO_USERNAME"),
        wipo_password=_get_optional("WIPO_PASSWORD"),
    )
