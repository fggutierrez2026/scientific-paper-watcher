import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from paper_watcher import __version__
from paper_watcher.adapters import (
    SearchOrchestrator,
    SearchRequest,
    SearchScope,
    build_builtin_registry,
)
from paper_watcher.config import load_config
from paper_watcher.exceptions import PaperWatcherError
from paper_watcher.logging_config import setup_logging
from paper_watcher.models import Paper, Patent
from paper_watcher.query_language import (
    normalize_common_query,
    to_arxiv_query,
    to_pubmed_query,
)
from paper_watcher.reports.markdown import (
    write_all_papers_report,
    write_detailed_all_papers_report,
    write_markdown_report,
    write_scoped_markdown_report,
)
from paper_watcher.sources.arxiv import search_arxiv
from paper_watcher.sources.biorxiv import BIORXIV_SERVERS, search_biorxiv
from paper_watcher.sources.openalex import enrich_papers_with_openalex
from paper_watcher.sources.pubmed import (
    fetch_pubmed_articles,
    search_pubmed,
)
from paper_watcher.storage.sqlite import (
    add_watch_query,
    count_papers,
    count_patents,
    database_connection,
    get_all_detailed_paper_report_rows,
    get_all_paper_report_rows,
    initialize_database,
    insert_papers,
    insert_patents,
    list_watch_query_rows,
    remove_watch_query,
    update_watch_query_last_checked,
)
from paper_watcher.time_window import (
    as_utc,
    parse_checkpoint,
    parse_since_date,
    since_days,
    validate_window,
)

logger = logging.getLogger(__name__)

SOURCE_COUNT = 4


@dataclass(frozen=True)
class RunResult:
    completed_sources: int
    total_sources: int = SOURCE_COUNT
    truncated_sources: tuple[str, ...] = ()

    @property
    def all_sources_completed(self) -> bool:
        return self.total_sources > 0 and self.completed_sources == self.total_sources

    @property
    def checkpoint_can_advance(self) -> bool:
        return self.all_sources_completed and not self.truncated_sources

def ensure_directories() -> None:
    """
    Ensure that the necessary directories exist.
    """
    config = load_config()
    config.database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    config.report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

def print_paper(paper) -> None:
    print(f"Source: {paper.source}")
    print(f"ID: {paper.external_id}")
    print(f"Title: {paper.title}")

    if paper.authors:
        authors = ", ".join(paper.authors[:3])

        if len(paper.authors) > 3:
            authors += ", et al."

        print(f"Authors: {authors}")

    if paper.journal:
        print(f"Journal: {paper.journal}")

    if paper.publication_date:
        print(
            f"Publication date: "
            f"{paper.publication_date}"
        )

    if paper.electronic_date:
        print(
            f"Electronic date: "
            f"{paper.electronic_date}"
        )

    if paper.pubmed_date:
        print(
            f"PubMed date: "
            f"{paper.pubmed_date}"
        )

    if paper.doi:
        print(f"DOI: {paper.doi}")

    print()


def print_patent(patent: Patent) -> None:
    print(f"Source: {patent.source}")
    print(f"ID: {patent.external_id}")
    print(f"Title: {patent.title}")
    print(f"Jurisdiction: {patent.jurisdiction}")
    if patent.publication_number:
        print(f"Publication number: {patent.publication_number}")
    if patent.application_number:
        print(f"Application number: {patent.application_number}")
    if patent.publication_date:
        print(f"Publication date: {patent.publication_date}")
    if patent.applicants:
        print(f"Applicants: {', '.join(patent.applicants[:3])}")
    print()

def _positive_int(value: str) -> int:
    number = int(value)

    if number < 1:
        raise argparse.ArgumentTypeError(
            "must be greater than or equal to 1"
        )

    return number

def _non_empty_text(
    value: str,
) -> str:
    cleaned = value.strip()

    if not cleaned:
        raise argparse.ArgumentTypeError(
            "must not be empty"
        )

    return cleaned


