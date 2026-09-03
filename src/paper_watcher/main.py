import argparse
import logging

from paper_watcher import __version__
from paper_watcher.config import load_config
from paper_watcher.exceptions import PaperWatcherError
from paper_watcher.logging_config import setup_logging
from paper_watcher.models import Paper
from paper_watcher.query_language import (
    normalize_common_query,
    to_arxiv_query,
    to_pubmed_query,
)
from paper_watcher.reports.markdown import (
    write_all_papers_report,
    write_markdown_report,
)
from paper_watcher.sources.arxiv import search_arxiv
from paper_watcher.sources.pubmed import (
    fetch_pubmed_articles,
    search_pubmed,
)
from paper_watcher.storage.sqlite import (
    add_watch_query,
    count_papers,
    database_connection,
    get_all_paper_report_rows,
    initialize_database,
    insert_papers,
    list_watch_queries,
    list_watch_query_rows,
    remove_watch_query,
)

logger = logging.getLogger(__name__)

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

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-watcher",
        description=(
            "Search scientific papers from "
            "PubMed and arXiv."
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
        help="Search configured scientific sources.",
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
            "Maximum number of papers to retrieve "
            "from each source (default: 5)."
        ),
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

    subparsers.add_parser(
        "list-queries",
        help="List stored watch queries.",
    )

    subparsers.add_parser(
        "report-all",
        help=(
            "Generate a Markdown report "
            "for all stored papers."
        ),
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

def run(
    query: str,
    max_results: int,
) -> None:
    """
    Run entry point for the application.
    """
    setup_logging()

    config = load_config()

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
        )

        pubmed_papers = fetch_pubmed_articles(
            pubmed_result.pmids
        )

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
        )

        arxiv_papers = (
            arxiv_result.papers
        )

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

        # Conserva aquí las impresiones que
        # ya utilizabas para arXiv.

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

    if successful_sources == 0:
        raise PaperWatcherError(
            "All paper sources failed: "
            + " | ".join(source_warnings)
        )

    all_papers = (
        pubmed_papers
        + arxiv_papers
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
        f"Total collected papers: "
        f"{len(all_papers)}"
    )

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

    print(
        f"Known papers: {insert_result.known_count}"
    )

    print(
        f"Total papers stored: {total_stored}"
    )

    report_path = write_markdown_report(
        report_dir=config.report_dir,
        query=common_query,
        papers=insert_result.new_papers,
        warnings=source_warnings,
    )

    print(
        f"Sources completed: "
        f"{successful_sources}/2"
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

def add_query_command(
    query: str,
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
        )

    if query_id is None:
        print(
            "Query already exists: "
            f"{normalized_query}"
        )
        return

    print(
        "Query added: "
        f"{normalized_query}"
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

    print(
        f"{'ID':<5} Query"
    )

    print(
        f"{'--':<5} "
        f"{'-' * 40}"
    )

    for row in query_rows:
        print(
            f"{row['id']:<5} "
            f"{row['query']}"
        )

def report_all_command() -> None:
    config = load_config()

    initialize_database(
        config.database_path
    )

    with database_connection(
        config.database_path
    ) as connection:
        rows = get_all_paper_report_rows(
            connection
        )

    report_path = write_all_papers_report(
        report_dir=config.report_dir,
        rows=rows,
    )

    print()
    print("=" * 70)
    print("ALL PAPERS REPORT")
    print("=" * 70)

    print(
        f"Rows: {len(rows)}"
    )

    print(
        f"Report written to: "
        f"{report_path}"
    )

def run_command(
    query: str | None,
    max_results: int,
) -> None:
    # Modo 1:
    # El usuario proporcionó una consulta concreta.
    if query is not None:
        run(
            query=query,
            max_results=max_results,
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
        queries = list_watch_queries(
            connection
        )

    if not queries:
        print("No stored queries.")
        return

    print()
    print("=" * 70)
    print("STORED QUERIES")
    print("=" * 70)

    print(
        f"Queries to run: {len(queries)}"
    )

    successful_queries = 0
    failed_queries = 0

    for index, stored_query in enumerate(
        queries,
        start=1,
    ):
        print()
        print("=" * 70)
        print(
            f"QUERY {index}/{len(queries)}"
        )
        print("=" * 70)

        print(
            f"Query: {stored_query}"
        )

        try:
            run(
                query=stored_query,
                max_results=max_results,
            )

            successful_queries += 1

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
        f"Queries processed: {len(queries)}"
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
            )

            return 0

        if args.command == "add-query":
            add_query_command(
                args.watch_query
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
            report_all_command()

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