from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from paper_watcher.models import Paper, Patent
from paper_watcher.storage.sqlite import PaperReportRow

LATEX_TEXT_COMMAND = re.compile(
    r"\\(?:emph|mbox|mathbf|mathit|mathrm|text|textbf|textit|underline)"
    r"\{([^{}]*)\}"
)
SIMPLE_TEXT_MATH = re.compile(r"\$([A-Za-z][A-Za-z0-9 .,'-]*)\$")
LATEX_ESCAPED_PUNCTUATION = re.compile(r"\\([%&#_$])")


def format_arxiv_abstract(abstract: str) -> str:
    """Make text-oriented arXiv LaTeX readable without flattening formulas."""
    formatted = abstract.replace("~", " ")

    # Commands can be nested, for example ``\underline{\text{r}}``.
    while True:
        unwrapped = LATEX_TEXT_COMMAND.sub(r"\1", formatted)
        if unwrapped == formatted:
            break
        formatted = unwrapped

    # Remove math delimiters only from text fragments. Mathematical expressions
    # such as ``$E=mc^2$`` remain intact for Markdown renderers with math support.
    formatted = SIMPLE_TEXT_MATH.sub(r"\1", formatted)
    formatted = LATEX_ESCAPED_PUNCTUATION.sub(r"\1", formatted)
    return re.sub(r"\s+", " ", formatted).strip()


def slugify_query(
    query: str,
) -> str:
    slug = query.strip().lower()

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        slug,
    )

    slug = slug.strip("-")

    return slug or "report"

def render_paper_markdown(
    paper: Paper,
) -> str:
    lines: list[str] = []

    lines.append(
        f"## {paper.title}"
    )

    lines.append("")

    if paper.is_preprint_and_peer_reviewed:
        lines.append("> [!NOTE]")
        preprint_sources = [
            s for s in paper.sources
            if s.lower() in {"arxiv", "biorxiv", "medrxiv"}
        ]
        prep_str = (
            ", ".join(s.upper() for s in preprint_sources)
            if preprint_sources
            else "preprint"
        )
        lines.append(
            f"> **Publicación multi-fuente:** Este trabajo fue avistado tanto como preprint en **{prep_str}** como en revista indexada en **PubMed**."
        )
        lines.append("")

    if paper.is_cross_source:
        header_sources = ", ".join(s.upper() for s in paper.sources)
        lines.append(
            f"**{header_sources}**"
        )
        lines.append("")
        lines.append(
            f"- **Sources:** {', '.join(paper.sources)}"
        )
        if paper.external_ids:
            ext_ids_str = ", ".join(
                f"{src}: {eid}"
                for src, eid in paper.external_ids.items()
            )
            lines.append(
                f"- **External IDs:** {ext_ids_str}"
            )
    else:
        lines.append(
            f"**{paper.source.upper()}**"
        )
        lines.append("")
        lines.append(
            f"- **Source:** {paper.source}"
        )
        lines.append(
            f"- **External ID:** {paper.external_id}"
        )

    if paper.published:
        lines.append(
            f"- **Published:** {paper.published}"
        )

    if paper.journal:
        lines.append(
            f"- **Journal:** {paper.journal}"
        )

    if paper.doi:
        lines.append(
            f"- **DOI:** {paper.doi}"
        )

    if paper.openalex_id:
        lines.append(
            f"- **OpenAlex:** [{paper.openalex_id}]({paper.openalex_id})"
        )

    if paper.citation_count is not None:
        citation_source = (
            "OpenAlex"
            if paper.openalex_id
            else paper.source.replace("_", " ").title()
        )
        lines.append(
            f"- **Citations ({citation_source}):** {paper.citation_count}"
        )

    if paper.topics:
        lines.append(
            f"- **Topics:** {', '.join(paper.topics)}"
        )

    if paper.pdf_url:
        lines.append(
            f"- **Open-access PDF:** [Download PDF]({paper.pdf_url})"
        )

    if paper.is_cross_source and paper.source_urls:
        links_str = " | ".join(
            f"[{src.capitalize()}]({url})"
            for src, url in paper.source_urls.items()
        )
        lines.append(
            f"- **URLs:** {links_str}"
        )
    elif paper.url:
        lines.append(
            f"- **URL:** {paper.url}"
        )

    if paper.authors:
        lines.append(
            "- **Authors:** "
            + ", ".join(paper.authors)
        )

    lines.append("")

    if paper.abstract:
        abstract = paper.abstract.strip()
        if any(source.lower() == "arxiv" for source in paper.sources):
            abstract = format_arxiv_abstract(abstract)
        lines.append(
            abstract
        )
    else:
        lines.append(
            "_Abstract not available._"
        )

    lines.append("")

    return "\n".join(lines)


