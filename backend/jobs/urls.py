import re
from posixpath import normpath
from urllib.parse import urlsplit, urlunsplit


class UnsafeJobUrlError(ValueError):
    pass


def normalize_job_url(value: str | None, *, required: bool = True) -> str | None:
    if value is None or not str(value).strip():
        if required:
            raise UnsafeJobUrlError("A job URL is required")
        return None
    normalized = str(value).strip()
    if len(normalized) > 2048:
        raise UnsafeJobUrlError("Job URLs cannot exceed 2048 characters")
    if "\\" in normalized or re.search(r"[\x00-\x20\x7f]", normalized):
        raise UnsafeJobUrlError("Job URL contains unsafe characters")
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeJobUrlError("Job URLs must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeJobUrlError("Job URLs cannot contain credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeJobUrlError("Job URL contains an invalid port") from exc
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UnsafeJobUrlError("Job URL contains an invalid hostname") from exc
    if ":" in hostname:
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port is not None else hostname
    raw_path = parsed.path or "/"
    path = normpath(raw_path)
    if raw_path.startswith("/") and not path.startswith("/"):
        path = f"/{path}"
    if raw_path.endswith("/") and not path.endswith("/"):
        path = f"{path}/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))
