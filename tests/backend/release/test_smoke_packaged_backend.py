from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts import smoke_packaged_backend


def test_packaged_smoke_never_follows_a_credentialed_redirect() -> None:
    leaked_requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            if self.path == "/api/v1/redirect":
                self.send_response(302)
                self.send_header("Location", "/api/v1/leaked")
                self.end_headers()
                return
            leaked_requests.append(self.headers.get("X-CareerOS-Session", ""))
            self.send_response(200)
            self.end_headers()

        def log_message(self, _format: str, *_arguments: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(RuntimeError, match="HTTP 302"):
            smoke_packaged_backend._request(
                base_url,
                "/api/v1/redirect",
                session_token="do-not-forward",
                access_token="also-do-not-forward",
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert leaked_requests == []


@pytest.mark.parametrize("returncode", [None, 1, -9])
def test_packaged_smoke_rejects_nonzero_sidecar_exit(returncode: int | None) -> None:
    with pytest.raises(RuntimeError, match="did not terminate cleanly"):
        smoke_packaged_backend._require_clean_exit(returncode)


def test_packaged_smoke_accepts_a_clean_sidecar_exit() -> None:
    smoke_packaged_backend._require_clean_exit(0)
