import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.api.middleware import (
    PrivatePathNoStoreMiddleware,
    RequestBodyLimitMiddleware,
    _declared_content_length,
)


def _bounded_app(*, max_bytes: int = 5, route_max_bytes=None):
    inner = FastAPI()
    calls = {"count": 0}

    @inner.post("/api/v1/body")
    async def read_body(request: Request) -> dict[str, int]:
        calls["count"] += 1
        return {"bytes": len(await request.body())}

    bounded = RequestBodyLimitMiddleware(
        inner,
        max_bytes=max_bytes,
        route_max_bytes=route_max_bytes,
    )
    return PrivatePathNoStoreMiddleware(bounded, path_prefix="/api/v1"), calls


def test_declared_oversize_is_rejected_before_route_dispatch() -> None:
    app, calls = _bounded_app()

    response = TestClient(app).post(
        "/api/v1/body",
        content=b"x",
        headers={"content-length": "6"},
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "File too large or request body exceeds the local processing limit."
    }
    assert response.headers["connection"] == "close"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert calls["count"] == 0


def test_streamed_oversize_without_content_length_stops_during_receive() -> None:
    app, calls = _bounded_app()

    response = TestClient(app).post(
        "/api/v1/body",
        content=(chunk for chunk in (b"abc", b"def")),
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "File too large or request body exceeds the local processing limit."
    }
    assert response.headers["connection"] == "close"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert calls["count"] == 1


def test_exact_streamed_body_reaches_the_route() -> None:
    app, calls = _bounded_app()

    response = TestClient(app).post(
        "/api/v1/body",
        content=(chunk for chunk in (b"ab", b"cde")),
    )

    assert response.status_code == 200
    assert response.json() == {"bytes": 5}
    assert calls["count"] == 1


def test_malformed_content_length_fails_closed() -> None:
    app, calls = _bounded_app()

    response = TestClient(app).post(
        "/api/v1/body",
        content=b"x",
        headers={"content-length": "+1"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid Content-Length header"}
    assert response.headers["connection"] == "close"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert calls["count"] == 0


@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"1"), (b"content-length", b"1")],
        [(b"content-length", b"1"), (b"content-length", b"2")],
        [(b"content-length", b"1"), (b"transfer-encoding", b"chunked")],
    ],
)
def test_ambiguous_request_framing_fails_closed(
    headers: list[tuple[bytes, bytes]],
) -> None:
    with pytest.raises(ValueError):
        _declared_content_length(headers)


def test_exact_route_override_does_not_weaken_other_paths() -> None:
    app, calls = _bounded_app(route_max_bytes={("POST", "/api/v1/body"): 8})
    client = TestClient(app)

    allowed = client.post("/api/v1/body", content=b"12345678")
    unrelated = client.post("/api/v1/body/", content=b"123456")

    assert allowed.status_code == 200
    assert allowed.json() == {"bytes": 8}
    assert unrelated.status_code == 413
    assert calls["count"] == 1
