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

def run() -> None:
    """
    Run entry point for the application.
    """
    setup_logging()

    config = load_config()

    ensure_directories()

    query = "protein design"
    max_results = 5
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

    print(f"Request timeout: "
          f"{config.request_timeout} seconds")

def main() -> int:
    """
    Main function to run the application.
    """
    try:
        run()

    except PaperWatcherError as exc:
        logger.error("An error occurred: %s", exc)

        print()
        print("Scientific Paper Watcher failed:")
        print(exc)
        return 1

    return 0

if __name__ == "__main__":
    main()