def render_patent_markdown(patent: Patent) -> str:
    lines = [f"### {patent.title}", "", f"**{patent.source.upper()}**", ""]
    if patent.publication_number:
        lines.append(f"- **Publication number:** {patent.publication_number}")
    if patent.application_number:
        lines.append(f"- **Application number:** {patent.application_number}")
    lines.append(f"- **Jurisdiction:** {patent.jurisdiction}")
    if patent.publication_date:
        lines.append(f"- **Published:** {patent.publication_date}")
    if patent.priority_date:
        lines.append(f"- **Priority:** {patent.priority_date}")
    if patent.family_id:
        lines.append(f"- **Family:** {patent.family_id}")
    if patent.applicants:
        lines.append(f"- **Applicants:** {', '.join(patent.applicants)}")
    if patent.inventors:
        lines.append(f"- **Inventors:** {', '.join(patent.inventors)}")
    if patent.cpc_codes:
        lines.append(f"- **CPC:** {', '.join(patent.cpc_codes)}")
    if patent.ipc_codes:
        lines.append(f"- **IPC:** {', '.join(patent.ipc_codes)}")
    if patent.url:
        lines.append(f"- **URL:** {patent.url}")
    lines.extend(["", patent.abstract.strip() if patent.abstract else "_Abstract not available._", ""])
    return "\n".join(lines)


