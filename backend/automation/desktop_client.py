"""Bounded fixed-operation HTTP bridge; the grant never follows redirects."""

from __future__ import annotations

import json
import math
import re
import time
from threading import Lock
from typing import Any, cast

import anyio
import httpx
from anyio.from_thread import start_blocking_portal

from backend.desktop.connection_descriptor import DescriptorError, read_connection_descriptor

MAX_RESPONSE_BYTES = 262144
MAX_REQUEST_BYTES = 266240
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 30.0
_URL = re.compile(r"http://(127\.0\.0\.1|\[::1\]):([1-9][0-9]{0,4})/api/v1\Z")
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
_OPERATIONS = re.compile(
    rf"/agent-bridge/(?:status|work-requests|resume-templates|work-requests/{_UUID}/(?:context|result))\Z"
)
_SAFE_CODES = frozenset(
    {
        "grant_required",
        "grant_expired",
        "grant_revoked",
        "scope_denied",
        "work_not_found",
        "work_expired",
        "work_canceled",
        "stale_input",
        "invalid_result",
        "evidence_invalid",
        "result_conflict",
        "revision_conflict",
        "vault_unavailable",
        "desktop_unavailable",
        "invalid_grant",
        "expired_grant",
        "revoked_grant",
    }
)


class DesktopBridgeError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def validate_canonical_desktop_url(url_str: str) -> str:
    match = _URL.fullmatch(url_str) if isinstance(url_str, str) else None
    if match is None or int(match[2]) > 65535:
        raise DesktopBridgeError(
            "invalid_desktop_url", "Use a canonical numeric loopback HTTP URL ending in /api/v1"
        )
    return url_str


