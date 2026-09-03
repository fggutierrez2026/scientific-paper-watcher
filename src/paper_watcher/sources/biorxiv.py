from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from paper_watcher.config import load_config
from paper_watcher.exceptions import (
    APIError,
    InvalidResponseError,
    NetworkError,
    RateLimitError,
    RequestTimeoutError,
    ServiceUnavailableError,
)
from paper_watcher.models import Paper
from paper_watcher.query_language import matches_query

logger = logging.getLogger(__name__)

BIORXIV_BASE_URL = "https://api.biorxiv.org/details"

BIORXIV_RETRYABLE_EXCEPTIONS = (
    RequestTimeoutError,
    NetworkError,
    RateLimitError,
    ServiceUnavailableError,
)


@dataclass(frozen=True)
class BiorxivSearchResult:
    papers: list[Paper]
    total_found: int
    query: str
    server: str


def _get_biorxiv(
    url: str,
    params: dict[str, Any] | None = None,
) -> requests.Response:
    config = load_config()

    retryer = Retrying(
        stop=stop_after_attempt(config.max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(BIORXIV_RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )

    for attempt in retryer:
        with attempt:
            try:
                response = requests.get(
                    url,
                    params=params,
                    timeout=config.request_timeout,
                )
            except requests.exceptions.Timeout as exc:
                raise RequestTimeoutError(
                    f"bioRxiv request timed out after {config.request_timeout}s"
                ) from exc
            except requests.exceptions.ConnectionError as exc:
                raise NetworkError(
                    f"bioRxiv network connection failed: {exc}"
                ) from exc
            except requests.exceptions.RequestException as exc:
                raise APIError(
                    f"bioRxiv request failed: {exc}"
                ) from exc

            status = response.status_code

            if status == 429:
                raise RateLimitError(
                    "bioRxiv rate limit reached (HTTP 429)"
                )

            if 500 <= status < 600:
                raise ServiceUnavailableError(
                    f"bioRxiv server error: HTTP {status}"
                )

            if not response.ok:
                raise APIError(
                    f"bioRxiv API returned HTTP {status}: {response.text[:200]}"
                )

            return response

    raise APIError("bioRxiv request failed after all retries")


def parse_biorxiv_json(
    data: dict[str, Any],
    query: str | None = None,
) -> list[Paper]:
    """
    Parses a bioRxiv API response dictionary and returns a list of Paper objects.
    If `query` is provided, filters papers matching the boolean query against title and abstract.
    """
    messages = data.get("messages", [])
    if messages and isinstance(messages, list):
        status = messages[0].get("status")
        if status not in ("ok", None):
            logger.warning("bioRxiv returned message status: %s", status)

    if "collection" not in data or not isinstance(data["collection"], list):
        raise InvalidResponseError(
            "Expected 'collection' list in bioRxiv API response"
        )

    collection = data["collection"]

    papers: list[Paper] = []

    for item in collection:
        doi = item.get("doi")
        title = item.get("title", "").strip()
        abstract = item.get("abstract", "").strip() or None

        raw_authors = item.get("authors", "")
        if raw_authors:
            authors = [a.strip() for a in raw_authors.split(";") if a.strip()]
        else:
            authors = []

        date = item.get("date")
        category = item.get("category")
        server = item.get("server", "biorxiv")
        version = item.get("version", "1")

        external_id = doi or f"{server}_{date}_{version}"
        url = f"https://doi.org/{doi}" if doi else f"https://www.biorxiv.org/content/{doi}v{version}"

        if query:
            text_to_search = f"{title} {abstract or ''}"
            try:
                if not matches_query(query, text_to_search):
                    continue
            except Exception as exc:
                logger.debug("Query matching error on paper %r: %s", title, exc)
                continue

        paper = Paper(
            source=server,
            external_id=external_id,
            title=title,
            authors=authors,
            abstract=abstract,
            journal=category,
            publication_date=date,
            electronic_date=None,
            pubmed_date=None,
            doi=doi,
            url=url,
        )
        papers.append(paper)

    return papers


def search_biorxiv(
    query: str,
    max_results: int = 5,
    server: str | None = None,
    interval: str | None = None,
    max_pages: int = 5,
) -> BiorxivSearchResult:
    """
    Searches bioRxiv/medRxiv for preprints in the specified interval matching `query`.
    Evaluates compound boolean queries against titles and abstracts locally.
    """
    config = load_config()

    server_to_use = server or config.biorxiv_server or "biorxiv"
    interval_to_use = interval or config.biorxiv_interval or "30d"

    cleaned_query = query.strip()
    logger.info(
        "Searching %s for query=%r in interval=%s (max_results=%d)",
        server_to_use,
        cleaned_query,
        interval_to_use,
        max_results,
    )

    matching_papers: list[Paper] = []
    cursor = 0
    pages_fetched = 0

    while len(matching_papers) < max_results and pages_fetched < max_pages:
        url = f"{BIORXIV_BASE_URL}/{server_to_use}/{interval_to_use}/{cursor}"

        response = _get_biorxiv(url)

        try:
            payload = response.json()
        except ValueError as exc:
            raise InvalidResponseError(
                f"bioRxiv response was not valid JSON: {exc}"
            ) from exc

        collection = payload.get("collection", [])
        if not collection:
            break

        papers = parse_biorxiv_json(payload, query=cleaned_query)
        matching_papers.extend(papers)

        pages_fetched += 1
        cursor += len(collection)

        if len(collection) < 30:  # bioRxiv default page size is typically 30 or 100
            break

        # Polite backoff between paginated calls
        if len(matching_papers) < max_results:
            time.sleep(0.5)

    limited_papers = matching_papers[:max_results]

    logger.info(
        "bioRxiv search returned %d matching preprints (after scanning %d pages)",
        len(limited_papers),
        pages_fetched,
    )

    return BiorxivSearchResult(
        papers=limited_papers,
        total_found=len(limited_papers),
        query=cleaned_query,
        server=server_to_use,
    )
