"""Network containment for user-declared provider destinations."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeProviderDestination(ValueError):
    """The declaration could expand access to a local or non-public service."""


def _public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return address.is_global


def validate_destination_literal(base_url: str) -> str:
    parsed = urlsplit(base_url)
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
    ):
        raise UnsafeProviderDestination("Provider destination must be a public HTTPS origin")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return hostname
    if not address.is_global:
        raise UnsafeProviderDestination("Provider destination must be publicly routable")
    return hostname


async def resolve_public_destination(base_url: str) -> tuple[str, ...]:
    """Resolve immediately before a request and reject every non-public answer."""

    hostname = validate_destination_literal(base_url)
    try:
        rows = await asyncio.wait_for(
            asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                443,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            ),
            timeout=5,
        )
    except (TimeoutError, OSError) as exc:
        raise UnsafeProviderDestination(
            "Provider destination could not be resolved safely"
        ) from exc
    addresses = tuple(sorted({str(row[4][0]) for row in rows}))
    if not addresses or len(addresses) > 16 or any(not _public_address(item) for item in addresses):
        raise UnsafeProviderDestination("Provider destination resolved outside the public network")
    return addresses
