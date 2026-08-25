from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import logging
from dataclasses import dataclass
import xml.etree.ElementTree as ET

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

ESEARCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
)

EFETCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
)

TOOL_NAME = "scientific-paper-watcher"

logger = logging.getLogger(__name__)

RETRYABLE_EXCEPTIONS = (
    RequestTimeoutError,
    NetworkError,
    RateLimitError,
    ServiceUnavailableError,
)

DEFAULT_RETRY_WAIT = wait_exponential(
    multiplier=2,
    min=2,
    max=8,
)

def _parse_retry_after(
    value: str | None,
) -> float | None:
    if not value:
        return None

    value = value.strip()

    # Caso 1: Retry-After expresado en segundos.
    try:
        seconds = float(value)

        if seconds >= 0:
            return seconds

    except ValueError:
        pass

    # Caso 2: Retry-After expresado como fecha HTTP.
    try:
        retry_time = parsedate_to_datetime(value)

    except (TypeError, ValueError, OverflowError):
        logger.warning(
            "Invalid Retry-After header received: %r",
            value,
        )

        return None

    if retry_time.tzinfo is None:
        retry_time = retry_time.replace(
            tzinfo=timezone.utc
        )

    delay = (
        retry_time
        - datetime.now(timezone.utc)
    ).total_seconds()

    return max(0.0, delay)

def _request_pubmed_once(
    url: str,
    params: dict[str, str | int],
    timeout: int,) -> requests.Response:

    try:
        response = requests.get(
            url,
            params=params,
            timeout=timeout,
        )

    except requests.exceptions.Timeout as exc:
        logger.error(
            "PubMed request timed out after %d seconds",
            timeout,
        )

        raise RequestTimeoutError(
            f"PubMed request timed out after {timeout} seconds"
        ) from exc

    except requests.exceptions.ConnectionError as exc:
        logger.error(
            "Could not connect to PubMed"
        )

        raise NetworkError(
            "Could not connect to PubMed"
        ) from exc

    except requests.exceptions.RequestException as exc:
        logger.error(
            "Unexpected error while requesting PubMed: %s",
            exc,
        )

        raise APIError(
            "Unexpected error while requesting PubMed"
        ) from exc

    _check_response_status(response)

    return response

def _wait_for_retry(retry_state) -> float:
    exception = None

    if retry_state.outcome is not None:
        exception = retry_state.outcome.exception()

    if (
        isinstance(exception, RateLimitError)
        and exception.retry_after is not None
    ):
        logger.info(
            "Respecting server Retry-After: %.1f seconds",
            exception.retry_after,
        )

        return exception.retry_after

    return DEFAULT_RETRY_WAIT(retry_state)

def _get_pubmed(
    url: str,
    params: dict[str, str | int],
) -> requests.Response:
    config = load_config()

    retryer = Retrying(
        retry=retry_if_exception_type(
            RETRYABLE_EXCEPTIONS
        ),
        stop=stop_after_attempt(
            config.max_retries + 1
        ),
        wait=_wait_for_retry,
        before_sleep=before_sleep_log(
            logger,
            logging.WARNING,
        ),
        reraise=True,
    )

    return retryer(
        _request_pubmed_once,
        url,
        params,
        config.request_timeout,
    )

def _check_response_status(
    response: requests.Response,
) -> None:
    status_code = response.status_code

    if status_code == 429:
        retry_after = _parse_retry_after(
            response.headers.get("Retry-After")
        )

        logger.warning(
            "PubMed rate limit reached: HTTP %d "
            "retry_after=%s",
            status_code,
            retry_after,
        )

        raise RateLimitError(
            "PubMed rate limit reached (HTTP 429)",
            retry_after=retry_after,
        )

    if status_code in {500, 502, 503, 504}:
        logger.warning(
            "PubMed service temporarily unavailable: HTTP %d",
            status_code,
        )

        raise ServiceUnavailableError(
            f"PubMed service temporarily unavailable "
            f"(HTTP {status_code})"
        )

    try:
        response.raise_for_status()

    except requests.exceptions.HTTPError as exc:
        logger.error(
            "PubMed returned HTTP %d",
            status_code,
        )

        raise APIError(
            f"PubMed returned HTTP {status_code}"
        ) from exc
    
