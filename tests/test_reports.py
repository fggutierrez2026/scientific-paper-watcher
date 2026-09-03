from __future__ import annotations

from pathlib import Path
from paper_watcher.models import Paper
from paper_watcher.reports.markdown import (
    escape_markdown_table_cell,
    render_all_papers_report_markdown,
    render_paper_markdown,
    render_report_markdown,
    slugify_query,
    write_all_papers_report,
    write_markdown_report,
)
from paper_watcher.storage.sqlite import PaperReportRow


def test_slugify_query():
    assert slugify_query("protein design") == "protein-design"
    assert slugify_query('("GBP protein" OR GGBP)') == "gbp-protein-or-ggbp"
    assert slugify_query("   ") == "report"


def test_escape_markdown_table_cell():
    raw = "Line 1\nLine 2 | Special\\Char"
    escaped = escape_markdown_table_cell(raw)
    assert "\n" not in escaped
    assert "\\|" in escaped
    assert "\\\\" in escaped


def test_render_and_write_markdown_report(tmp_path: Path, sample_paper: Paper):
    report_path = write_markdown_report(
        report_dir=tmp_path,
        query="protein design",
        papers=[sample_paper],
        warnings=["Source X degraded"],
    )
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "# Scientific Paper Watcher Report" in content
    assert "**Query:** protein design" in content
    assert "Source X degraded" in content
    assert sample_paper.title in content
    assert sample_paper.external_id in content


def test_render_and_write_all_papers_report(tmp_path: Path):
    rows = [
        PaperReportRow(
            query="protein design",
            title="Design of Novel Enzymes",
            authors=["Alice", "Bob"],
            source="pubmed",
            url="https://example.com/1",
        ),
        PaperReportRow(
            query=None,
            title="Legacy Paper",
            authors=["Charlie"],
            source="arxiv",
            url="https://example.com/2",
        ),
    ]
    report_path = write_all_papers_report(
        report_dir=tmp_path,
        rows=rows,
    )
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "| Query | Title | Authors | Source | URL |" in content
    assert "legacy / unknown" in content
    assert "Design of Novel Enzymes" in content

