from __future__ import annotations

from pathlib import Path

from paper_watcher.models import Paper
from paper_watcher.reports.markdown import (
    escape_markdown_table_cell,
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


def test_render_paper_markdown_cross_source(tmp_path: Path):
    cross_paper = Paper(
        source="arxiv",
        external_id="2608.12345",
        title="Multi-Source Synthesis of GFP",
        authors=["Alice", "Bob"],
        abstract="Dual discovery abstract.",
        journal="Science",
        publication_date="2026-08-01",
        electronic_date=None,
        pubmed_date="2026-08-20",
        doi="10.1038/nature12345",
        url="https://arxiv.org/abs/2608.12345",
        sources=["arxiv", "pubmed"],
        external_ids={"arxiv": "2608.12345", "pubmed": "42111111"},
        source_urls={
            "arxiv": "https://arxiv.org/abs/2608.12345",
            "pubmed": "https://pubmed.ncbi.nlm.nih.gov/42111111/",
        },
    )

    report_path = write_markdown_report(
        report_dir=tmp_path,
        query="gfp synthesis",
        papers=[cross_paper],
    )
    content = report_path.read_text(encoding="utf-8")
    assert "> [!NOTE]" in content
    assert "Publicación multi-fuente" in content
    assert "**ARXIV, PUBMED**" in content
    assert "- **Sources:** arxiv, pubmed" in content
    assert "arxiv: 2608.12345" in content
    assert "pubmed: 42111111" in content
    assert "[Arxiv](https://arxiv.org/abs/2608.12345)" in content
    assert "[Pubmed](https://pubmed.ncbi.nlm.nih.gov/42111111/)" in content
    assert "**Cross-source Merged:** 1" in content

