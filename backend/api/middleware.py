"""ASGI middleware shared by the CareerOS HTTP boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, PlainTextResponse

from backend.career.activity import VaultActivityGate

ASGIApp = Callable[
    [dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]],
    Awaitable[None],
]
PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}
PRIVATE_SECURITY_HEADERS = {
    **PRIVATE_NO_STORE_HEADERS,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), display-capture=(), payment=(), usb=()"
    ),
}


def _declared_content_length(headers: list[tuple[bytes, bytes]]) -> int | None:
    values = [value for name, value in headers if name.lower() == b"content-length"]
    transfer_encodings = [value for name, value in headers if name.lower() == b"transfer-encoding"]
    if values and transfer_encodings:
        raise ValueError("Ambiguous request framing")
    if not values:
        return None
    if len(values) != 1:
        raise ValueError("Duplicate Content-Length headers")
    try:
        decoded = values[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Invalid Content-Length header") from exc
    if not decoded or len(decoded) > 20 or not decoded.isdecimal():
        raise ValueError("Invalid Content-Length header")
    return int(decoded)


class RequestBodyLimitMiddleware:
    """Reject oversized bodies while ASGI is receiving them, before multipart parsing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        route_max_bytes: dict[tuple[str, str], int] | None = None,
    ) -> None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        self.app = app
        self._max_bytes = max_bytes
        self._route_max_bytes: dict[tuple[str, str], int] = {}
        for (method, path), route_limit in (route_max_bytes or {}).items():
            if (
                not method
                or not path.startswith("/")
                or isinstance(route_limit, bool)
                or not isinstance(route_limit, int)
                or route_limit <= 0
            ):
                raise ValueError("route_max_bytes must contain exact routes and positive limits")
            self._route_max_bytes[(method.upper(), path)] = route_limit

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        max_bytes = self._route_max_bytes.get(
            (str(scope.get("method", "GET")).upper(), str(scope.get("path", ""))),
            self._max_bytes,
        )
        try:
            declared = _declared_content_length(scope.get("headers", []))
        except ValueError:
            response = JSONResponse(
                {"detail": "Invalid Content-Length header"},
                status_code=400,
                headers={"Connection": "close"},
            )
            await response(scope, receive, send)
            return
        if declared is not None and declared > max_bytes:
            response = JSONResponse(
                {"detail": "File too large or request body exceeds the local processing limit."},
                status_code=413,
                headers={"Connection": "close"},
            )
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                if not isinstance(body, bytes):
                    raise StarletteHTTPException(
                        status_code=400,
                        detail="Invalid request body",
                    )
                received += len(body)
                if received > max_bytes:
                    raise StarletteHTTPException(
                        status_code=413,
                        detail="File too large or request body exceeds the local processing limit.",
                        headers={"Connection": "close"},
                    )
            return message

        await self.app(scope, limited_receive, send)


def is_private_path(path: str, *, path_prefix: str) -> bool:
    """Return whether ``path`` belongs to an exact private API subtree."""
    normalized_prefix = path_prefix.rstrip("/")
    return path == normalized_prefix or path.startswith(f"{normalized_prefix}/")


class PrivatePathNoStoreMiddleware:
    """Apply private-cache headers even when an inner middleware responds early."""

    def __init__(self, app: ASGIApp, *, path_prefix: str) -> None:
        self.app = app
        self._path_prefix = path_prefix.rstrip("/")

    async def __call__(self, scope, receive, send) -> None:
        path = scope.get("path", "")
        is_private = scope.get("type") == "http" and is_private_path(
            path,
            path_prefix=self._path_prefix,
        )
        if not is_private:
            await self.app(scope, receive, send)
            return

        async def send_private(message) -> None:
            if message.get("type") == "http.response.start":
                managed_names = {name.lower().encode("ascii") for name in PRIVATE_SECURITY_HEADERS}
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in managed_names
                ]
                headers.extend(
                    (name.lower().encode("ascii"), value.encode("ascii"))
                    for name, value in PRIVATE_SECURITY_HEADERS.items()
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_private)


class VaultActivityMiddleware:
    """Hold a reader permit for private requests outside maintenance writers."""

    _MAINTENANCE_REQUESTS = frozenset(
        {
            ("DELETE", "/career-profile"),
            ("POST", "/portability/restore"),
            ("DELETE", "/portability/erase"),
            ("POST", "/desktop/shutdown"),
        }
    )
    _PROBE_REQUESTS = frozenset(
        {
            ("GET", "/health"),
            ("GET", "/health/live"),
            ("GET", "/health/ready"),
        }
    )

    def __init__(self, app: ASGIApp, *, path_prefix: str, gate: VaultActivityGate) -> None:
        self.app = app
        self._path_prefix = path_prefix.rstrip("/")
        self._gate = gate

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not is_private_path(path, path_prefix=self._path_prefix):
            await self.app(scope, receive, send)
            return
        relative_path = path[len(self._path_prefix) :] or "/"
        request_key = (str(scope.get("method", "GET")).upper(), relative_path)
        if request_key in self._MAINTENANCE_REQUESTS or request_key in self._PROBE_REQUESTS:
            await self.app(scope, receive, send)
            return
        async with self._gate.reader():
            await self.app(scope, receive, send)


def _canonical_request_host(authority: str) -> str:
    if not authority or any(character.isspace() for character in authority):
        raise ValueError("Invalid Host header")
    parsed = urlsplit(f"//{authority}")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
    ):
        raise ValueError("Invalid Host header")
    port = parsed.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid Host header")
    hostname = parsed.hostname
    try:
        return ip_address(hostname).compressed.lower()
    except ValueError:
        return hostname.lower()


class CanonicalTrustedHostMiddleware:
    """Reject ambiguous Host authorities and compare one canonical host exactly."""

    def __init__(self, app: ASGIApp, *, allowed_hosts: list[str]) -> None:
        if not allowed_hosts:
            raise ValueError("allowed_hosts must not be empty")
        self.app = app
        self._allowed_hosts = frozenset(allowed_hosts)

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        host_headers = [
            value for name, value in scope.get("headers", []) if name.lower() == b"host"
        ]
        try:
            if len(host_headers) != 1:
                raise ValueError("Exactly one Host header is required")
            host = _canonical_request_host(host_headers[0].decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            response = PlainTextResponse("Invalid host header", status_code=400)
            await response(scope, receive, send)
            return
        if host not in self._allowed_hosts:
            response = PlainTextResponse("Invalid host header", status_code=400)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
