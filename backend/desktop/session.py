from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse

ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]]


class DesktopSessionMiddleware:
    """Require the unpersisted native-shell secret on desktop HTTP requests."""

    def __init__(self, app: ASGIApp, *, token: str) -> None:
        if len(token) < 32:
            raise ValueError("Desktop session middleware requires a strong token")
        self.app = app
        self._token = token.encode("utf-8")

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        supplied = b""
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-careeros-session":
                supplied = value.strip()
                break

        if not supplied or not hmac.compare_digest(supplied, self._token):
            response = JSONResponse(
                status_code=403,
                content={"detail": "Desktop session authorization failed"},
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
