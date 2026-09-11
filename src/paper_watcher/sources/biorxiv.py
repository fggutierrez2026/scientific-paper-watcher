from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from paper_watcher.config import load_config
from paper_watcher.exceptions import InvalidResponseError
from paper_watcher.http import HttpClient, HttpPolicy
from paper_watcher.models import Paper
from paper_watcher.query_language import matches_query
from paper_watcher.time_window import format_biorxiv_date, validate_window

logger = logging.getLogger(__name__)

BIORXIV_BASE_URL = "https://api.biorxiv.org/details"
BIORXIV_SERVERS = ("biorxiv", "medrxiv")

@dataclass(frozen=True)
class BiorxivSearchResult:
    papers: list[Paper]
    total_found: int
    query: str
    server: str
    exhaustive: bool = True


def _get_biorxiv(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    http_client: HttpClient | None = None,
) -> requests.Response:
    config = load_config()
    client = http_client or HttpClient(
        HttpPolicy(config.request_timeout, config.max_retries, backoff_max=10)
    )
    return client.request(
        "GET", url, provider="bioRxiv/medRxiv", params=params
    )


def parse_biorxiv_json(
    data: dict[str, Any],
    query: str | None = None,
    server: str | None = None,
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
            "Expected 'collection' list in bioRxiv/medRxiv API response"
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
        paper_server = item.get("server") or server or "biorxiv"
        version = item.get("version", "1")

        external_id = doi or f"{paper_server}_{date}_{version}"
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
            source=paper_server,
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
    since: datetime | None = None,
    until: datetime | None = None,
    *,
    http_client: HttpClient | None = None,
) -> BiorxivSearchResult:
    """
    Searches bioRxiv/medRxiv for preprints in the specified interval matching `query`.
    Evaluates compound boolean queries against titles and abstracts locally.
    """
    config = load_config()

    server_to_use = (server or "biorxiv").lower()
    interval_to_use = interval or config.biorxiv_interval or "30d"
    since, until = validate_window(since, until)
    if since is not None and until is not None:
        interval_to_use = (
            f"{format_biorxiv_date(since)}/{format_biorxiv_date(until)}"
        )

    if server_to_use not in BIORXIV_SERVERS:
        raise ValueError(
            f"Unsupported preprint server: {server_to_use}. "
            f"Expected one of: {', '.join(BIORXIV_SERVERS)}"
        )

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
    exhaustive = False

    while len(matching_papers) < max_results and pages_fetched < max_pages:
        url = f"{BIORXIV_BASE_URL}/{server_to_use}/{interval_to_use}/{cursor}"

        if http_client is None:
            response = _get_biorxiv(url)
        else:
            response = _get_biorxiv(url, http_client=http_client)

        try:
            payload = response.json()
        except ValueError as exc:
            raise InvalidResponseError(
                f"{server_to_use} response was not valid JSON: {exc}"
            ) from exc

        collection = payload.get("collection", [])
        if not collection:
            exhaustive = True
            break

        papers = parse_biorxiv_json(
            payload,
            query=cleaned_query,
            server=server_to_use,
        )
        matching_papers.extend(papers)

        pages_fetched += 1
        cursor += len(collection)

        total_posts = None
        messages = payload.get("messages")
        if messages and isinstance(messages, list) and isinstance(messages[0], dict):
            raw_total_posts = messages[0].get("total_posts")
            if isinstance(raw_total_posts, (str, int)):
                try:
                    total_posts = int(raw_total_posts)
                except ValueError:
                    total_posts = None

        if total_posts is not None and cursor >= total_posts:
            exhaustive = True
            break

        if len(collection) < 30:  # bioRxiv default page size is typically 30 or 100
            exhaustive = True
            break

        # Polite backoff between paginated calls
        if len(matching_papers) < max_results:
            time.sleep(0.5)

    limited_papers = matching_papers[:max_results]

    logger.info(
        "%s search returned %d matching preprints (after scanning %d pages)",
        server_to_use,
        len(limited_papers),
        pages_fetched,
    )

    return BiorxivSearchResult(
        papers=limited_papers,
        total_found=len(limited_papers),
        query=cleaned_query,
        server=server_to_use,
        exhaustive=exhaustive,
    )
