from __future__ import annotations

from paper_watcher.normalization import normalize_doi, normalize_title


def test_normalize_doi():
    assert normalize_doi(None) is None
    assert normalize_doi("") is None
    assert normalize_doi("   ") is None
    assert normalize_doi("10.1000/182") == "10.1000/182"
    assert normalize_doi("https://doi.org/10.1000/182") == "10.1000/182"
    assert normalize_doi("http://doi.org/10.1000/182") == "10.1000/182"
    assert normalize_doi("doi:10.1000/182") == "10.1000/182"
    assert normalize_doi("  DOI:10.1000/182  ") == "10.1000/182"


def test_normalize_title():
    assert normalize_title("  De Novo  Protein   Design  ") == "de novo protein design"
    assert normalize_title("A Study ON CRISPR/Cas9") == "a study on crispr/cas9"

