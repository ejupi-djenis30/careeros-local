import pytest


@pytest.fixture
def bridge_client(client):
    """The production bridge requires a numeric loopback peer and Host."""
    client._transport.client = ("127.0.0.1", 50000)
    client.headers["Host"] = "127.0.0.1"
    return client
