from __future__ import annotations

import hmac
import ipaddress
import re
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse

ASGIApp = Callable[
    [dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]
]


class DesktopSessionMiddleware:
    """Require the unpersisted native-shell secret on desktop HTTP requests."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        token: str,
        exempt_path_prefix: str | None = None,
    ) -> None:
        if len(token) < 32:
            raise ValueError("Desktop session middleware requires a strong token")
        self.app = app
        self._token = token.encode("utf-8")
        self._exempt_path_prefix = exempt_path_prefix.rstrip("/") if exempt_path_prefix else None

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        bridge = self._exempt_path_prefix
        if bridge and path.startswith(bridge + "/"):

            async def private_send(message):
                if message.get("type") == "http.response.start":
                    message["headers"] = [
                        (k, v)
                        for k, v in message.get("headers", [])
                        if k.lower() not in (b"cache-control", b"pragma")
                    ]
                    message["headers"].extend(
                        [(b"cache-control", b"no-store, max-age=0"), (b"pragma", b"no-cache")]
                    )
                await send(message)

            suffix = path[len(bridge) :]
            uuid_pattern = (
                r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
            )
            permitted = (
                scope.get("method") == "GET"
                and (
                    suffix in ("/status", "/work-requests", "/resume-templates")
                    or re.fullmatch(rf"/work-requests/{uuid_pattern}/(?:context|result)", suffix)
                    is not None
                )
            ) or (
                scope.get("method") == "POST"
                and re.fullmatch(rf"/work-requests/{uuid_pattern}/result", suffix) is not None
            )
            headers = scope.get("headers", [])
            origins = [v for k, v in headers if k.lower() == b"origin"]
            try:
                loopback = ipaddress.ip_address(scope.get("client", ("", 0))[0]).is_loopback
            except ValueError:
                loopback = False
            if permitted and loopback and not origins:
                await self.app(scope, receive, private_send)
                return
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": {
                        "code": "scope_denied",
                        "message": "Bridge transport authorization failed",
                    }
                },
            )
            await response(scope, receive, private_send)
            return

        supplied_values = [
            value.strip()
            for name, value in scope.get("headers", [])
            if name.lower() == b"x-careeros-session"
        ]
        supplied = supplied_values[0] if len(supplied_values) == 1 else b""

        if not supplied or not hmac.compare_digest(supplied, self._token):
            response = JSONResponse(
                status_code=403,
                content={"detail": "Desktop session authorization failed"},
                headers={
                    "Cache-Control": "no-store, max-age=0",
                    "Pragma": "no-cache",
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