@dataclass(frozen=True)
class PubMedSearchResult:
    query: str
    total_count: int
    pmids: list[str]

def search_pubmed(query: str, 
    max_results: int = 5
    ) -> PubMedSearchResult:

    """
    Search PubMed for articles matching the given query.

    Args:
        query (str): The search query.
        max_results (int): Maximum number of results to return.

    Returns:
        PubMedSearchResult: An object containing the search results.
    """
    config = load_config()

    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results,
        "sort": "pub_date",
        "tool": TOOL_NAME,
        "email": config.ncbi_email,
    }

    logger.info(
        "Searching PubMed for query=%r max_results=%d",
        query,
        max_results,
    )

    response = _get_pubmed(ESEARCH_URL, params)

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        logger.error(
            "PubMed Esearch returned invalid JSON: %s",
            exc,
        )
        raise InvalidResponseError(
            "PubMed Esearch returned invalid JSON"
        ) from exc

    try:
        search_result = data["esearchresult"]

        total_count = int(search_result["count"])

        pmids = search_result["idlist"]
    except (KeyError, TypeError, ValueError) as exc:
        logger.error(
            "PubMed Esearch returned unexpected JSON structure: %s",
            exc,
        )
        raise InvalidResponseError(
            "PubMed Esearch returned unexpected JSON structure"
        ) from exc

    logger.info(
        "PubMed search completed: total_count=%d returned=%d",
        total_count,
        len(pmids),
    )  

    return PubMedSearchResult(
        query=query,
        total_count=total_count,
        pmids=pmids,
    )

def fetch_pubmed_articles(pmids: list[str]) -> list[Paper]:
    """
    Fetch detailed information for a list of PubMed IDs (PMIDs).

    Args:
        pmids (list[str]): A list of PubMed IDs.    
    """

    if not pmids:
        return []

    config = load_config()

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "tool": TOOL_NAME,
        "email": config.ncbi_email,
    }

    response = requests.get(
        EFETCH_URL,
        params=params,
        timeout=config.request_timeout,
    )

    response.raise_for_status()

    papers = parse_pubmed_xml(response.content)

    logger.info(
        "Parsed %d PubMed articles for %d PMIDs",
        len(papers),
        len(pmids),
    )

    return papers

def _element_text(element: ET.Element | None,) -> str | None:
    """
    Helper function to extract text from an XML element.

    Args:
        element (ET.Element): The parent XML element.
        tag (str): The tag name of the child element.

    Returns:
        str | None: The text content of the child element, or None if not found.
    """

    if element is None:
        return None

    text = "".join(element.itertext()).strip()
    return text or None

def _parse_authors(article: ET.Element) -> list[str]:
    """
    Parse the authors from a PubMed article XML element.

    Args:
        article (ET.Element): The XML element representing the article.
    """
    authors: list[str] = []

    author_elements = article.findall(
        "./MedlineCitation/Article/AuthorList/Author"
        )

    for author in author_elements:
        collective_name = author.findtext("CollectiveName")

        if collective_name:
            authors.append(collective_name.strip())
            continue

        last_name = author.findtext("LastName")
        fore_name = author.findtext("ForeName") 

        name_parts = [
            part.strip() for part in (fore_name, last_name) if part
        ]

        if name_parts:
            authors.append(" ".join(name_parts))

    return authors

def _parse_abstract(article: ET.Element) -> str | None:
    """
    Parse the abstract from a PubMed article XML element.

    Args:
        article (ET.Element): The XML element representing the article.
    """

    abstract_elements = article.findall(
        "./MedlineCitation/Article/Abstract/AbstractText"
    )

    if abstract_elements is None:
        return None

    sections: list[str] = []

    for element in abstract_elements:
        text = _element_text(element)

        if not text:
            continue

        label = element.attrib.get("Label")

        if label:
            sections.append(f"{label}: {text}")
        else:
            sections.append(text)

    if not sections:
        return None

    return "\n\n".join(sections)

