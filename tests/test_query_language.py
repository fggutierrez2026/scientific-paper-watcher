from __future__ import annotations

import pytest

from paper_watcher.query_language import (
    QuerySyntaxError,
    normalize_common_query,
    to_arxiv_query,
    to_pubmed_query,
    tokenize_query,
)


class TestQueryTokenizer:
    def test_single_term(self):
        tokens = tokenize_query("protein")
        assert tokens == [("TERM", "protein")]

    def test_phrase(self):
        tokens = tokenize_query('"protein design"')
        assert tokens == [("PHRASE", "protein design")]

    def test_plus_alias_for_and(self):
        tokens = tokenize_query('"GBP protein" + "biological sensor"')
        assert tokens == [
            ("PHRASE", "GBP protein"),
            ("OP", "AND"),
            ("PHRASE", "biological sensor"),
        ]

    def test_complex_boolean_with_parentheses(self):
        query = '("glucose binding protein" OR GGBP) AND (biosensor OR "biological sensor")'
        tokens = tokenize_query(query)
        assert tokens == [
            ("LPAREN", "("),
            ("PHRASE", "glucose binding protein"),
            ("OP", "OR"),
            ("TERM", "GGBP"),
            ("RPAREN", ")"),
            ("OP", "AND"),
            ("LPAREN", "("),
            ("TERM", "biosensor"),
            ("OP", "OR"),
            ("PHRASE", "biological sensor"),
            ("RPAREN", ")"),
        ]

    def test_not_operator(self):
        tokens = tokenize_query('crispr NOT "cas9"')
        assert tokens == [
            ("TERM", "crispr"),
            ("OP", "NOT"),
            ("PHRASE", "cas9"),
        ]

    @pytest.mark.parametrize(
        "invalid_query, error_substring",
        [
            ("", "Query cannot be empty"),
            ("   ", "Query cannot be empty"),
            ('"unclosed phrase', "Unclosed quoted phrase"),
            ('""', "Quoted phrase cannot be empty"),
            ('"   "', "Quoted phrase cannot be empty"),
            ("AND protein", "Unexpected Boolean operator 'AND'"),
            ("protein AND", "Query cannot end with a Boolean operator"),
            ("protein AND AND design", "Unexpected Boolean operator 'AND'"),
            ('"protein" "design"', "Missing Boolean operator"),
            ("(protein", "Unclosed parenthesis"),
            ("protein)", "Unexpected ')'"),
            ("()", "Empty or incomplete parenthesized expression"),
            ("( )", "Empty or incomplete parenthesized expression"),
        ],
    )
    def test_syntax_errors(self, invalid_query: str, error_substring: str):
        with pytest.raises(QuerySyntaxError) as exc_info:
            tokenize_query(invalid_query)
        assert error_substring in str(exc_info.value)


class TestQueryNormalization:
    def test_plus_normalization(self):
        normalized = normalize_common_query('"GBP protein" + "biological sensor"')
        assert normalized == '"GBP protein" AND "biological sensor"'

    def test_spacing_normalization(self):
        normalized = normalize_common_query('  ( "protein"   OR   "peptide" )  AND biosensor  ')
        assert normalized == '( "protein" OR "peptide" ) AND biosensor'


class TestQueryTranslation:
    def test_pubmed_translation(self):
        query = '("GBP protein" OR GGBP) AND biosensor'
        translated = to_pubmed_query(query)
        assert translated == '( "GBP protein" OR GGBP ) AND biosensor'

    def test_arxiv_translation_terms(self):
        query = "protein"
        translated = to_arxiv_query(query)
        assert translated == "all:protein"

    def test_arxiv_translation_multiword_phrase(self):
        phrase_q = '"alphafold prediction"'
        assert to_arxiv_query(phrase_q) == 'all:"alphafold prediction"'

    def test_arxiv_translation_compound(self):
        query = '("GBP protein" OR GGBP) AND (biosensor OR "biological sensor")'
        translated = to_arxiv_query(query)
        assert translated == (
            '( all:"GBP protein" OR all:GGBP ) AND ( all:biosensor OR all:"biological sensor" )'
        )

    def test_arxiv_not_translation_to_andnot(self):
        query = 'crispr NOT "cas9"'
        translated = to_arxiv_query(query)
        assert translated == 'all:crispr ANDNOT all:"cas9"'
