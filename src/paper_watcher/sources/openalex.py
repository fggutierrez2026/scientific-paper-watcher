from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote

import requests

from paper_watcher.config import load_config
from paper_watcher.exceptions import (
    InvalidResponseError,
    PaperWatcherError,
)
from paper_watcher.http import HttpClient, HttpPolicy
from paper_watcher.models import Paper
from paper_watcher.normalization import normalize_doi, normalize_title

logger = logging.getLogger(__name__)

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_SELECT = ",".join(
    (
        "id",
        "display_name",
        "cited_by_count",
        "topics",
        "best_oa_location",
    )
)
@dataclass(frozen=True)
class OpenAlexMetadata:
    openalex_id: str
    citation_count: int
    topics: list[str]
    pdf_url: str | None


@dataclass(frozen=True)
class OpenAlexEnrichmentResult:
    papers: list[Paper]
    enriched_count: int
    unmatched_count: int
    failed_count: int


def _get_openalex(
    url: str,
    params: dict[str, str | int],
    *,
    http_client: HttpClient | None = None,
) -> requests.Response:
    config = load_config()
    client = http_client or HttpClient(
        HttpPolicy(config.request_timeout, config.max_retries, backoff_max=10)
    )
    return client.request(
        "GET",
        url,
        provider="OpenAlex",
        params=params,
        allowed_statuses={404},
    )


def parse_openalex_work(data: dict[str, Any]) -> OpenAlexMetadata:
    openalex_id = data.get("id")
    if not isinstance(openalex_id, str) or not openalex_id.strip():
        raise InvalidResponseError("OpenAlex work is missing a valid id")

    raw_citation_count = data.get("cited_by_count", 0)
    if not isinstance(raw_citation_count, int) or raw_citation_count < 0:
        raise InvalidResponseError(
            "OpenAlex work has an invalid cited_by_count"
        )

    topics: list[str] = []
    raw_topics = data.get("topics") or []
    if not isinstance(raw_topics, list):
        raise InvalidResponseError("OpenAlex work has an invalid topics field")

    for topic in raw_topics:
        if not isinstance(topic, dict):
            continue
        display_name = topic.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            topics.append(display_name.strip())

    pdf_url = None
    best_oa_location = data.get("best_oa_location")
    if isinstance(best_oa_location, dict):
        raw_pdf_url = best_oa_location.get("pdf_url")
        if isinstance(raw_pdf_url, str) and raw_pdf_url.strip():
            pdf_url = raw_pdf_url.strip()

    return OpenAlexMetadata(
        openalex_id=openalex_id.strip(),
        citation_count=raw_citation_count,
        topics=topics[:3],
        pdf_url=pdf_url,
    )


def lookup_openalex_work(
    paper: Paper,
    api_key: str | None = None,
) -> OpenAlexMetadata | None:
    params: dict[str, str | int] = {"select": OPENALEX_SELECT}
    if api_key:
        params["api_key"] = api_key

    normalized_doi = normalize_doi(paper.doi)
    if normalized_doi:
        identifier = quote(f"doi:{normalized_doi}", safe=":/")
        response = _get_openalex(
            f"{OPENALEX_WORKS_URL}/{identifier}",
            params,
        )
        if response.status_code == 404:
            return None
        try:
            payload = response.json()
        except ValueError as exc:
            raise InvalidResponseError(
                f"OpenAlex response was not valid JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise InvalidResponseError("OpenAlex work response must be an object")
        return parse_openalex_work(payload)

    params.update({"search": paper.title, "per_page": 1})
    response = _get_openalex(OPENALEX_WORKS_URL, params)
    try:
        payload = response.json()
    except ValueError as exc:
        raise InvalidResponseError(
            f"OpenAlex response was not valid JSON: {exc}"
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise InvalidResponseError("OpenAlex search response is missing results")
    if not payload["results"]:
        return None

    work = payload["results"][0]
    if not isinstance(work, dict):
        raise InvalidResponseError("OpenAlex search result must be an object")

    matched_title = work.get("display_name")
    if not isinstance(matched_title, str) or (
        normalize_title(matched_title) != normalize_title(paper.title)
    ):
        return None

    return parse_openalex_work(work)


def enrich_papers_with_openalex(
    papers: list[Paper],
    api_key: str | None = None,
) -> OpenAlexEnrichmentResult:
    enriched_papers: list[Paper] = []
    cache: dict[str, OpenAlexMetadata | None | PaperWatcherError] = {}
    enriched_count = 0
    unmatched_count = 0
    failed_count = 0

    for paper in papers:
        normalized_doi = normalize_doi(paper.doi)
        cache_key = f"doi:{normalized_doi}" if normalized_doi else (
            f"title:{normalize_title(paper.title)}"
        )

        if cache_key not in cache:
            try:
                cache[cache_key] = lookup_openalex_work(paper, api_key=api_key)
            except PaperWatcherError as exc:
                cache[cache_key] = exc
                logger.warning(
                    "OpenAlex enrichment failed for %r: %s", paper.title, exc
                )

        metadata = cache[cache_key]
        if isinstance(metadata, PaperWatcherError):
            failed_count += 1
            enriched_papers.append(paper)
        elif metadata is None:
            unmatched_count += 1
            enriched_papers.append(paper)
        else:
            enriched_count += 1
            enriched_papers.append(
                replace(
                    paper,
                    openalex_id=metadata.openalex_id,
                    citation_count=metadata.citation_count,
                    topics=metadata.topics,
                    pdf_url=metadata.pdf_url,
                )
            )

    return OpenAlexEnrichmentResult(
        papers=enriched_papers,
        enriched_count=enriched_count,
        unmatched_count=unmatched_count,
        failed_count=failed_count,
    )
