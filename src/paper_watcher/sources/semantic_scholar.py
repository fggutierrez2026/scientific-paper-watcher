from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from paper_watcher.exceptions import InvalidResponseError
from paper_watcher.http import HttpClient
from paper_watcher.models import Paper
from paper_watcher.normalization import normalize_doi
from paper_watcher.query_language import tokenize_query
from paper_watcher.time_window import as_utc, validate_window

SEMANTIC_SCHOLAR_SEARCH_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)
SEMANTIC_SCHOLAR_FIELDS = ",".join(
    (
        "paperId",
        "corpusId",
        "externalIds",
        "url",
        "title",
        "abstract",
        "authors",
        "venue",
        "year",
        "publicationDate",
        "citationCount",
        "s2FieldsOfStudy",
        "openAccessPdf",
    )
)
SEMANTIC_SCHOLAR_PAGE_SIZE = 100
SEMANTIC_SCHOLAR_RELEVANCE_LIMIT = 1000


@dataclass(frozen=True)
class SemanticScholarSearchResult:
    papers: list[Paper]
    total_count: int
    next_offset: int | None
    truncated: bool
    warnings: tuple[str, ...] = ()


def to_semantic_scholar_query(query: str) -> str:
    """Translate the common Boolean syntax to relevance-search plain text.

    AND/OR and grouping are removed. Terms governed by NOT are omitted because
    the relevance endpoint has no exclusion operator. Hyphens become spaces as
    required by Semantic Scholar's relevance search.
    """
    positive_terms: list[str] = []
    negate_next = False
    suppressed_depth = 0

    for token_type, value in tokenize_query(query):
        if token_type == "OP":
            if value == "NOT" and suppressed_depth == 0:
                negate_next = True
            continue
        if token_type == "LPAREN":
            if suppressed_depth:
                suppressed_depth += 1
            elif negate_next:
                suppressed_depth = 1
                negate_next = False
            continue
        if token_type == "RPAREN":
            if suppressed_depth:
                suppressed_depth -= 1
            continue
        if token_type not in {"TERM", "PHRASE"}:
            continue
        if suppressed_depth:
            continue
        if negate_next:
            negate_next = False
            continue
        positive_terms.append(value)

    plain_text = " ".join(positive_terms)
    plain_text = re.sub(r"[-‐‑‒–—]+", " ", plain_text)
    return re.sub(r"\s+", " ", plain_text).strip()


def parse_semantic_scholar_paper(data: dict[str, Any]) -> Paper:
    paper_id = data.get("paperId")
    title = data.get("title")
    if not isinstance(paper_id, str) or not paper_id.strip():
        raise InvalidResponseError("Semantic Scholar paper is missing paperId")
    if not isinstance(title, str) or not title.strip():
        raise InvalidResponseError("Semantic Scholar paper is missing title")

    raw_external_ids = data.get("externalIds") or {}
    if not isinstance(raw_external_ids, dict):
        raise InvalidResponseError(
            "Semantic Scholar paper has invalid externalIds"
        )
    identifier_names = {
        "DOI": "doi",
        "PubMed": "pmid",
        "ArXiv": "arxiv",
        "CorpusId": "corpus_id",
    }
    external_ids = {"semantic_scholar": paper_id.strip()}
    for raw_name, raw_value in raw_external_ids.items():
        if raw_value is None:
            continue
        name = identifier_names.get(str(raw_name), str(raw_name).lower())
        external_ids[name] = str(raw_value).strip()
    corpus_id = data.get("corpusId")
    if corpus_id is not None:
        external_ids.setdefault("corpus_id", str(corpus_id))

    raw_authors = data.get("authors") or []
    if not isinstance(raw_authors, list):
        raise InvalidResponseError("Semantic Scholar paper has invalid authors")
    authors: list[str] = []
    for author in raw_authors:
        if not isinstance(author, dict):
            continue
        author_name = author.get("name")
        if isinstance(author_name, str) and author_name.strip():
            authors.append(author_name.strip())

    topics: list[str] = []
    raw_topics = data.get("s2FieldsOfStudy") or data.get("fieldsOfStudy") or []
    if isinstance(raw_topics, list):
        for topic in raw_topics:
            category = topic.get("category") if isinstance(topic, dict) else topic
            if isinstance(category, str) and category.strip():
                topics.append(category.strip())

    publication_date = data.get("publicationDate")
    if not isinstance(publication_date, str) or not publication_date.strip():
        year = data.get("year")
        publication_date = str(year) if isinstance(year, (str, int)) else None

    citation_count = data.get("citationCount")
    if not isinstance(citation_count, int) or citation_count < 0:
        citation_count = None

    open_access_pdf = data.get("openAccessPdf")
    pdf_url = None
    if isinstance(open_access_pdf, dict):
        candidate = open_access_pdf.get("url")
        if isinstance(candidate, str) and candidate.strip():
            pdf_url = candidate.strip()

    url = data.get("url")
    if not isinstance(url, str) or not url.strip():
        url = f"https://www.semanticscholar.org/paper/{paper_id.strip()}"

    abstract = data.get("abstract")
    venue = data.get("venue")
    return Paper(
        source="semantic_scholar",
        external_id=paper_id.strip(),
        title=" ".join(title.split()),
        authors=authors,
        abstract=abstract.strip() if isinstance(abstract, str) and abstract.strip() else None,
        journal=venue.strip() if isinstance(venue, str) and venue.strip() else None,
        publication_date=publication_date,
        electronic_date=None,
        pubmed_date=None,
        doi=normalize_doi(external_ids.get("doi")),
        url=url.strip(),
        external_ids=external_ids,
        source_urls={"semantic_scholar": url.strip()},
        citation_count=citation_count,
        topics=list(dict.fromkeys(topics)),
        pdf_url=pdf_url,
    )


