"""ASGI middleware shared by the CareerOS HTTP boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

ASGIApp = Callable[
    [dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]],
    Awaitable[None],
]
PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


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
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in {b"cache-control", b"pragma"}
                ]
                headers.extend(
                    (
                        (
                            b"cache-control",
                            PRIVATE_NO_STORE_HEADERS["Cache-Control"].encode("ascii"),
                        ),
                        (
                            b"pragma",
                            PRIVATE_NO_STORE_HEADERS["Pragma"].encode("ascii"),
                        ),
                    )
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_private)
