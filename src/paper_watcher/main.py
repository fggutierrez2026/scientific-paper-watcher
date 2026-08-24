from paper_watcher.config import load_config
from paper_watcher.sources.pubmed import search_pubmed
from paper_watcher.logging_config import setup_logging

from paper_watcher.sources.pubmed import (
    fetch_pubmed_articles,
    search_pubmed,
)

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

def run() -> None:
    """
    Run entry point for the application.
    """
    setup_logging()

    config = load_config()

    ensure_directories()

    query = "protein design"

    print("Scientific Paper Watcher")
    print("-------------------------")
    print(f"Searching PubMed for query: '{query}'")
    print()

    result = search_pubmed(query=query,
                           max_results=5,
    )

    print(f"Results found: {result.total_count}")
    print()

    papers = fetch_pubmed_articles(result.pmids)
    print(f"Articles retrieved: {len(papers)}")
    print()

    for index, paper in enumerate(papers, start=1):
        print(f"{index}. {paper.title}")
        print(f"   PMID: {paper.external_id}")

        if paper.authors:
            authors = ", ".join(paper.authors[:3])

            if len(paper.authors) > 3:
                authors += ", et al."

            print(f"   Authors: {authors}")

        print(f"   Journal: {paper.journal}")
        print(f"   Publication date: {paper.publication_date}")
        print(f"   Electronic date: {paper.electronic_date}")
        print(f"   PubMed date: {paper.pubmed_date}")
        print(f"   DOI: {paper.doi}")
        print()

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