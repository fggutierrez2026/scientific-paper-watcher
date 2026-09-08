from unittest.mock import MagicMock, call, patch

from paper_watcher.exceptions import APIError
from paper_watcher.models import Paper
from paper_watcher.sources.openalex import (
    OPENALEX_SELECT,
    enrich_papers_with_openalex,
    lookup_openalex_work,
    parse_openalex_work,
)


def _paper(*, doi: str | None = "10.1000/example") -> Paper:
    return Paper(
        source="pubmed",
        external_id="123",
        title="Engineering of novel glucose biosensors",
        authors=["Alice Smith"],
        abstract="An abstract.",
        journal="Biosensors",
        publication_date="2026-01-15",
        electronic_date=None,
        pubmed_date=None,
        doi=doi,
        url="https://example.org/paper",
    )


def _work() -> dict:
    return {
        "id": "https://openalex.org/W123",
        "display_name": "Engineering of novel glucose biosensors",
        "cited_by_count": 42,
        "topics": [
            {"display_name": "Biosensor Engineering", "score": 0.99},
            {"display_name": "Protein Design", "score": 0.75},
        ],
        "best_oa_location": {
            "pdf_url": "https://repository.example.org/paper.pdf"
        },
    }


def test_parse_openalex_work_extracts_enrichment_fields():
    metadata = parse_openalex_work(_work())

    assert metadata.openalex_id == "https://openalex.org/W123"
    assert metadata.citation_count == 42
    assert metadata.topics == ["Biosensor Engineering", "Protein Design"]
    assert metadata.pdf_url == "https://repository.example.org/paper.pdf"


@patch("paper_watcher.sources.openalex._get_openalex")
def test_lookup_by_doi_uses_singleton_endpoint(mock_get):
    response = MagicMock()
    response.json.return_value = _work()
    mock_get.return_value = response

    metadata = lookup_openalex_work(_paper(), api_key="secret")

    assert metadata is not None
    assert metadata.citation_count == 42
    mock_get.assert_called_once_with(
        "https://api.openalex.org/works/doi:10.1000/example",
        {"select": OPENALEX_SELECT, "api_key": "secret"},
    )


@patch("paper_watcher.sources.openalex._get_openalex")
def test_lookup_by_doi_treats_not_found_as_unmatched(mock_get):
    response = MagicMock(status_code=404)
    mock_get.return_value = response

    assert lookup_openalex_work(_paper()) is None


@patch("paper_watcher.sources.openalex._get_openalex")
def test_title_fallback_requires_exact_normalized_title(mock_get):
    response = MagicMock()
    response.json.return_value = {
        "results": [{**_work(), "display_name": "A different paper"}]
    }
    mock_get.return_value = response

    assert lookup_openalex_work(_paper(doi=None)) is None


@patch("paper_watcher.sources.openalex.lookup_openalex_work")
def test_enrichment_caches_matches_and_isolates_failures(mock_lookup):
    duplicate = _paper()
    failed = Paper(
        **{
            **_paper(doi="10.1000/failure").__dict__,
            "external_id": "456",
        }
    )
    mock_lookup.side_effect = [parse_openalex_work(_work()), APIError("outage")]

    result = enrich_papers_with_openalex([duplicate, duplicate, failed])

    assert result.enriched_count == 2
    assert result.failed_count == 1
    assert result.unmatched_count == 0
    assert result.papers[0].citation_count == 42
    assert result.papers[0].topics == ["Biosensor Engineering", "Protein Design"]
    assert mock_lookup.call_args_list == [
        call(duplicate, api_key=None),
        call(failed, api_key=None),
    ]
