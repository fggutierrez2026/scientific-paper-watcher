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