def _since_date(value: str) -> datetime:
    try:
        return parse_since_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-watcher",
        description=(
            "Search papers and patents through configured source adapters."
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    run_parser = subparsers.add_parser(
        "run",
        help=(
            "Run a direct or stored query (compatibility command; "
            "use search for new direct searches)."
        ),
    )

    run_parser.add_argument(
        "--query",
        type=_non_empty_text,
        help=(
            "Scientific query to run. "
            "If omitted, stored watch queries "
            "will be used."
        ),
    )

    run_parser.add_argument(
        "--max-results",
        type=_positive_int,
        default=5,
        help=(
            "Maximum number of documents to retrieve "
            "from each source (default: 5)."
        ),
    )

    run_parser.add_argument(
        "--scope",
        choices=tuple(SearchScope),
        default=None,
        help=(
            "Search scope. Defaults to papers for --query; when running stored "
            "queries, each query's saved scope is used unless overridden."
        ),
    )

    run_parser.add_argument(
        "--openalex",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enrich results with OpenAlex citations, topics, and an "
            "open-access PDF link. Overrides OPENALEX_ENABLED."
        ),
    )

    time_group = run_parser.add_mutually_exclusive_group()
    time_group.add_argument(
        "--since",
        type=_since_date,
        metavar="YYYY-MM-DD",
        help="Retrieve documents added on or after this UTC date.",
    )
    time_group.add_argument(
        "--days",
        type=_positive_int,
        metavar="N",
        help="Retrieve documents added during the last N days.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search papers, patents, or both.",
    )
    search_parser.add_argument(
        "--query",
        required=True,
        type=_non_empty_text,
        help="Query to run.",
    )
    search_parser.add_argument(
        "--scope",
        choices=tuple(SearchScope),
        default=SearchScope.PAPERS,
        help="Search scope (default: papers).",
    )
    search_parser.add_argument(
        "--max-results",
        type=_positive_int,
        default=5,
        help="Maximum results to retrieve from each source (default: 5).",
    )
    search_parser.add_argument(
        "--openalex",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable OpenAlex enrichment for paper results.",
    )
    search_time_group = search_parser.add_mutually_exclusive_group()
    search_time_group.add_argument(
        "--since",
        type=_since_date,
        metavar="YYYY-MM-DD",
        help="Retrieve documents added on or after this UTC date.",
    )
    search_time_group.add_argument(
        "--days",
        type=_positive_int,
        metavar="N",
        help="Retrieve documents added during the last N days.",
    )

    add_query_parser = subparsers.add_parser(
        "add-query",
        help="Store a query to watch.",
    )

    add_query_parser.add_argument(
        "watch_query",
        type=_non_empty_text,
        help="Scientific query to store.",
    )
    add_query_parser.add_argument(
        "--scope",
        choices=tuple(SearchScope),
        default=SearchScope.PAPERS,
        help="Stored search scope (default: papers).",
    )

    subparsers.add_parser(
        "list-queries",
        help="List stored watch queries.",
    )

    report_all_parser = subparsers.add_parser(
        "report-all",
        help=(
            "Generate a Markdown report "
            "for all stored papers."
        ),
    )
    report_all_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Include complete paper metadata and abstracts.",
    )

    remove_query_parser = (
        subparsers.add_parser(
            "remove-query",
            help=(
                "Remove a stored watch query "
                "by its database ID."
            ),
        )
    )

    remove_query_parser.add_argument(
        "query_id",
        type=_positive_int,
        help=(
            "Database ID of the stored query "
            "to remove."
        ),
    )

    return parser

