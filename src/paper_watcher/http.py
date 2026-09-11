from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from paper_watcher.exceptions import (
    APIError,
    NetworkError,
    RateLimitError,
    RequestTimeoutError,
    ServiceUnavailableError,
)

logger = logging.getLogger(__name__)

RETRYABLE_EXCEPTIONS = (
    RequestTimeoutError,
    NetworkError,
    RateLimitError,
    ServiceUnavailableError,
)

SENSITIVE_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "consumer_key",
        "consumer_secret",
        "email",
        "mailto",
        "password",
        "token",
        "username",
    }
)


@dataclass(frozen=True)
class HttpPolicy:
    timeout: int
    max_retries: int
    backoff_min: float = 1.0
    backoff_max: float = 30.0

    def __post_init__(self) -> None:
        if self.timeout < 1:
            raise ValueError("HTTP timeout must be greater than or equal to 1")
        if self.max_retries < 0:
            raise ValueError("HTTP max_retries cannot be negative")


class HttpClient:
    """Shared timeout, retry and safe-error behavior for provider adapters."""

    def __init__(
        self,
        policy: HttpPolicy,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.policy = policy
        self.session = session or requests.Session()

    def request(
        self,
        method: str,
        url: str,
        *,
        provider: str,
        response_validator: Callable[[requests.Response], None] | None = None,
        allowed_statuses: Collection[int] = (),
        **kwargs: Any,
    ) -> requests.Response:
        retryer = Retrying(
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
            stop=stop_after_attempt(self.policy.max_retries + 1),
            wait=self._retry_wait,
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        return retryer(
            self._request_once,
            method,
            url,
            provider,
            response_validator,
            frozenset(allowed_statuses),
            kwargs,
        )

    def _request_once(
        self,
        method: str,
        url: str,
        provider: str,
        response_validator: Callable[[requests.Response], None] | None,
        allowed_statuses: frozenset[int],
        kwargs: dict[str, Any],
    ) -> requests.Response:
        safe_url = redact_url(url)
        try:
            response = self.session.request(
                method,
                url,
                timeout=self.policy.timeout,
                **kwargs,
            )
        except requests.exceptions.Timeout as exc:
            raise RequestTimeoutError(
                f"{provider} request timed out after {self.policy.timeout} seconds"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise NetworkError(f"Could not connect to {provider}") from exc
        except requests.exceptions.RequestException as exc:
            raise APIError(
                f"Unexpected error while requesting {provider} at {safe_url}"
            ) from exc

        if response.status_code == 429:
            raise RateLimitError(
                f"{provider} rate limit reached (HTTP 429)",
                retry_after=parse_retry_after(response.headers.get("Retry-After")),
            )
        if 500 <= response.status_code < 600:
            raise ServiceUnavailableError(
                f"{provider} service temporarily unavailable "
                f"(HTTP {response.status_code})"
            )
        if response_validator is not None:
            response_validator(response)
        if response.status_code in allowed_statuses:
            return response
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise APIError(
                f"{provider} returned HTTP {response.status_code} at {safe_url}"
            ) from exc
        return response

    def _retry_wait(self, retry_state: Any) -> float:
        if retry_state.outcome is not None:
            exception = retry_state.outcome.exception()
            if (
                isinstance(exception, RateLimitError)
                and exception.retry_after is not None
            ):
                return exception.retry_after
        fallback = wait_exponential(
            multiplier=1,
            min=self.policy.backoff_min,
            max=self.policy.backoff_max,
        )
        return float(fallback(retry_state))


def parse_retry_after(
    value: str | None, *, now: datetime | None = None
) -> float | None:
    if not value:
        return None
    cleaned = value.strip()
    try:
        return max(0.0, float(cleaned))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    return max(0.0, (retry_at - current).total_seconds())


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow copy safe for diagnostic logging."""
    return {
        key: "[REDACTED]" if _is_sensitive(key) else value
        for key, value in values.items()
    }


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    safe_query = urlencode(
        [
            (key, "[REDACTED]" if _is_sensitive(key) else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ],
        safe="[]",
    )
    safe_netloc = parts.hostname or ""
    if parts.port is not None:
        safe_netloc = f"{safe_netloc}:{parts.port}"
    return urlunsplit(
        (parts.scheme, safe_netloc, parts.path, safe_query, parts.fragment)
    )


def _is_sensitive(name: str) -> bool:
    normalized = name.lower().replace("-", "_")
    return normalized in SENSITIVE_NAMES or any(
        token in normalized for token in ("secret", "password", "token", "api_key")
    )
