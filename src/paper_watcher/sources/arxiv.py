from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

import requests

from paper_watcher.config import load_config
from paper_watcher.exceptions import InvalidResponseError
from paper_watcher.http import HttpClient, HttpPolicy
from paper_watcher.models import Paper
from paper_watcher.time_window import format_arxiv_date, validate_window

ARXIV_API_URL = "https://export.arxiv.org/api/query"

NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

ARXIV_MIN_INTERVAL = 3.0

_last_arxiv_request_at: float | None = None

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ArxivSearchResult:
    query: str
    total_count: int
    papers: list[Paper]

def _text(
    element: ET.Element | None,
) -> str | None:
    if element is None:
        return None

    text = "".join(
        element.itertext()
    ).strip()

    return text or None

def _extract_arxiv_id(
    entry_id: str,
) -> str:
    return entry_id.rstrip("/").split("/")[-1]

def parse_arxiv_xml(
    xml_content: bytes,
) -> list[Paper]:
    try:
        root = ET.fromstring(
            xml_content
        )

    except ET.ParseError as exc:
        logger.error(
            "arXiv returned invalid XML: %s",
            exc,
        )

        raise InvalidResponseError(
            "arXiv returned invalid XML"
        ) from exc

    papers: list[Paper] = []

    entries = root.findall(
        "atom:entry",
        NAMESPACES,
    )

    for entry in entries:
        entry_id = _text(
            entry.find(
                "atom:id",
                NAMESPACES,
            )
        )

        title = _text(
            entry.find(
                "atom:title",
                NAMESPACES,
            )
        )

        if not entry_id or not title:
            continue

        authors = []

        for author in entry.findall(
            "atom:author",
            NAMESPACES,
        ):
            name = _text(
                author.find(
                    "atom:name",
                    NAMESPACES,
                )
            )

            if name:
                authors.append(name)

        abstract = _text(
            entry.find(
                "atom:summary",
                NAMESPACES,
            )
        )

        published = _text(
            entry.find(
                "atom:published",
                NAMESPACES,
            )
        )

        publication_date = (
            published[:10]
            if published
            else None
        )

        doi = _text(
            entry.find(
                "arxiv:doi",
                NAMESPACES,
            )
        )

        journal_ref = _text(
            entry.find(
                "arxiv:journal_ref",
                NAMESPACES,
            )
        )

        arxiv_id = _extract_arxiv_id(
            entry_id
        )

        paper = Paper(
            source="arxiv",
            external_id=arxiv_id,
            title=" ".join(title.split()),
            authors=authors,
            abstract=abstract,
            journal=journal_ref,
            publication_date=publication_date,
            electronic_date=publication_date,
            pubmed_date=None,
            doi=doi,
            url=f"https://arxiv.org/abs/{arxiv_id}",
        )

        papers.append(paper)

    return papers

def _parse_total_results(
    xml_content: bytes,
) -> int:
    try:
        root = ET.fromstring(xml_content)

    except ET.ParseError as exc:
        raise InvalidResponseError(
            "arXiv returned invalid XML"
        ) from exc

    value = root.findtext(
        "opensearch:totalResults",
        namespaces=NAMESPACES,
    )

    if value is None:
        raise InvalidResponseError(
            "arXiv response does not contain totalResults"
        )

    try:
        return int(value)

    except ValueError as exc:
        raise InvalidResponseError(
            "arXiv returned an invalid totalResults value"
        ) from exc

def _respect_arxiv_rate_limit() -> None:
    global _last_arxiv_request_at

    now = time.monotonic()

    if _last_arxiv_request_at is not None:
        elapsed = now - _last_arxiv_request_at
        remaining = ARXIV_MIN_INTERVAL - elapsed

        if remaining > 0:
            logger.info(
                "Waiting %.2f seconds to respect arXiv rate limit",
                remaining,
            )

            time.sleep(remaining)

    _last_arxiv_request_at = time.monotonic()

def _get_arxiv(
    params: dict[str, str | int],
    *,
    http_client: HttpClient | None = None,
) -> requests.Response:
    config = load_config()

    _respect_arxiv_rate_limit()

    logger.info(
        "Requesting arXiv API"
    )

    client = http_client or HttpClient(
        HttpPolicy(
            config.request_timeout,
            config.max_retries,
            backoff_min=3,
            backoff_max=12,
        )
    )
    return client.request(
        "GET",
        ARXIV_API_URL,
        provider="arXiv",
        params=params,
        headers={"User-Agent": "scientific-paper-watcher/0.0.1"},
    )

def search_arxiv(
    query: str,
    max_results: int = 5,
    since: datetime | None = None,
    until: datetime | None = None,
    *,
    http_client: HttpClient | None = None,
) -> ArxivSearchResult:
    cleaned_query = query.strip()
    since, until = validate_window(since, until)

    search_query = cleaned_query
    if since is not None and until is not None:
        search_query = (
            f"({cleaned_query}) AND submittedDate:"
            f"[{format_arxiv_date(since)} TO {format_arxiv_date(until)}]"
        )

    params: dict[str, str | int] = {
        "search_query": search_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    logger.info(
        "Searching arXiv for query=%r max_results=%d",
        cleaned_query,
        max_results,
    )

    if http_client is None:
        response = _get_arxiv(params)
    else:
        response = _get_arxiv(params, http_client=http_client)

    papers = parse_arxiv_xml(
        response.content
    )

    total_count = _parse_total_results(
        response.content
    )

    logger.info(
        "arXiv search completed: total_count=%d returned=%d",
        total_count,
        len(papers),
    )

    return ArxivSearchResult(
        query=query,
        total_count=total_count,
        papers=papers,
    )
