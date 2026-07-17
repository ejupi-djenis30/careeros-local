import ipaddress
from typing import Iterable, Optional
from urllib.parse import urlsplit, urlunsplit


class LocalInferenceEndpointError(ValueError):
    """Raised when an inference endpoint crosses the local privacy boundary."""


DEFAULT_LOCAL_INFERENCE_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "ollama",
    "host.docker.internal",
}


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_local_inference_url(
    url: str,
    *,
    allowed_hosts: Optional[Iterable[str]] = None,
) -> str:
    """Validate and normalize an Ollama base URL without resolving DNS."""
    parsed = urlsplit((url or "").strip())
    if parsed.scheme != "http":
        raise LocalInferenceEndpointError("Local inference must use an http endpoint")
    if not parsed.hostname:
        raise LocalInferenceEndpointError("Local inference endpoint requires a host")
    if parsed.username or parsed.password:
        raise LocalInferenceEndpointError("Credentials are forbidden in inference URLs")
    if parsed.query or parsed.fragment:
        raise LocalInferenceEndpointError("Query strings and fragments are forbidden")
    if parsed.path not in {"", "/"}:
        raise LocalInferenceEndpointError("Use the Ollama origin without an API path")

    host = parsed.hostname.lower().strip("[]")
    allowlist = {
        item.lower().strip("[]") for item in (allowed_hosts or DEFAULT_LOCAL_INFERENCE_HOSTS)
    }
    if host not in allowlist and not _is_loopback(host):
        raise LocalInferenceEndpointError(
            f"Inference host '{host}' is not in the explicit local allowlist"
        )

    if ":" in host:
        authority = f"[{host}]"
    else:
        authority = host
    if parsed.port is not None:
        authority = f"{authority}:{parsed.port}"
    return urlunsplit(("http", authority, "", "", ""))