def _request_id(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(_UUID, value) is None:
        raise DesktopBridgeError("invalid_result", "Work request identity must be a canonical UUID")
    return value


class DesktopBridgeClient:
    def __init__(
        self,
        base_url: str | None,
        token: str,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
        connection_file: str | None = None,
    ) -> None:
        if bool(base_url) == bool(connection_file):
            raise DesktopBridgeError("invalid_desktop_url", "Choose one desktop connection mode")
        self.base_url = validate_canonical_desktop_url(base_url) if base_url else ""
        self.connection_file = connection_file
        self._connection_identity: tuple | None = None
        if not token or any(ord(c) < 33 or ord(c) > 126 for c in token) or len(token) > 512:
            raise DesktopBridgeError("grant_required", "A valid automation grant token is required")
        self.token = token
        if not math.isfinite(timeout_seconds):
            raise DesktopBridgeError("invalid_result", "Timeout must be finite")
        self.timeout = min(max(1.0, float(timeout_seconds)), MAX_TIMEOUT_SECONDS)
        self._transport = transport
        self._lock = Lock()
        self._closed = False
        self._portal_context = start_blocking_portal()
        self._portal = self._portal_context.__enter__()
        self._client = self._portal.call(self._new_client)

    async def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout, trust_env=False, follow_redirects=False, transport=self._transport
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._portal.call(self._client.aclose)
            finally:
                self._portal_context.__exit__(None, None, None)

    def __enter__(self) -> DesktopBridgeClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, json_data: Any = None
    ) -> Any:
        deadline = time.monotonic() + self.timeout
        if not self._lock.acquire(timeout=self.timeout):
            raise DesktopBridgeError("desktop_unavailable", "Desktop operation deadline exceeded")
        try:
            if self._closed:
                raise DesktopBridgeError("desktop_unavailable", "Desktop bridge is closed")
            return self._portal.call(
                self._request_with_deadline, method, path, params, json_data, deadline
            )
        finally:
            self._lock.release()

    async def _request_with_deadline(self, method, path, params, json_data, deadline):
        try:
            with anyio.fail_after(max(0, deadline - time.monotonic())):
                identity = None
                if self.connection_file:
                    try:
                        current = await anyio.to_thread.run_sync(
                            read_connection_descriptor,
                            self.connection_file,
                            abandon_on_cancel=True,
                        )
                    except DescriptorError:
                        raise DesktopBridgeError(
                            "desktop_unavailable",
                            "Open CareerOS to renew its private connection metadata",
                        ) from None
                    self.base_url = validate_canonical_desktop_url(current.api_base_url)
                    identity = (
                        current.instance_id,
                        current.pid,
                        current.process_start,
                        self.base_url,
                    )
                if identity is not None and identity != self._connection_identity:
                    await self._client.aclose()
                    self._client = await self._new_client()
                    self._connection_identity = identity
                return await self._request_async(method, path, params=params, json_data=json_data)
        except TimeoutError:
            raise DesktopBridgeError(
                "desktop_unavailable", "Desktop operation deadline exceeded"
            ) from None

    async def _request_async(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, json_data: Any = None
    ) -> Any:
        if not _OPERATIONS.fullmatch(path) or (
            method != "GET" and not (method == "POST" and path.endswith("/result"))
        ):
            raise DesktopBridgeError("invalid_result", "Unsupported bridge operation")
        try:
            outgoing = (
                None
                if json_data is None
                else json.dumps(
                    json_data, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                ).encode("utf-8")
            )
        except (ValueError, TypeError):
            raise DesktopBridgeError("invalid_result", "Proposal is not valid JSON") from None
        if outgoing is not None and len(outgoing) > MAX_REQUEST_BYTES:
            raise DesktopBridgeError("invalid_result", "Proposal exceeds the byte limit")
        try:
            async with self._client.stream(
                method,
                self.base_url + path,
                params=params,
                content=outgoing,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
                timeout=self.timeout,
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    raise DesktopBridgeError(
                        "bridge_error",
                        "Redirects are not permitted",
                        status_code=response.status_code,
                    )
                length = response.headers.get("content-length")
                if length is not None:
                    if not length.isascii() or not length.isdigit():
                        raise DesktopBridgeError("bridge_error", "Invalid response length")
                    if int(length) > MAX_RESPONSE_BYTES:
                        raise DesktopBridgeError(
                            "response_too_large", "Response exceeds the byte limit"
                        )
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(chunks) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise DesktopBridgeError(
                            "response_too_large", "Response exceeds the byte limit"
                        )
                    chunks.extend(chunk)
                try:
                    body = json.loads(chunks)
                except (ValueError, UnicodeError):
                    raise DesktopBridgeError(
                        "bridge_error", "Desktop response is not valid JSON"
                    ) from None
                if not response.is_success:
                    code = {
                        401: "grant_required",
                        403: "scope_denied",
                        404: "work_not_found",
                        409: "result_conflict",
                        422: "invalid_result",
                        503: "desktop_unavailable",
                    }.get(response.status_code, "bridge_error")
                    if isinstance(body, dict) and isinstance(body.get("detail"), dict):
                        candidate = body["detail"].get("code")
                        if isinstance(candidate, str) and candidate in _SAFE_CODES:
                            code = candidate
                    # Error bodies, URLs and exception strings are untrusted and can contain secrets.
                    raise DesktopBridgeError(
                        code,
                        "CareerOS could not complete this bridge operation",
                        status_code=response.status_code,
                    )
                return body
        except DesktopBridgeError:
            raise
        except (httpx.HTTPError, ValueError, OSError):
            raise DesktopBridgeError(
                "desktop_unavailable", "CareerOS desktop is unavailable"
            ) from None

    def get_agent_status(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", "/agent-bridge/status"))

    def list_work_requests(self, offset: int = 0, limit: int = 25) -> dict[str, Any]:
        if (
            isinstance(offset, bool)
            or isinstance(limit, bool)
            or offset < 0
            or not 1 <= limit <= 50
        ):
            raise DesktopBridgeError("invalid_result", "Invalid pagination")
        return cast(
            dict[str, Any],
            self._request(
                "GET", "/agent-bridge/work-requests", params={"offset": offset, "limit": limit}
            ),
        )

    def get_work_context(self, request_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", f"/agent-bridge/work-requests/{_request_id(request_id)}/context"),
        )

    def submit_work_result(self, request_id: str, submission: dict[str, Any]) -> dict[str, Any]:
        identity = _request_id(request_id)
        if submission.get("request_id") != identity:
            raise DesktopBridgeError(
                "invalid_result", "Submission identity does not match its request"
            )
        return cast(
            dict[str, Any],
            self._request(
                "POST", f"/agent-bridge/work-requests/{identity}/result", json_data=submission
            ),
        )

    def get_work_result(self, request_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", f"/agent-bridge/work-requests/{_request_id(request_id)}/result"),
        )

    def list_resume_templates(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/agent-bridge/resume-templates"))
