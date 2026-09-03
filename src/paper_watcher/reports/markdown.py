from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from paper_watcher.models import Paper
from paper_watcher.storage.sqlite import (
    PaperReportRow,
)


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

    if paper.url:
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
        lines.append(
            paper.abstract.strip()
        )
    else:
        lines.append(
            "_Abstract not available._"
        )

    lines.append("")

    return "\n".join(lines)

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
