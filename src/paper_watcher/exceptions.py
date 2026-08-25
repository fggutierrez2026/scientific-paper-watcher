class PaperWatcherError(Exception):
    """Base exception for Scientific Paper Watcher."""


class APIError(PaperWatcherError):
    """Base exception for external API errors."""


class NetworkError(APIError):
    """Raised when a network connection fails."""


class RequestTimeoutError(NetworkError):
    """Raised when an API request exceeds the configured timeout."""


class RateLimitError(APIError):
    """Raised when an API rejects requests because of rate limiting."""

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)

        self.retry_after = retry_after


class ServiceUnavailableError(APIError):
    """Raised when an external service is temporarily unavailable."""


class InvalidResponseError(APIError):
    """Raised when an API returns data that cannot be parsed."""