def _parse_doi(article: ET.Element) -> str | None:
    """
    Parse the DOI from a PubMed article XML element.

    Args:
        article (ET.Element): The XML element representing the article.
    """

    article_ids = article.findall(
        "./PubmedData/ArticleIdList/ArticleId"
    )

    for article_id in article_ids:
        if article_id.attrib.get("IdType") == "doi":
            doi = _element_text(article_id)

            if doi:
                return doi.strip()

    return None

def _date_element_to_string(date_element: ET.Element | None) -> str | None:
    """
    Convert a date XML element to a string representation.

    Args:
        date_element (ET.Element): The XML element representing the date.
    """

    if date_element is None:
        return None

    year = date_element.findtext("Year")
    month = date_element.findtext("Month")
    day = date_element.findtext("Day")

    if not year:
        return None

    year = year.strip()

    if month:
        month = month.strip().zfill(2)

    if day:
        day = day.strip().zfill(2)

    parts = [
        part 
        for part in (year, month, day) 
        if part
    ]

    return "-".join(parts)


def _parse_electronic_date(article: ET.Element) -> str | None:
    """
    Parse the electronic publication date from a PubMed article XML element.

    Args:
        article (ET.Element): The XML element representing the article.
    """

    electronic_date = article.find("./MedlineCitation/Article/ArticleDate[@DateType='Electronic']")

    parsed_date = _date_element_to_string(electronic_date)

    if parsed_date:
        return parsed_date

    for pub_status in ("epublish", "aheadofprint",):

        history_date = article.find("./PubmedData/History/"
                                    "PubMedPubDate[@PubStatus='{pub_status}']"
        )

        parsed_date = _date_element_to_string(history_date)

        if parsed_date:
            return parsed_date

    return None

def _parse_publication_date(article: ET.Element) -> str | None:
    """
    Parse the publication date from a PubMed article XML element.

    Args:
        article (ET.Element): The XML element representing the article.
    """

    pub_date = article.find(
        "./MedlineCitation/Article/"
        "Journal/JournalIssue/PubDate"
    )

    if pub_date is None:
        return None

    medline_date = pub_date.findtext("MedlineDate")

    if medline_date:
        return medline_date.strip()

    year = pub_date.findtext("Year")
    month = pub_date.findtext("Month")
    day = pub_date.findtext("Day")
    season = pub_date.findtext("Season")


    parts = [
        part.strip() 
        for part in (year, month, day) 
        if part
    ]

    if season:
        parts.append(season.strip())

    if not parts:
        return None

    date_parts = [year]

    return "-".join(date_parts)

def _parse_pubmed_date(
    article: ET.Element,
) -> str | None:
    for pub_status in (
        "pubmed",
        "entrez",
    ):
        date_element = article.find(
            "./PubmedData/History/"
            f"PubMedPubDate[@PubStatus='{pub_status}']"
        )

        parsed_date = _date_element_to_string(
            date_element
        )

        if parsed_date:
            return parsed_date

    return None

def parse_pubmed_xml(xml_content: bytes) -> list[Paper]:
    """
    Parse the XML content returned by PubMed and extract article information.

    Args:
        xml_content (bytes): The XML content returned by PubMed.
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        logger.error(
            "PubMed EFetch returned invalid XML: %s",
            exc,
        )
        raise InvalidResponseError(
            " PubMed EFetch returned invalid XML"
        ) from exc
    
    papers: list[Paper] = []

    for article in root.findall("./PubmedArticle"):
        pmid = article.findtext("./MedlineCitation/PMID")

        title_element = article.find("./MedlineCitation/Article/ArticleTitle")
        
        title = _element_text(title_element)

        journal = article.findtext("./MedlineCitation/Article/Journal/Title")

        if not pmid or not title:
            continue

        clean_pmid = pmid.strip()

        paper = Paper(
            source="pubmed",
            external_id=clean_pmid,
            title=title,
            authors=_parse_authors(article),
            abstract=_parse_abstract(article),
            journal=journal.strip() if journal else None,
            publication_date=_parse_publication_date(article),
            electronic_date=_parse_electronic_date(article),
            pubmed_date=_parse_pubmed_date(article),
            doi=_parse_doi(article),
            url=f"https://pubmed.ncbi.nlm.nih.gov/{clean_pmid}/",
        )

        papers.append(paper)

    return papers
