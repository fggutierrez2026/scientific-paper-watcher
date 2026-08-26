import argparse
from paper_watcher import __version__
from paper_watcher.config import load_config
from paper_watcher.sources.pubmed import search_pubmed
from paper_watcher.logging_config import setup_logging

from paper_watcher.sources.pubmed import (
    fetch_pubmed_articles,
    search_pubmed,
)

from paper_watcher.sources.arxiv import search_arxiv

import logging

from paper_watcher.exceptions import PaperWatcherError

from paper_watcher.storage.sqlite import (
    count_papers,
    database_connection,
    initialize_database,
    insert_papers,
    add_watch_query,
    list_watch_queries,
)

from paper_watcher.reports.markdown import (
    write_markdown_report,
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
        "--query",
        type=_non_empty_text,
        help="Scientific search query.",
    )

    parser.add_argument(
        "--max-results",
        type=_positive_int,
        default=5,
        help=(
            "Maximum number of papers to retrieve "
            "from each source (default: 5)."
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(
        dest="command",
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

    initialize_database(
        config.database_path
    )

    ensure_directories()

    print()
    print("=" * 70)
    print("PUBMED")
    print("=" * 70)

    pubmed_result = search_pubmed(
        query,
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

    print()
    print("=" * 70)
    print("ARXIV")
    print("=" * 70)

    arxiv_result = search_arxiv(
        query,
        max_results=max_results,
    )

    print(
        f"Total arXiv results: "
        f"{arxiv_result.total_count}"
    )
    print(
        f"Articles retrieved: "
        f"{len(arxiv_result.papers)}"
    )
    print()

    for paper in arxiv_result.papers:
        print_paper(paper)

    all_papers = (pubmed_papers + arxiv_result.papers)

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
        f"{len(arxiv_result.papers)}"
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

        inserted_ids = insert_papers(
            connection,
            all_papers,
        )

        total_stored = count_papers(
            connection
        )

    print(
        f"Database: "
        f"{config.database_path}"
    )

    print(
        f"Papers inserted: "
        f"{len(inserted_ids)}"
    )

    print(
        f"Total papers stored: "
        f"{total_stored}"
    )

    report_path = write_markdown_report(
        report_dir=config.report_dir,
        query=query,
        papers=all_papers,
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

    initialize_database(
        config.database_path
    )

    with database_connection(
        config.database_path
    ) as connection:
        query_id = add_watch_query(
            connection,
            query,
        )

    if query_id is None:
        print(
            f"Query already exists: {query}"
        )
        return

    print(
        f"Query added: {query}"
    )

def list_queries_command() -> None:
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

    print("Stored queries:")
    print()

    for index, query in enumerate(
        queries,
        start=1,
    ):
        print(
            f"{index}. {query}"
        )

def main(
    argv: list[str] | None = None,
) -> int:
    setup_logging()

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "add-query":
            add_query_command(
                args.watch_query
            )
            return 0

        if args.command == "list-queries":
            list_queries_command()
            return 0

        if args.query is None:
            parser.error(
                "--query is required unless using "
                "add-query or list-queries"
            )

        run(
            query=args.query,
            max_results=args.max_results,
        )

    except PaperWatcherError as exc:
        logger.error(
            "Scientific Paper Watcher failed: %s",
            exc,
        )

        print()
        print("Scientific Paper Watcher failed:")
        print(exc)

        return 1

    return 0

if __name__ == "__main__":
    main()