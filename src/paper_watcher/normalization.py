from __future__ import annotations

import re


def normalize_doi(
    doi: str | None,
) -> str | None:
    if doi is None:
        return None

    normalized = doi.strip().lower()

    if not normalized:
        return None

    prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "doi:",
    )

    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[
                len(prefix):
            ].strip()

    return normalized or None


def normalize_title(
    title: str,
) -> str:
    normalized = title.strip().lower()

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    )

    return normalized


def normalize_patent_jurisdiction(
    jurisdiction: str,
) -> str:
    return re.sub(r"[^A-Z0-9]", "", jurisdiction.upper())


def normalize_patent_number(
    number: str | None,
) -> str | None:
    if number is None:
        return None

    normalized = re.sub(r"[^A-Z0-9]", "", number.upper())
    return normalized or None