def render_scoped_report_markdown(
    query: str,
    papers: list[Paper],
    patents: list[Patent],
    *,
    scope: str,
    generated_at: datetime | None = None,
    warnings: list[str] | None = None,
) -> str:
    generated_at = generated_at or datetime.now().astimezone()
    warnings = warnings or []
    lines = [
        "# Scientific Paper Watcher Search Report",
        "",
        f"**Query:** {query}",
        f"**Scope:** {scope}",
        f"**Generated:** {generated_at.isoformat(timespec='seconds')}",
        f"**Papers:** {len(papers)}",
        f"**Patents:** {len(patents)}",
        "",
    ]
    if warnings:
        lines.extend(["## Source warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    if scope in {"papers", "all"}:
        lines.extend(["## Papers", ""])
        if papers:
            for paper in papers:
                rendered = render_paper_markdown(paper)
                lines.append(rendered.replace("## ", "### ", 1))
        else:
            lines.extend(["_No new papers found._", ""])

    if scope in {"patents", "all"}:
        lines.extend(["## Patents", ""])
        if patents:
            lines.extend(render_patent_markdown(patent) for patent in patents)
        else:
            lines.extend(["_No new patents found._", ""])

    return "\n".join(lines)


def write_scoped_markdown_report(
    report_dir: Path,
    query: str,
    papers: list[Paper],
    patents: list[Patent],
    *,
    scope: str,
    generated_at: datetime | None = None,
    warnings: list[str] | None = None,
) -> Path:
    generated_at = generated_at or datetime.now().astimezone()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / (
        f"{slugify_query(query)}_{scope}_"
        f"{generated_at.strftime('%Y-%m-%d_%H%M%S')}.md"
    )
    report_path.write_text(
        render_scoped_report_markdown(
            query,
            papers,
            patents,
            scope=scope,
            generated_at=generated_at,
            warnings=warnings,
        ),
        encoding="utf-8",
    )
    return report_path

def render_report_markdown(
    query: str,
    papers: list[Paper],
    generated_at: datetime | None = None,
    warnings: list[str] | None = None,
) -> str:
    if generated_at is None:
        generated_at = (
            datetime.now().astimezone()
        )

    if warnings is None:
        warnings = []
    
    lines: list[str] = []

    lines.append(
        "# Scientific Paper Watcher Report"
    )

    lines.append("")

    lines.append(
        f"**Query:** {query}"
    )

    lines.append("")

    lines.append(
        "**Generated:** "
        f"{generated_at.isoformat(timespec='seconds')}"
    )

    lines.append("")

    lines.append(
        f"**New Papers:** {len(papers)}"
    )

    merged_count = sum(
        1 for p in papers if p.is_cross_source
    )
    if merged_count > 0:
        lines.append(
            f"**Cross-source Merged:** {merged_count}"
        )

    lines.append("")

    if warnings:
        lines.append(
            "## Source warnings"
        )

        lines.append("")

        for warning in warnings:
            lines.append(
                f"- {warning}"
            )

        lines.append("")

    lines.append("---")
    lines.append("")

    if not papers:
        if warnings:
            lines.append(
                "_No new papers found among sources "
                "that completed successfully._"
            )
        else:
            lines.append(
                "_No new papers found._"
            )

        lines.append("")

        return "\n".join(lines)

    for index, paper in enumerate(
        papers
    ):
        lines.append(
            render_paper_markdown(
                paper
            )
        )

        if index < len(papers) - 1:
            lines.append("---")
            lines.append("")

    return "\n".join(lines)

def write_markdown_report(
    report_dir: Path,
    query: str,
    papers: list[Paper],
    generated_at: datetime | None = None,
    warnings: list[str] | None = None,
) -> Path:
    if generated_at is None:
        generated_at = datetime.now().astimezone()

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        f"{slugify_query(query)}_"
        f"{generated_at.strftime('%Y-%m-%d_%H%M%S')}"
        ".md"
    )

    report_path = (
        report_dir
        / filename
    )

    content = render_report_markdown(
        query=query,
        papers=papers,
        generated_at=generated_at,
        warnings=warnings,
    )

    report_path.write_text(
        content,
        encoding="utf-8",
    )

    return report_path

def escape_markdown_table_cell(
    value: str,
) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )

def render_all_papers_report_markdown(
    rows: list[PaperReportRow],
    generated_at: datetime | None = None,
) -> str:
    if generated_at is None:
        generated_at = (
            datetime.now().astimezone()
        )

    lines = [
        "# Scientific Paper Watcher - All Papers",
        "",
        (
            "**Generated:** "
            f"{generated_at.isoformat()}"
        ),
        "",
        f"**Rows:** {len(rows)}",
        "",
    ]

    if not rows:
        lines.append(
            "_No papers stored._"
        )
        lines.append("")

        return "\n".join(lines)

    lines.extend(
        [
            "| Query | Title | Authors | Source | URL |",
            "|---|---|---|---|---|",
        ]
    )

    for row in rows:
        query = (
            row.query
            if row.query is not None
            else "legacy / unknown"
        )

        authors = ", ".join(
            row.authors
        )

        url = row.url or ""

        cells = [
            query,
            row.title,
            authors,
            row.source,
            url,
        ]

        cells = [
            escape_markdown_table_cell(
                cell
            )
            for cell in cells
        ]

        lines.append(
            "| "
            + " | ".join(cells)
            + " |"
        )

    lines.append("")

    return "\n".join(lines)

def write_all_papers_report(
    report_dir: Path,
    rows: list[PaperReportRow],
    generated_at: datetime | None = None,
) -> Path:
    if generated_at is None:
        generated_at = (
            datetime.now().astimezone()
        )

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = generated_at.strftime(
        "%Y-%m-%d_%H%M%S"
    )

    report_path = (
        report_dir
        / f"all-papers_{timestamp}.md"
    )

    content = (
        render_all_papers_report_markdown(
            rows=rows,
            generated_at=generated_at,
        )
    )

    report_path.write_text(
        content,
        encoding="utf-8",
    )

    return report_path
