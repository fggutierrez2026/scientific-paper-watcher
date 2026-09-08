from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import call, patch

from paper_watcher.config import Config
from paper_watcher.exceptions import APIError
from paper_watcher.main import RunResult, build_parser, run, run_command
from paper_watcher.models import Paper
from paper_watcher.sources.arxiv import ArxivSearchResult
from paper_watcher.sources.biorxiv import BiorxivSearchResult
from paper_watcher.sources.pubmed import PubMedSearchResult
from paper_watcher.storage.sqlite import (
    add_watch_query,
    database_connection,
    initialize_database,
    list_watch_query_rows,
    update_watch_query_last_checked,
)


def test_openalex_cli_flag_can_override_configuration():
    parser = build_parser()

    enabled = parser.parse_args(["run", "--query", "biosensor", "--openalex"])
    disabled = parser.parse_args(
        ["run", "--query", "biosensor", "--no-openalex"]
    )

    assert enabled.openalex is True
    assert disabled.openalex is False


def test_time_window_cli_flags():
    parser = build_parser()

    since_args = parser.parse_args(
        ["run", "--query", "biosensor", "--since", "2026-08-01"]
    )
    days_args = parser.parse_args(
        ["run", "--query", "biosensor", "--days", "7"]
    )

    assert since_args.since == datetime(2026, 8, 1, tzinfo=UTC)
    assert days_args.days == 7


def test_stored_query_uses_and_advances_checkpoint(tmp_path: Path):
    config = Config(
        database_path=tmp_path / "papers.db",
        report_dir=tmp_path / "reports",
        request_timeout=10,
        max_retries=2,
        ncbi_email="test@example.com",
    )
    initialize_database(config.database_path)
    previous = datetime(2026, 9, 1, 10, tzinfo=UTC)
    checked_at = datetime(2026, 9, 8, 15, 30, tzinfo=UTC)
    with database_connection(config.database_path) as connection:
        query_id = add_watch_query(connection, "biosensor")
        assert query_id is not None
        update_watch_query_last_checked(connection, query_id, previous)

    with (
        patch("paper_watcher.main.load_config", return_value=config),
        patch("paper_watcher.main.datetime") as mock_datetime,
        patch(
            "paper_watcher.main.run",
            return_value=RunResult(completed_sources=4),
        ) as mock_run,
    ):
        mock_datetime.now.return_value = checked_at
        run_command(query=None, max_results=5)

    mock_run.assert_called_once_with(
        query="biosensor",
        max_results=5,
        use_openalex=None,
        since=previous,
        until=checked_at,
    )
    with database_connection(config.database_path) as connection:
        row = list_watch_query_rows(connection)[0]
    assert row["last_checked_at"] == "2026-09-08T15:30:00+00:00"


def test_stored_query_does_not_advance_checkpoint_after_partial_run(
    tmp_path: Path,
):
    config = Config(
        database_path=tmp_path / "papers.db",
        report_dir=tmp_path / "reports",
        request_timeout=10,
        max_retries=2,
        ncbi_email="test@example.com",
    )
    initialize_database(config.database_path)
    previous = datetime(2026, 9, 1, 10, tzinfo=UTC)
    checked_at = datetime(2026, 9, 8, 15, 30, tzinfo=UTC)
    with database_connection(config.database_path) as connection:
        query_id = add_watch_query(connection, "biosensor")
        assert query_id is not None
        update_watch_query_last_checked(connection, query_id, previous)

    with (
        patch("paper_watcher.main.load_config", return_value=config),
        patch("paper_watcher.main.datetime") as mock_datetime,
        patch(
            "paper_watcher.main.run",
            return_value=RunResult(completed_sources=3),
        ),
    ):
        mock_datetime.now.return_value = checked_at
        run_command(query=None, max_results=5)

    with database_connection(config.database_path) as connection:
        row = list_watch_query_rows(connection)[0]
    assert row["last_checked_at"] == "2026-09-01T10:00:00+00:00"


def test_checkpoint_cannot_advance_when_incremental_results_are_truncated():
    result = RunResult(
        completed_sources=4,
        truncated_sources=("PubMed",),
    )

    assert result.all_sources_completed is True
    assert result.checkpoint_can_advance is False


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
        call(
            "biosensor",
            max_results=3,
            server="biorxiv",
            interval="14d",
            since=None,
            until=None,
        ),
        call(
            "biosensor",
            max_results=3,
            server="medrxiv",
            interval="14d",
            since=None,
            until=None,
        ),
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
