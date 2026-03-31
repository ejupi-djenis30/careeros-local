import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.providers.llm.g4f_provider import G4FProvider


def _make_response(content: str, reasoning: str | None = None):
    message = SimpleNamespace(content=content, reasoning=reasoning)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _make_chunk(content: str):
    delta = SimpleNamespace(content=content)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice])


async def _async_iter(items):
    for item in items:
        yield item


def _install_fake_g4f(monkeypatch):
    class HuggingChat:
        pass

    class DeepInfra:
        pass

    class FakeRetryProvider:
        def __init__(self, providers, shuffle=True):
            self.providers = providers
            self.shuffle = shuffle

    class FakeClient:
        instances = []

        def __init__(self, provider=None, **kwargs):
            self.provider = provider
            self.kwargs = kwargs
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=MagicMock(),
                    stream=MagicMock(),
                )
            )
            type(self).instances.append(self)

    class FakeAsyncClient:
        instances = []

        def __init__(self, provider=None, **kwargs):
            self.provider = provider
            self.kwargs = kwargs
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=AsyncMock(),
                    stream=MagicMock(),
                )
            )
            type(self).instances.append(self)

    fake_provider_module = SimpleNamespace(
        HuggingChat=HuggingChat,
        DeepInfra=DeepInfra,
        RetryProvider=FakeRetryProvider,
    )

    fake_client_factory = SimpleNamespace(create_provider=MagicMock())
    fake_client_module = types.ModuleType("g4f.client")
    fake_client_module.Client = FakeClient
    fake_client_module.AsyncClient = FakeAsyncClient
    fake_client_module.ClientFactory = fake_client_factory

    fake_cookies_module = types.ModuleType("g4f.cookies")
    fake_cookies_module.set_cookies_dir = MagicMock()
    fake_cookies_module.read_cookie_files = MagicMock()

    fake_g4f_module = types.ModuleType("g4f")
    fake_g4f_module.Provider = fake_provider_module

    monkeypatch.setitem(sys.modules, "g4f", fake_g4f_module)
    monkeypatch.setitem(sys.modules, "g4f.client", fake_client_module)
    monkeypatch.setitem(sys.modules, "g4f.cookies", fake_cookies_module)

    FakeClient.instances.clear()
    FakeAsyncClient.instances.clear()

    return SimpleNamespace(
        HuggingChat=HuggingChat,
        DeepInfra=DeepInfra,
        FakeRetryProvider=FakeRetryProvider,
        FakeClient=FakeClient,
        FakeAsyncClient=FakeAsyncClient,
        client_factory=fake_client_factory,
        cookies=fake_cookies_module,
    )


def test_g4f_provider_initialization_uses_retry_provider_and_proxy(monkeypatch, tmp_path):
    fake = _install_fake_g4f(monkeypatch)

    provider = G4FProvider(
        model="",
        providers_list=["HuggingChat", "DeepInfra"],
        proxies="http://localhost:8080",
        shuffle_providers=False,
        cookies_dir=str(tmp_path),
    )

    assert provider.model_id == "g4f[HuggingChat,DeepInfra]/auto"
    assert isinstance(provider._provider, fake.FakeRetryProvider)
    assert provider._provider.providers == [fake.HuggingChat, fake.DeepInfra]
    assert provider._provider.shuffle is False
    assert fake.FakeClient.instances[0].kwargs["proxies"] == "http://localhost:8080"
    fake.cookies.set_cookies_dir.assert_called_once_with(str(tmp_path))
    fake.cookies.read_cookie_files.assert_called_once_with(str(tmp_path))


def test_g4f_provider_no_providers_uses_auto_selection(monkeypatch, tmp_path):
    fake = _install_fake_g4f(monkeypatch)

    provider = G4FProvider(model="", providers_list=[], cookies_dir=str(tmp_path))

    assert provider.model_id == "g4f/auto"
    assert provider._provider is None
    assert fake.FakeClient.instances[0].provider is None


def test_g4f_provider_generate_text(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(
        model="gpt-4o-mini", providers_list=["HuggingChat"], cookies_dir=str(tmp_path)
    )
    provider.client.chat.completions.create.return_value = _make_response("Mocked G4F Response")

    result = provider.generate_text("System", "User")

    assert result == "Mocked G4F Response"


def test_g4f_provider_generate_json_parses_dirty_output(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(model="", providers_list=["HuggingChat"], cookies_dir=str(tmp_path))
    provider.client.chat.completions.create.return_value = _make_response(
        'Reasoning first\n```json\n{"hello": "world"}\n```'
    )

    result = provider.generate_json("System", "User")

    assert result == {"hello": "world"}


@pytest.mark.asyncio
async def test_g4f_provider_generate_text_async(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(model="", providers_list=["HuggingChat"], cookies_dir=str(tmp_path))
    provider.async_client.chat.completions.create.return_value = _make_response(
        "Async G4F Response"
    )

    result = await provider.generate_text_async("System", "User")

    assert result == "Async G4F Response"


@pytest.mark.asyncio
async def test_g4f_provider_generate_text_stream_async(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(model="", providers_list=["HuggingChat"], cookies_dir=str(tmp_path))
    provider.async_client.chat.completions.stream.return_value = _async_iter(
        [_make_chunk("Hel"), _make_chunk("lo")]
    )

    tokens = []
    async for token in provider.generate_text_stream_async("System", "User"):
        tokens.append(token)

    assert tokens == ["Hel", "lo"]
