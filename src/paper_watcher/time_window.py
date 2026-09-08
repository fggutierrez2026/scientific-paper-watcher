from __future__ import annotations

from datetime import UTC, datetime, timedelta


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_since_date(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("must use YYYY-MM-DD format") from exc
    return parsed.replace(tzinfo=UTC)


def parse_checkpoint(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid stored checkpoint: {value!r}") from exc
    return as_utc(parsed)


def since_days(days: int, until: datetime) -> datetime:
    if days < 1:
        raise ValueError("days must be greater than or equal to 1")
    return as_utc(until) - timedelta(days=days)


def validate_window(
    since: datetime | None,
    until: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    normalized_since = as_utc(since) if since is not None else None
    normalized_until = as_utc(until) if until is not None else None

    if normalized_since is not None and normalized_until is None:
        normalized_until = datetime.now(UTC)
    if (
        normalized_since is not None
        and normalized_until is not None
        and normalized_since > normalized_until
    ):
        raise ValueError("since must not be later than until")

    return normalized_since, normalized_until


def format_pubmed_date(value: datetime) -> str:
    return as_utc(value).strftime("%Y/%m/%d")


def format_arxiv_date(value: datetime) -> str:
    return as_utc(value).strftime("%Y%m%d%H%M")


def format_biorxiv_date(value: datetime) -> str:
    return as_utc(value).strftime("%Y-%m-%d")
