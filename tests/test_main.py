from pathlib import Path
from unittest.mock import call, patch

from paper_watcher.config import Config
from paper_watcher.exceptions import APIError
from paper_watcher.main import run
from paper_watcher.models import Paper
from paper_watcher.sources.arxiv import ArxivSearchResult
from paper_watcher.sources.biorxiv import BiorxivSearchResult
from paper_watcher.sources.pubmed import PubMedSearchResult


def test_run_queries_both_preprint_servers_and_isolates_failure(
    tmp_path: Path,
    capsys,
):
    config = Config(
        database_path=tmp_path / "papers.db",
        report_dir=tmp_path / "reports",
        request_timeout=10,
        max_retries=2,
        ncbi_email="test@example.com",
        biorxiv_interval="14d",
    )
    medrxiv_paper = Paper(
        source="medrxiv",
        external_id="10.1101/2026.08.12.111111",
        title="Clinical evaluation of a wearable biosensor",
        authors=["Ada Lovelace"],
        abstract="A clinical biosensor study.",
        journal="infectious diseases",
        publication_date="2026-08-12",
        electronic_date=None,
        pubmed_date=None,
        doi="10.1101/2026.08.12.111111",
        url="https://doi.org/10.1101/2026.08.12.111111",
    )

    with (
        patch("paper_watcher.main.load_config", return_value=config),
        patch(
            "paper_watcher.main.search_pubmed",
            return_value=PubMedSearchResult("biosensor", 0, []),
        ),
        patch("paper_watcher.main.fetch_pubmed_articles", return_value=[]),
        patch(
            "paper_watcher.main.search_arxiv",
            return_value=ArxivSearchResult("biosensor", 0, []),
        ),
        patch("paper_watcher.main.search_biorxiv") as search_preprints,
        patch(
            "paper_watcher.main.write_markdown_report",
            return_value=tmp_path / "report.md",
        ) as write_report,
    ):
        search_preprints.side_effect = [
            APIError("temporary outage"),
            BiorxivSearchResult(
                papers=[medrxiv_paper],
                total_found=1,
                query="biosensor",
                server="medrxiv",
            ),
        ]

        run("biosensor", max_results=3)

    assert search_preprints.call_args_list == [
        call("biosensor", max_results=3, server="biorxiv", interval="14d"),
        call("biosensor", max_results=3, server="medrxiv", interval="14d"),
    ]
    report_call = write_report.call_args.kwargs
    assert len(report_call["papers"]) == 1
    assert report_call["papers"][0].source == "medrxiv"
    assert report_call["papers"][0].doi == medrxiv_paper.doi
    assert report_call["warnings"] == [
        "bioRxiv unavailable: temporary outage"
    ]

    output = capsys.readouterr().out
    assert "bioRxiv unavailable: temporary outage" in output
    assert "medRxiv papers: 1" in output
    assert "Sources completed: 3/4" in output
