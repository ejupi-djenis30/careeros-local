"""Exercise real HTTPX/httpcore transport boundaries without external traffic."""

import socket

import httpx
import pytest

from backend.providers.configuration.client import DeclarativeJobProvider
from backend.providers.configuration.network_policy import (
    UnsafeProviderDestination,
    resolve_public_destination,
    validate_destination_literal,
)
from backend.providers.jobs.exceptions import ProviderError
from backend.providers.jobs.models import JobSearchRequest
from tests.backend.providers.configuration.helpers import json_provider_payload


@pytest.mark.asyncio
async def test_transport_connects_to_validated_ip_and_preserves_tls_hostname(monkeypatch):
    from httpcore._backends.anyio import AnyIOBackend

    resolutions = []
    connections = []
    tls_names = []
    writes = []

    def rebinding_dns(host, *_args, **_kwargs):
        resolutions.append(host)
        address = "93.184.216.34" if len(resolutions) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    class Stream:
        async def start_tls(self, ssl_context, server_hostname, timeout=None):
            assert ssl_context.check_hostname is True
            tls_names.append(server_hostname)
            return self

        async def write(self, buffer, timeout=None):
            writes.append(buffer)

        async def read(self, max_bytes, timeout=None):
            body = b'{"data":{"total":0,"jobs":[]}}'
            return (
                b"HTTP/1.1 200 OK\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )

        async def aclose(self):
            pass

        def get_extra_info(self, info):
            return None

    async def connect(_self, host, port, **_kwargs):
        connections.append((host, port))
        return Stream()

    monkeypatch.setattr(socket, "getaddrinfo", rebinding_dns)
    monkeypatch.setattr(AnyIOBackend, "connect_tcp", connect)
    provider = DeclarativeJobProvider(json_provider_payload())
    try:
        result = await provider.search(JobSearchRequest())
    finally:
        await provider.close()

    assert result.items == []
    assert resolutions == ["jobs.example.com"]
    assert connections == [("93.184.216.34", 443)]
    assert tls_names == ["jobs.example.com"]
    assert b"Host: jobs.example.com\r\n" in b"".join(writes)


@pytest.mark.asyncio
async def test_retry_revalidates_dns_before_another_connection(monkeypatch):
    resolutions = []
    requests = []

    def rebinding_dns(host, *_args, **_kwargs):
        resolutions.append(host)
        address = "93.184.216.34" if len(resolutions) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    async def no_delay(_seconds):
        return None

    def handler(request):
        requests.append(request)
        raise httpx.ConnectError("synthetic failure", request=request)

    monkeypatch.setattr(socket, "getaddrinfo", rebinding_dns)
    monkeypatch.setattr("backend.providers.configuration.transport.asyncio.sleep", no_delay)
    raw = json_provider_payload().model_dump()
    raw["request"]["retries"] = 1
    provider = DeclarativeJobProvider(type(json_provider_payload()).model_validate(raw))
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(UnsafeProviderDestination):
            await provider.search(JobSearchRequest())
    finally:
        await provider.close()
    assert len(resolutions) == 2
    assert len(requests) == 1
    assert requests[0].url.host == "93.184.216.34"


@pytest.mark.parametrize(
    "destination", ["https://224.0.0.1", "https://[ff0e::1]", "https://[::ffff:127.0.0.1]"]
)
def test_nonpublic_unicast_destinations_are_rejected(destination):
    with pytest.raises(UnsafeProviderDestination):
        validate_destination_literal(destination)


@pytest.mark.asyncio
async def test_dns_resolution_failure_is_explicit(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise OSError("synthetic DNS failure")

    monkeypatch.setattr(socket, "getaddrinfo", unavailable)
    with pytest.raises(UnsafeProviderDestination, match="resolved safely"):
        await resolve_public_destination("https://jobs.example.com")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["redirect", "oversized", "compressed", "chunked"])
async def test_real_http_client_rejects_unsafe_response_before_parsing(monkeypatch, kind):
    async def resolved(_base_url):
        return ("93.184.216.34",)

    calls = []

    class ChunkedBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 60_000
            yield b"x" * 60_000

    def handler(request):
        calls.append(request)
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "https://127.0.0.1/private"})
        if kind == "compressed":
            return httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=b"")
        if kind == "chunked":
            return httpx.Response(200, stream=ChunkedBody())
        return httpx.Response(200, content=b"x" * 100_001)

    monkeypatch.setattr(
        "backend.providers.configuration.transport.resolve_public_destination", resolved
    )
    original = httpx.AsyncClient
    monkeypatch.setattr(
        "backend.providers.configuration.transport.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    provider = DeclarativeJobProvider(json_provider_payload())
    try:
        with pytest.raises(ProviderError):
            await provider.search(JobSearchRequest())
    finally:
        await provider.close()
    assert len(calls) == 1
    assert calls[0].headers["Host"] == "jobs.example.com"
