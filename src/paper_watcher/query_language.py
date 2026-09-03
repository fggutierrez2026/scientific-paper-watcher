from __future__ import annotations

import ast
import re

from paper_watcher.exceptions import (
    PaperWatcherError,
)


class QuerySyntaxError(
    PaperWatcherError
):
    """
    Raised when a common watcher query
    has invalid syntax.
    """


_BOOLEAN_RE = re.compile(
    r"(AND|OR|NOT)\b",
    re.IGNORECASE,
)


QueryToken = tuple[str, str]


def _clean_term(
    value: str,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        value.strip(),
    )


def tokenize_query(
    query: str,
) -> list[QueryToken]:
    query = query.strip()

    if not query:
        raise QuerySyntaxError(
            "Query cannot be empty"
        )

    tokens: list[QueryToken] = []

    buffer: list[str] = []

    def flush_term() -> None:
        if not buffer:
            return

        term = _clean_term(
            "".join(buffer)
        )

        buffer.clear()

        if term:
            tokens.append(
                (
                    "TERM",
                    term,
                )
            )

    index = 0

    while index < len(query):
        char = query[index]

        if char == '"':
            flush_term()

            closing = query.find(
                '"',
                index + 1,
            )

            if closing == -1:
                raise QuerySyntaxError(
                    "Unclosed quoted phrase"
                )

            phrase = _clean_term(
                query[
                    index + 1:
                    closing
                ]
            )

            if not phrase:
                raise QuerySyntaxError(
                    "Quoted phrase cannot be empty"
                )

            tokens.append(
                (
                    "PHRASE",
                    phrase,
                )
            )

            index = closing + 1
            continue

        if char == "(":
            flush_term()

            tokens.append(
                (
                    "LPAREN",
                    char,
                )
            )

            index += 1
            continue

        if char == ")":
            flush_term()

            tokens.append(
                (
                    "RPAREN",
                    char,
                )
            )

            index += 1
            continue

        if char == "+":
            flush_term()

            tokens.append(
                (
                    "OP",
                    "AND",
                )
            )

            index += 1
            continue

        operator_match = (
            _BOOLEAN_RE.match(
                query,
                index,
            )
        )

        if operator_match is not None:
            previous_is_boundary = (
                index == 0
                or query[index - 1].isspace()
                or query[index - 1] in "()"
            )

            end = operator_match.end()

            next_is_boundary = (
                end == len(query)
                or query[end].isspace()
                or query[end] in "()"
            )

            if (
                previous_is_boundary
                and next_is_boundary
            ):
                flush_term()

                tokens.append(
                    (
                        "OP",
                        operator_match
                        .group(1)
                        .upper(),
                    )
                )

                index = end
                continue

        buffer.append(
            char
        )

        index += 1

    flush_term()

    validate_query_tokens(
        tokens
    )

    return tokens

def validate_query_tokens(
    tokens: list[QueryToken],
) -> None:
    if not tokens:
        raise QuerySyntaxError(
            "Query cannot be empty"
        )

    expecting_operand = True

    parenthesis_depth = 0

    for token_type, token_value in tokens:
        if token_type in {
            "TERM",
            "PHRASE",
        }:
            if not expecting_operand:
                raise QuerySyntaxError(
                    "Missing Boolean operator "
                    f"before {token_value!r}"
                )

            expecting_operand = False
            continue

        if token_type == "LPAREN":
            if not expecting_operand:
                raise QuerySyntaxError(
                    "Missing Boolean operator "
                    "before '('"
                )

            parenthesis_depth += 1
            continue

        if token_type == "RPAREN":
            if parenthesis_depth == 0:
                raise QuerySyntaxError(
                    "Unexpected ')'"
                )

            if expecting_operand:
                raise QuerySyntaxError(
                    "Empty or incomplete "
                    "parenthesized expression"
                )

            parenthesis_depth -= 1
            expecting_operand = False
            continue

        if token_type == "OP":
            if expecting_operand:
                raise QuerySyntaxError(
                    "Unexpected Boolean operator "
                    f"{token_value!r}"
                )

            expecting_operand = True
            continue

        raise QuerySyntaxError(
            f"Unknown token type: "
            f"{token_type}"
        )

    if parenthesis_depth != 0:
        raise QuerySyntaxError(
            "Unclosed parenthesis"
        )

    if expecting_operand:
        raise QuerySyntaxError(
            "Query cannot end with "
            "a Boolean operator"
        )

