import ipaddress
import re
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
_LOCAL_CONTAINER_ALIAS = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    re.IGNORECASE,
)


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_local_container_alias(host: str) -> bool:
    """Recognize a single-label container DNS alias, never a domain or IP address."""
    return "." not in host and bool(_LOCAL_CONTAINER_ALIAS.fullmatch(host))


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
    requested_allowlist = {
        item.strip().lower().strip("[]")
        for item in (DEFAULT_LOCAL_INFERENCE_HOSTS if allowed_hosts is None else allowed_hosts)
        if item.strip().strip("[]")
    }
    unsafe_requested = {
        item
        for item in requested_allowlist
        if item not in DEFAULT_LOCAL_INFERENCE_HOSTS
        and not _is_loopback(item)
        and not _is_local_container_alias(item)
    }
    if unsafe_requested:
        raise LocalInferenceEndpointError(
            "Inference allowlist contains a host outside the built-in local boundary"
        )
    explicit_container_alias = (
        allowed_hosts is not None
        and host in requested_allowlist
        and _is_local_container_alias(host)
    )
    if (
        host not in DEFAULT_LOCAL_INFERENCE_HOSTS
        and not _is_loopback(host)
        and not explicit_container_alias
    ):
        raise LocalInferenceEndpointError(
            f"Inference host '{host}' is outside the built-in local boundary"
        )
    if host not in requested_allowlist and not _is_loopback(host):
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
