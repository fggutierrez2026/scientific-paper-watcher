from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from paper_watcher.adapters import (
    AdapterResult,
    OrchestrationResult,
    SearchScope,
    SourceStatus,
)
from paper_watcher.config import Config
from paper_watcher.main import (
    RunResult,
    build_parser,
    list_queries_command,
    main,
    report_all_command,
    run,
    run_command,
)
from paper_watcher.models import Paper, Patent
from paper_watcher.storage.sqlite import (
    add_watch_query,
    database_connection,
    initialize_database,
    insert_papers,
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
        scope=SearchScope.PAPERS,
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


def test_search_cli_defaults_to_papers_and_accepts_all_scopes():
    parser = build_parser()

    default = parser.parse_args(["search", "--query", "biosensor"])
    assert default.scope == SearchScope.PAPERS
    for scope in SearchScope:
        parsed = parser.parse_args(
            ["search", "--query", "biosensor", "--scope", scope.value]
        )
        assert parsed.scope == scope

    with pytest.raises(SystemExit):
        parser.parse_args(
            ["search", "--query", "biosensor", "--scope", "invalid"]
        )


def test_search_and_run_commands_dispatch_compatible_arguments():
    with patch("paper_watcher.main.run_command") as command:
        assert main(["search", "--query", "biosensor", "--scope", "all"]) == 0
        assert command.call_args.kwargs["scope"] == "all"

    with patch("paper_watcher.main.run_command") as command:
        assert main(["run", "--query", "biosensor"]) == 0
        assert command.call_args.kwargs["scope"] is None


def test_report_all_cli_accepts_verbose_short_and_long_flags():
    parser = build_parser()

    assert parser.parse_args(["report-all"]).verbose is False
    assert parser.parse_args(["report-all", "-v"]).verbose is True
    assert parser.parse_args(["report-all", "--verbose"]).verbose is True

    with patch("paper_watcher.main.report_all_command") as command:
        assert main(["report-all", "-v"]) == 0
        command.assert_called_once_with(verbose=True)


def test_verbose_report_all_uses_detailed_rows(tmp_path: Path, sample_paper: Paper):
    config = Config(
        database_path=tmp_path / "papers.db",
        report_dir=tmp_path / "reports",
        request_timeout=10,
        max_retries=2,
        ncbi_email="test@example.com",
    )
    initialize_database(config.database_path)
    with database_connection(config.database_path) as connection:
        insert_papers(connection, [sample_paper], query="biosensor")

    with patch("paper_watcher.main.load_config", return_value=config):
        report_all_command(verbose=True)

    reports = list(config.report_dir.glob("all-papers-detailed_*.md"))
    assert len(reports) == 1
    content = reports[0].read_text(encoding="utf-8")
    assert sample_paper.title in content
    assert sample_paper.abstract is not None
    assert sample_paper.abstract in content


def test_stored_query_preserves_patent_scope(tmp_path: Path):
    config = Config(
        database_path=tmp_path / "papers.db",
        report_dir=tmp_path / "reports",
        request_timeout=10,
        max_retries=2,
        ncbi_email="test@example.com",
    )
    initialize_database(config.database_path)
    with database_connection(config.database_path) as connection:
        assert add_watch_query(connection, "biosensor", "patents") is not None

    with (
        patch("paper_watcher.main.load_config", return_value=config),
        patch(
            "paper_watcher.main.run",
            return_value=RunResult(completed_sources=0, total_sources=0),
        ) as mock_run,
    ):
        run_command(query=None, max_results=5)

    assert mock_run.call_args.kwargs["scope"] is SearchScope.PATENTS


def test_list_queries_displays_saved_scope(tmp_path: Path, capsys):
    config = Config(
        database_path=tmp_path / "papers.db",
        report_dir=tmp_path / "reports",
        request_timeout=10,
        max_retries=2,
        ncbi_email="test@example.com",
    )
    initialize_database(config.database_path)
    with database_connection(config.database_path) as connection:
        add_watch_query(connection, "biosensor", "all")

    with patch("paper_watcher.main.load_config", return_value=config):
        list_queries_command()

    output = capsys.readouterr().out
    assert "Scope" in output
    assert "all" in output
    assert "biosensor" in output


def test_run_routes_all_scope_and_writes_combined_report(
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
        patent_sources=("lens",),
    )
    paper = Paper(
        source="pubmed",
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

    patent = Patent(
        source="lens",
        external_id="US123A1",
        publication_number="US123A1",
        application_number=None,
        jurisdiction="US",
        title="A biosensor patent",
        abstract="A patent abstract.",
        inventors=["Grace Hopper"],
        applicants=["Example Corp"],
        priority_date="2025-01-01",
        publication_date="2026-01-01",
        cpc_codes=["G01N"],
        ipc_codes=[],
        family_id=None,
        citations=[],
        url="https://example.test/patent",
    )
    orchestration = OrchestrationResult(
        (
            AdapterResult("pubmed", (paper,), total_count=1),
            AdapterResult("lens", (patent,), total_count=1),
            AdapterResult(
                "failed",
                warnings=("failed unavailable: temporary outage",),
                status=SourceStatus.FAILED,
            ),
        )
    )

    with (
        patch("paper_watcher.main.load_config", return_value=config),
        patch("paper_watcher.main.build_builtin_registry"),
        patch("paper_watcher.main.SearchOrchestrator") as orchestrator_class,
        patch(
            "paper_watcher.main.write_scoped_markdown_report",
            return_value=tmp_path / "report.md",
        ) as write_report,
    ):
        orchestrator_class.return_value.search.return_value = orchestration

        result = run("biosensor", max_results=3, scope="all")

    search_call = orchestrator_class.return_value.search.call_args
    assert search_call.kwargs["scope"] is SearchScope.ALL
    assert search_call.kwargs["paper_sources"] == config.paper_sources
    assert search_call.kwargs["patent_sources"] == config.patent_sources
    report_call = write_report.call_args.kwargs
    assert report_call["scope"] == "all"
    assert report_call["warnings"] == [
        "failed unavailable: temporary outage"
    ]
    assert result.completed_sources == 2
    assert result.total_sources == 3

    output = capsys.readouterr().out
    assert "PAPERS" in output
    assert "PATENTS" in output
    assert "Papers collected: 1" in output
    assert "Patents collected: 1" in output
    assert "Sources completed: 2/3" in output