def _legacy_run(
    query: str,
    max_results: int,
    use_openalex: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> RunResult:
    """
    Run entry point for the application.
    """
    setup_logging()

    config = load_config()
    since, until = validate_window(since, until)

    common_query = normalize_common_query(
        query
    )

    pubmed_query = to_pubmed_query(
        common_query
    )

    arxiv_query = to_arxiv_query(
        common_query
    )

    pubmed_papers: list[Paper] = []
    arxiv_papers: list[Paper] = []

    source_warnings: list[str] = []

    successful_sources = 0
    truncated_sources: list[str] = []

    initialize_database(
        config.database_path
    )

    ensure_directories()

    print()
    print("=" * 70)
    print("QUERY")
    print("=" * 70)

    print(
        f"Common : {common_query}"
    )

    print(
        f"PubMed : {pubmed_query}"
    )

    print(
        f"arXiv  : {arxiv_query}"
    )

    if since is not None and until is not None:
        print(f"Since  : {since.astimezone(UTC).isoformat(timespec='seconds')}")
        print(f"Until  : {until.astimezone(UTC).isoformat(timespec='seconds')}")

    print()
    print("=" * 70)
    print("PUBMED")
    print("=" * 70)

    try:
        # Aquí conserva tu código PubMed actual:
        #
        # search_pubmed(...)
        # fetch_pubmed_articles(...)
        # impresión de resultados
        #
        # Debe terminar dejando los Paper en:
        # pubmed_papers

        pubmed_result = search_pubmed(
            pubmed_query,
            max_results=max_results,
            since=since,
            until=until,
        )

        pubmed_papers = fetch_pubmed_articles(
            pubmed_result.pmids
        )

        if since is not None and pubmed_result.total_count > len(pubmed_result.pmids):
            truncated_sources.append("PubMed")

        print(
            f"Total PubMed results: "
            f"{pubmed_result.total_count}"
        )
        print(
            f"Articles retrieved: "
            f"{len(pubmed_papers)}"
        )
        print()

        for paper in pubmed_papers:
            print_paper(paper)

        successful_sources += 1

    except PaperWatcherError as exc:
        warning = (
            f"PubMed unavailable: {exc}"
        )

        logger.warning(warning)

        source_warnings.append(
            warning
        )

        print()
        print(warning)

    print()
    print("=" * 70)
    print("ARXIV")
    print("=" * 70)

    try:
        arxiv_result = search_arxiv(
            query=arxiv_query,
            max_results=max_results,
            since=since,
            until=until,
        )

        arxiv_papers = (
            arxiv_result.papers
        )

        if since is not None and arxiv_result.total_count > len(arxiv_papers):
            truncated_sources.append("arXiv")

        print(
            f"Total arXiv results: "
            f"{arxiv_result.total_count}"
        )
        print(
            f"Articles retrieved: "
            f"{len(arxiv_papers)}"
        )
        print()

        for paper in arxiv_papers:
            print_paper(paper)

        successful_sources += 1

    except PaperWatcherError as exc:
        warning = (
            f"arXiv unavailable: {exc}"
        )

        logger.warning(warning)

        source_warnings.append(
            warning
        )

        print()
        print(warning)

    biorxiv_papers: list[Paper] = []
    medrxiv_papers: list[Paper] = []
    preprint_papers = {
        "biorxiv": biorxiv_papers,
        "medrxiv": medrxiv_papers,
    }

    for server in BIORXIV_SERVERS:
        display_name = "bioRxiv" if server == "biorxiv" else "medRxiv"

        print()
        print("=" * 70)
        print(f"SOURCE: {display_name}")
        print("=" * 70)

        try:
            result = search_biorxiv(
                common_query,
                max_results=max_results,
                server=server,
                interval=config.biorxiv_interval,
                since=since,
                until=until,
            )

            preprint_papers[server].extend(result.papers)

            if since is not None and not result.exhaustive:
                truncated_sources.append(display_name)

            print(
                f"Preprints matched: "
                f"{len(result.papers)}"
            )
            print()

            for paper in result.papers:
                print_paper(paper)

            successful_sources += 1

        except PaperWatcherError as exc:
            warning = f"{display_name} unavailable: {exc}"

            logger.warning(warning)
            source_warnings.append(warning)

            print()
            print(warning)

    if successful_sources == 0:
        raise PaperWatcherError(
            "All paper sources failed: "
            + " | ".join(source_warnings)
        )

    if truncated_sources:
        warning = (
            "Incremental window truncated for "
            f"{', '.join(truncated_sources)}; increase --max-results "
            "before advancing the checkpoint."
        )
        logger.warning(warning)
        source_warnings.append(warning)
        print()
        print(warning)

    all_papers = (
        pubmed_papers
        + arxiv_papers
        + biorxiv_papers
        + medrxiv_papers
    )

    openalex_enabled = (
        config.openalex_enabled if use_openalex is None else use_openalex
    )
    openalex_enriched_count = 0
    openalex_unmatched_count = 0

    if openalex_enabled and all_papers:
        print()
        print("=" * 70)
        print("OPENALEX ENRICHMENT")
        print("=" * 70)

        enrichment_result = enrich_papers_with_openalex(
            all_papers,
            api_key=config.openalex_api_key,
        )
        all_papers = enrichment_result.papers
        openalex_enriched_count = enrichment_result.enriched_count
        openalex_unmatched_count = enrichment_result.unmatched_count

        print(f"Papers enriched: {openalex_enriched_count}")
        print(f"Papers not matched: {openalex_unmatched_count}")
        print(f"Enrichment failures: {enrichment_result.failed_count}")

        if enrichment_result.failed_count:
            source_warnings.append(
                "OpenAlex enrichment failed for "
                f"{enrichment_result.failed_count} paper(s)."
            )

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(
        f"PubMed papers: "
        f"{len(pubmed_papers)}"
    )

    print(
        f"arXiv papers: "
        f"{len(arxiv_papers)}"
    )

    print(
        f"bioRxiv papers: "
        f"{len(biorxiv_papers)}"
    )

    print(
        f"medRxiv papers: "
        f"{len(medrxiv_papers)}"
    )

    print(
        f"Total collected papers: "
        f"{len(all_papers)}"
    )

    if openalex_enabled:
        print(f"OpenAlex enriched: {openalex_enriched_count}")
        print(f"OpenAlex unmatched: {openalex_unmatched_count}")

    print()
    print("=" * 70)
    print("STORAGE")
    print("=" * 70)

    with database_connection(
        config.database_path
    ) as connection:
        insert_result = insert_papers(
            connection,
            all_papers,
            query=common_query,
        )

        total_stored = count_papers(
            connection
        )

    print(
        f"Database: {config.database_path}"
    )

    print(
        f"Papers retrieved: {insert_result.processed_count}"
    )

    print(
        f"New papers: {insert_result.inserted_count}"
    )

    if insert_result.merged_count > 0:
        print(
            f"Cross-source merged: {insert_result.merged_count}"
        )

    print(
        f"Known papers: {insert_result.known_count}"
    )

    print(
        f"Total papers stored: {total_stored}"
    )

    reported_papers = (
        insert_result.new_papers
        + insert_result.merged_papers
    )

    report_path = write_markdown_report(
        report_dir=config.report_dir,
        query=common_query,
        papers=reported_papers,
        warnings=source_warnings,
    )

    print(
        f"Sources completed: "
        f"{successful_sources}/{SOURCE_COUNT}"
    )

    print()
    print("=" * 70)
    print("REPORT")
    print("=" * 70)

    print(
        f"Report written to: {report_path}"
    )

    print(f"Request timeout: "
          f"{config.request_timeout} seconds")

    return RunResult(
        completed_sources=successful_sources,
        truncated_sources=tuple(truncated_sources),
    )


def run(
    query: str,
    max_results: int,
    use_openalex: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    scope: SearchScope | str = SearchScope.PAPERS,
) -> RunResult:
    """Search configured adapters, persist results, and write a scoped report."""
    setup_logging()
    config = load_config()
    since, until = validate_window(since, until)
    common_query = normalize_common_query(query)
    parsed_scope = SearchScope(scope)

    initialize_database(config.database_path)
    ensure_directories()

    registry = build_builtin_registry(config)
    paper_sources = tuple(
        source for source in config.paper_sources if source != "openalex"
    )
    orchestration = SearchOrchestrator(registry).search(
        SearchRequest(
            common_query,
            max_results=max_results,
            since=since,
            until=until,
        ),
        scope=parsed_scope,
        paper_sources=paper_sources,
        patent_sources=config.patent_sources,
    )
    total_sources = len(orchestration.source_results)
    if total_sources and orchestration.completed_sources == 0:
        raise PaperWatcherError(
            "All selected sources failed: " + " | ".join(orchestration.warnings)
        )

    papers = list(orchestration.papers)
    patents = list(orchestration.patents)
    warnings = list(orchestration.warnings)
    if parsed_scope in {SearchScope.PAPERS, SearchScope.ALL} and not paper_sources:
        warnings.append("No paper sources are enabled.")
    if (
        parsed_scope in {SearchScope.PATENTS, SearchScope.ALL}
        and not config.patent_sources
    ):
        warnings.append(
            "No patent sources are enabled; patent adapters are added in phase 4."
        )
    openalex_enabled = (
        config.openalex_enabled if use_openalex is None else use_openalex
    )
    if openalex_enabled and papers:
        enrichment = enrich_papers_with_openalex(
            papers, api_key=config.openalex_api_key
        )
        papers = enrichment.papers
        if enrichment.failed_count:
            warnings.append(
                f"OpenAlex enrichment failed for {enrichment.failed_count} paper(s)."
            )

    print()
    print("=" * 70)
    print("SEARCH")
    print("=" * 70)
    print(f"Query: {common_query}")
    print(f"Scope: {parsed_scope.value}")

    if parsed_scope in {SearchScope.PAPERS, SearchScope.ALL}:
        print()
        print("=" * 70)
        print("PAPERS")
        print("=" * 70)
        for paper in papers:
            print_paper(paper)
        print(f"Papers retrieved: {len(papers)}")

    if parsed_scope in {SearchScope.PATENTS, SearchScope.ALL}:
        print()
        print("=" * 70)
        print("PATENTS")
        print("=" * 70)
        for patent in patents:
            print_patent(patent)
        print(f"Patents retrieved: {len(patents)}")

    if warnings:
        print()
        print("=" * 70)
        print("SOURCE WARNINGS")
        print("=" * 70)
        for warning in warnings:
            print(f"- {warning}")

    with database_connection(config.database_path) as connection:
        paper_insert = insert_papers(connection, papers, query=common_query)
        patent_insert = insert_patents(connection, patents, query=common_query)
        total_papers = count_papers(connection)
        total_patents = count_patents(connection)

    reported_papers = paper_insert.new_papers + paper_insert.merged_papers
    reported_patents = patent_insert.new_patents + patent_insert.merged_patents
    report_path = write_scoped_markdown_report(
        config.report_dir,
        common_query,
        reported_papers,
        reported_patents,
        scope=parsed_scope.value,
        warnings=warnings,
    )

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Papers collected: {len(papers)}")
    print(f"Patents collected: {len(patents)}")
    print(f"New papers: {paper_insert.inserted_count}")
    print(f"New patents: {patent_insert.inserted_count}")
    print(f"Total papers stored: {total_papers}")
    print(f"Total patents stored: {total_patents}")
    print(f"Sources completed: {orchestration.completed_sources}/{total_sources}")
    print(f"Report written to: {report_path}")

    return RunResult(
        completed_sources=orchestration.completed_sources,
        total_sources=total_sources,
        truncated_sources=orchestration.truncated_sources,
    )

def add_query_command(
    query: str,
    scope: SearchScope | str = SearchScope.PAPERS,
) -> None:
    config = load_config()

    normalized_query = (
        normalize_common_query(
            query
        )
    )

    initialize_database(
        config.database_path
    )

    with database_connection(
        config.database_path
    ) as connection:
        query_id = add_watch_query(
            connection,
            normalized_query,
            SearchScope(scope).value,
        )

    if query_id is None:
        print(
            "Query already exists: "
            f"{normalized_query} [{SearchScope(scope).value}]"
        )
        return

    print(
        "Query added: "
        f"{normalized_query} [{SearchScope(scope).value}]"
    )

def list_queries_command() -> None:
    config = load_config()

    initialize_database(
        config.database_path
    )

    with database_connection(
        config.database_path
    ) as connection:
        query_rows = list_watch_query_rows(
            connection
        )

    if not query_rows:
        print(
            "No stored queries."
        )
        return

    print()
    print("Stored queries:")
    print()

    print(f"{'ID':<5} {'Scope':<9} {'Last checked (UTC)':<27} Query")

    print(f"{'--':<5} {'-' * 9} {'-' * 27} {'-' * 40}")

    for row in query_rows:
        print(
            f"{row['id']:<5} "
            f"{row['scope']:<9} "
            f"{(row['last_checked_at'] or 'never'):<27} "
            f"{row['query']}"
        )

def report_all_command(verbose: bool = False) -> None:
    config = load_config()

    initialize_database(
        config.database_path
    )

    with database_connection(
        config.database_path
    ) as connection:
        if verbose:
            detailed_rows = get_all_detailed_paper_report_rows(connection)
            row_count = len(detailed_rows)
        else:
            rows = get_all_paper_report_rows(connection)
            row_count = len(rows)

    if verbose:
        report_path = write_detailed_all_papers_report(
            report_dir=config.report_dir,
            rows=detailed_rows,
        )
    else:
        report_path = write_all_papers_report(
            report_dir=config.report_dir,
            rows=rows,
        )

    print()
    print("=" * 70)
    print("ALL PAPERS REPORT")
    print("=" * 70)

    count_label = "Papers" if verbose else "Rows"
    print(f"{count_label}: {row_count}")

    print(
        f"Report written to: "
        f"{report_path}"
    )

def run_command(
    query: str | None,
    max_results: int,
    use_openalex: bool | None = None,
    since: datetime | None = None,
    days: int | None = None,
    scope: SearchScope | str | None = None,
) -> None:
    checked_at = datetime.now(UTC)
    explicit_since = since_days(days, checked_at) if days is not None else since
    if explicit_since is not None:
        explicit_since = as_utc(explicit_since)
    if explicit_since is not None and explicit_since > checked_at:
        raise PaperWatcherError("--since must not be in the future")

    # Modo 1:
    # El usuario proporcionó una consulta concreta.
    if query is not None:
        run(
            query=query,
            max_results=max_results,
            use_openalex=use_openalex,
            since=explicit_since,
            until=checked_at if explicit_since is not None else None,
            scope=scope or SearchScope.PAPERS,
        )
        return

    # Modo 2:
    # No se proporcionó --query.
    # Ejecutamos las consultas guardadas en SQLite.
    config = load_config()

    initialize_database(
        config.database_path
    )

    with database_connection(
        config.database_path
    ) as connection:
        query_rows = list_watch_query_rows(
            connection
        )

    if not query_rows:
        print("No stored queries.")
        return

    print()
    print("=" * 70)
    print("STORED QUERIES")
    print("=" * 70)

    print(
        f"Queries to run: {len(query_rows)}"
    )

    successful_queries = 0
    failed_queries = 0

    for index, query_row in enumerate(
        query_rows,
        start=1,
    ):
        stored_query = str(query_row["query"])
        stored_scope = SearchScope(scope or str(query_row["scope"]))
        effective_since = explicit_since
        if effective_since is None and query_row["last_checked_at"]:
            try:
                effective_since = parse_checkpoint(query_row["last_checked_at"])
            except ValueError as exc:
                raise PaperWatcherError(str(exc)) from exc

        print()
        print("=" * 70)
        print(
            f"QUERY {index}/{len(query_rows)}"
        )
        print("=" * 70)

        print(
            f"Query: {stored_query}"
        )
        print(f"Scope: {stored_scope.value}")

        try:
            run_result = run(
                query=stored_query,
                max_results=max_results,
                use_openalex=use_openalex,
                since=effective_since,
                until=checked_at if effective_since is not None else None,
                scope=stored_scope,
            )

            successful_queries += 1

            if run_result.checkpoint_can_advance:
                with database_connection(config.database_path) as connection:
                    update_watch_query_last_checked(
                        connection,
                        int(query_row["id"]),
                        checked_at,
                    )
            else:
                print(
                    "Checkpoint not advanced because a source failed or the "
                    "result window was truncated."
                )

        except PaperWatcherError as exc:
            failed_queries += 1

            logger.error(
                "Stored query failed: "
                "query=%r error=%s",
                stored_query,
                exc,
            )

            print()
            print(
                f"Query failed: {stored_query}"
            )

            print(
                f"Reason: {exc}"
            )

    print()
    print("=" * 70)
    print("BATCH SUMMARY")
    print("=" * 70)

    print(
        f"Queries processed: {len(query_rows)}"
    )

    print(
        f"Queries successful: {successful_queries}"
    )

    print(
        f"Queries failed: {failed_queries}"
    )

def remove_query_command(
    query_id: int,
) -> None:
    config = load_config()

    initialize_database(
        config.database_path
    )

    with database_connection(
        config.database_path
    ) as connection:
        removed_query = remove_watch_query(
            connection,
            query_id,
        )

    if removed_query is None:
        print(
            f"Query not found: {query_id}"
        )
        return

    print()
    print("Query removed:")
    print(
        f"{query_id}. "
        f"{removed_query}"
    )

def main(
    argv: list[str] | None = None,
) -> int:
    setup_logging()

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            run_command(
                query=args.query,
                max_results=args.max_results,
                use_openalex=args.openalex,
                since=args.since,
                days=args.days,
                scope=args.scope,
            )

            return 0

        if args.command == "search":
            run_command(
                query=args.query,
                max_results=args.max_results,
                use_openalex=args.openalex,
                since=args.since,
                days=args.days,
                scope=args.scope,
            )

            return 0

        if args.command == "add-query":
            add_query_command(
                args.watch_query,
                args.scope,
            )

            return 0

        if args.command == "list-queries":
            list_queries_command()

            return 0

        if args.command == "remove-query":
            remove_query_command(
                args.query_id
            )

            return 0

        if args.command == "report-all":
            report_all_command(verbose=args.verbose)

            return 0

    except PaperWatcherError as exc:
        logger.error(
            "Scientific Paper Watcher failed: %s",
            exc,
        )

        print()
        print(
            "Scientific Paper Watcher failed:"
        )
        print(exc)

        return 1

    return 0

if __name__ == "__main__":
    main()