def search_semantic_scholar(
    query: str,
    *,
    max_results: int,
    http_client: HttpClient,
    api_key: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = None,
) -> SemanticScholarSearchResult:
    plain_query = to_semantic_scholar_query(query)
    if not plain_query:
        raise ValueError("Semantic Scholar query has no positive terms")
    if max_results < 1:
        raise ValueError("max_results must be greater than or equal to 1")
    try:
        offset = int(cursor) if cursor is not None else 0
    except ValueError as exc:
        raise ValueError("Semantic Scholar cursor must be an integer offset") from exc
    if offset < 0 or offset >= SEMANTIC_SCHOLAR_RELEVANCE_LIMIT:
        raise ValueError("Semantic Scholar cursor must be between 0 and 999")

    since, until = validate_window(since, until)
    base_params: dict[str, str | int] = {
        "query": plain_query,
        "fields": SEMANTIC_SCHOLAR_FIELDS,
    }
    if since is not None or until is not None:
        start = as_utc(since).date().isoformat() if since is not None else ""
        end = as_utc(until).date().isoformat() if until is not None else ""
        base_params["publicationDateOrYear"] = f"{start}:{end}"
    headers = {"x-api-key": api_key} if api_key else None

    papers: list[Paper] = []
    warnings: list[str] = []
    total_count = 0
    next_offset: int | None = offset
    result_limit = min(
        max_results, SEMANTIC_SCHOLAR_RELEVANCE_LIMIT - offset
    )

    while len(papers) < result_limit and next_offset is not None:
        page_limit = min(
            SEMANTIC_SCHOLAR_PAGE_SIZE, result_limit - len(papers)
        )
        params = {**base_params, "offset": next_offset, "limit": page_limit}
        response = http_client.request(
            "GET",
            SEMANTIC_SCHOLAR_SEARCH_URL,
            provider="Semantic Scholar",
            params=params,
            headers=headers,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise InvalidResponseError(
                "Semantic Scholar returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise InvalidResponseError(
                "Semantic Scholar search response is missing data"
            )
        raw_total = payload.get("total", 0)
        if not isinstance(raw_total, int) or raw_total < 0:
            raise InvalidResponseError(
                "Semantic Scholar search response has invalid total"
            )
        total_count = raw_total
        for item in payload["data"]:
            if not isinstance(item, dict):
                warnings.append("Semantic Scholar skipped a malformed paper")
                continue
            try:
                papers.append(parse_semantic_scholar_paper(item))
            except InvalidResponseError as exc:
                warnings.append(str(exc))
        raw_next = payload.get("next")
        candidate_offset = raw_next if isinstance(raw_next, int) else None
        if candidate_offset is not None and candidate_offset <= next_offset:
            raise InvalidResponseError(
                "Semantic Scholar returned a non-advancing next offset"
            )
        next_offset = candidate_offset
        if not payload["data"]:
            next_offset = None
        if next_offset is not None and next_offset >= SEMANTIC_SCHOLAR_RELEVANCE_LIMIT:
            next_offset = None

    truncated = total_count > offset + len(papers)
    if max_results > SEMANTIC_SCHOLAR_RELEVANCE_LIMIT - offset and truncated:
        warnings.append(
            "Semantic Scholar relevance search is capped at 1,000 results"
        )
    return SemanticScholarSearchResult(
        papers=papers[:result_limit],
        total_count=total_count,
        next_offset=next_offset,
        truncated=truncated,
        warnings=tuple(warnings),
    )
