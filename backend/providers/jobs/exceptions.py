class ProviderError(Exception):
    """Base exception for provider errors."""
    def __init__(self, provider: str, message: str):
        self.provider = provider
        self.message = message
        super().__init__(f"[{provider}] {message}")

class ResponseParseError(ProviderError):
    """Raised when response parsing fails."""
    pass

class LocationNotFoundError(Exception):
    """Raised when a location cannot be resolved."""
    pass

def format_provider_error(e: Exception) -> str:
    """Format exceptions like tenacity RetryError into readable HTTP errors."""
    error_msg = str(e)
    cause = getattr(e, "__cause__", None)

    if cause is not None:
        if hasattr(cause, "last_attempt"):
            exc = cause.last_attempt.exception()
            if hasattr(exc, "response") and exc.response is not None:
                error_msg = f"HTTP {exc.response.status_code} Error"
            elif exc:
                error_msg = str(exc)
        else:
            if hasattr(cause, "response") and cause.response is not None:
                error_msg = f"HTTP {cause.response.status_code} Error"
            else:
                error_msg = str(cause)

    return error_msg
