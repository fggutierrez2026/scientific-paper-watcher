from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import requests

from paper_watcher.exceptions import APIError
from paper_watcher.http import (
    HttpClient,
    HttpPolicy,
    parse_retry_after,
    redact_mapping,
    redact_url,
)


def test_parse_retry_after_supports_seconds_and_http_date():
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)

    assert parse_retry_after("3.5", now=now) == 3.5
    assert parse_retry_after("Thu, 10 Sep 2026 12:00:08 GMT", now=now) == 8
    assert parse_retry_after("invalid", now=now) is None


def test_http_client_retries_rate_limit_without_losing_provider_options():
    limited = MagicMock(status_code=429, headers={"Retry-After": "0"})
    successful = MagicMock(status_code=200, headers={})
    successful.raise_for_status.return_value = None
    session = MagicMock(spec=requests.Session)
    session.request.side_effect = [limited, successful]
    client = HttpClient(HttpPolicy(timeout=7, max_retries=1), session=session)

    response = client.request(
        "GET",
        "https://example.test/search",
        provider="Example",
        params={"query": "protein", "api_key": "private"},
        headers={"X-Custom": "preserved"},
    )

    assert response is successful
    assert session.request.call_count == 2
    assert session.request.call_args.kwargs["timeout"] == 7
    assert session.request.call_args.kwargs["headers"] == {"X-Custom": "preserved"}


def test_redaction_covers_urls_and_diagnostic_mappings():
    url = "https://user:password@example.test/path?query=safe&api_key=secret"

    redacted_url = redact_url(url)
    redacted_values = redact_mapping(
        {"query": "safe", "Authorization": "Bearer private", "client_secret": "x"}
    )

    assert "password" not in redacted_url
    assert "secret" not in redacted_url
    assert "query=safe" in redacted_url
    assert redacted_values == {
        "query": "safe",
        "Authorization": "[REDACTED]",
        "client_secret": "[REDACTED]",
    }


def test_http_client_allows_provider_specific_statuses():
    not_found = MagicMock(status_code=404, headers={})
    session = MagicMock(spec=requests.Session)
    session.request.return_value = not_found
    client = HttpClient(HttpPolicy(timeout=7, max_retries=0), session=session)

    assert client.request(
        "GET",
        "https://example.test/work",
        provider="Example",
        allowed_statuses={404},
    ) is not_found
    not_found.raise_for_status.assert_not_called()


def test_http_error_does_not_expose_url_credentials():
    denied = MagicMock(status_code=401, headers={})
    denied.raise_for_status.side_effect = requests.exceptions.HTTPError("denied")
    session = MagicMock(spec=requests.Session)
    session.request.return_value = denied
    client = HttpClient(HttpPolicy(timeout=7, max_retries=0), session=session)

    with pytest.raises(APIError) as caught:
        client.request(
            "GET",
            "https://user:password@example.test/work?api_key=private",
            provider="Example",
        )

    message = str(caught.value)
    assert "password" not in message
    assert "private" not in message
    assert "[REDACTED]" in message