def normalize_common_query(
    query: str,
) -> str:
    tokens = tokenize_query(
        query
    )

    parts: list[str] = []

    for token_type, value in tokens:
        if token_type == "PHRASE":
            parts.append(
                f'"{value}"'
            )

        elif token_type == "TERM" or token_type == "OP":
            parts.append(
                value
            )

        elif token_type == "LPAREN":
            parts.append(
                "("
            )

        elif token_type == "RPAREN":
            parts.append(
                ")"
            )

    return " ".join(
        parts
    )

def to_pubmed_query(
    query: str,
) -> str:
    return normalize_common_query(
        query
    )

def _arxiv_term(
    term: str,
) -> str:
    words = term.split()

    if len(words) == 1:
        return (
            f"all:{words[0]}"
        )

    translated = [
        f"all:{word}"
        for word in words
    ]

    return (
        "("
        + " AND ".join(
            translated
        )
        + ")"
    )

def to_arxiv_query(
    query: str,
) -> str:
    tokens = tokenize_query(
        query
    )

    parts: list[str] = []

    for token_type, value in tokens:
        if token_type == "TERM":
            parts.append(
                _arxiv_term(
                    value
                )
            )

        elif token_type == "PHRASE":
            parts.append(
                f'all:"{value}"'
            )

        elif token_type == "OP":
            if value == "NOT":
                parts.append(
                    "ANDNOT"
                )
            else:
                parts.append(
                    value
                )

        elif token_type == "LPAREN":
            parts.append(
                "("
            )

        elif token_type == "RPAREN":
            parts.append(
                ")"
            )

    return " ".join(
        parts
    )


def _eval_bool_ast(node: ast.AST) -> bool:
    if isinstance(node, ast.Expression):
        return _eval_bool_ast(node.body)
    elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_bool_ast(node.operand)
    elif isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval_bool_ast(val) for val in node.values)
        elif isinstance(node.op, ast.Or):
            return any(_eval_bool_ast(val) for val in node.values)
    raise ValueError(f"Unsupported AST node: {type(node)}")


def matches_query(
    query: str,
    text: str,
) -> bool:
    """
    Evaluates whether `text` satisfies the compound boolean `query`.

    Tokenizes `query`, checks presence of terms and phrases in `text` (case-insensitive),
    and safely evaluates the resulting boolean logic expression.
    """
    tokens = tokenize_query(query)
    lower_text = text.lower()

    expr_parts: list[str] = []
    for token_type, value in tokens:
        if token_type == "TERM":
            words = value.lower().split()
            term_match = all(w in lower_text for w in words)
            expr_parts.append(str(term_match))
        elif token_type == "PHRASE":
            phrase_match = value.lower() in lower_text
            expr_parts.append(str(phrase_match))
        elif token_type == "OP":
            if value == "NOT":
                expr_parts.append("and not")
            elif value == "AND":
                expr_parts.append("and")
            elif value == "OR":
                expr_parts.append("or")
        elif token_type == "LPAREN":
            expr_parts.append("(")
        elif token_type == "RPAREN":
            expr_parts.append(")")

    expr_str = " ".join(expr_parts)
    try:
        parsed = ast.parse(expr_str, mode="eval")
        return _eval_bool_ast(parsed)
    except Exception as exc:
        raise QuerySyntaxError(
            f"Failed to evaluate query match: {exc}"
        ) from exc
