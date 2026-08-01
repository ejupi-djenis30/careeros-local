from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.middleware import CanonicalTrustedHostMiddleware


def _client() -> TestClient:
    inner = FastAPI()

    @inner.get("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    app = CanonicalTrustedHostMiddleware(
        inner,
        allowed_hosts=["localhost", "127.0.0.1", "::1"],
    )
    return TestClient(app)


def test_canonical_host_middleware_accepts_dns_ipv4_and_bracketed_ipv6_with_ports():
    client = _client()

    for authority in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000"):
        response = client.get("/probe", headers={"Host": authority})
        assert response.status_code == 200


def test_canonical_host_middleware_rejects_untrusted_or_ambiguous_authorities():
    client = _client()

    for authority in (
        "localhost.evil:8000",
        "user@localhost:8000",
        "localhost/path",
        "localhost:0",
        "[::2]:8000",
        "::1",
    ):
        response = client.get("/probe", headers={"Host": authority})
        assert response.status_code == 400
