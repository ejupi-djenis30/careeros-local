import re

from backend.core.diagnostics import FailureDiagnostic

_APPROVED_PROVIDER_MESSAGES = {
    "Job details request failed",
    "Max retries exceeded",
    "Provider request failed",
    "Search failed",
    "Session not initialized",
}
_HTTP_ERROR = re.compile(r"^HTTP [1-5][0-9]{2} Error$")


class ProviderError(Exception):
    """Base exception for provider errors."""

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        diagnostic: FailureDiagnostic | None = None,
    ):
        self.provider = provider
        self.message = (
            message
            if message in _APPROVED_PROVIDER_MESSAGES or _HTTP_ERROR.fullmatch(message)
            else "Provider request failed"
        )
        self.diagnostic = diagnostic
        super().__init__(f"[{provider}] {self.message}")


class ResponseParseError(ProviderError):
    """Raised when response parsing fails."""

    pass


class LocationNotFoundError(Exception):
    """Raised when a location cannot be resolved."""

    pass


def format_provider_error(e: Exception) -> str:
    """Return only an HTTP class when available; never expose exception text."""
    candidates: list[BaseException] = [e]
    cause = getattr(e, "__cause__", None)
    if isinstance(cause, BaseException):
        candidates.append(cause)
        last_attempt = getattr(cause, "last_attempt", None)
        if last_attempt is not None:
            try:
                attempted = last_attempt.exception()
            except Exception:
                attempted = None
            if isinstance(attempted, BaseException):
                candidates.append(attempted)

    for candidate in candidates:
        status = getattr(candidate, "status_code", None)
        response = getattr(candidate, "response", None)
        if status is None and response is not None:
            status = getattr(response, "status_code", None)
        if isinstance(status, int) and 100 <= status <= 599:
            return f"HTTP {status} Error"
    return "Provider request failed"
