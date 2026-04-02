import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.providers.llm.g4f_provider import G4FInitializationError, G4FProvider


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
        working = True
        needs_auth = True
        supports_stream = True
        default_model = "openai/gpt-oss-120b"

    class DeepInfra:
        working = True
        needs_auth = False
        supports_stream = True
        default_model = "MiniMaxAI/MiniMax-M2.5"

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
    assert fake.FakeClient.instances[0].kwargs["proxy"] == "http://localhost:8080"
    fake.cookies.set_cookies_dir.assert_called_once_with(str(tmp_path))
    fake.cookies.read_cookie_files.assert_called_once_with(str(tmp_path))


def test_g4f_provider_no_providers_uses_auto_discovery(monkeypatch, tmp_path):
    fake = _install_fake_g4f(monkeypatch)

    provider = G4FProvider(model="", providers_list=[], cookies_dir=str(tmp_path))

    assert provider.model_id == "g4f[DeepInfra]/auto"
    assert provider.provider_names == ["DeepInfra"]
    assert provider._provider is fake.DeepInfra
    assert fake.FakeClient.instances[0].provider is fake.DeepInfra


def test_g4f_provider_no_providers_raises_when_internal_fallback_disabled(monkeypatch, tmp_path):
    fake = _install_fake_g4f(monkeypatch)
    fake.DeepInfra.working = False

    with pytest.raises(
        G4FInitializationError,
        match="No stable unauthenticated g4f providers were auto-discovered",
    ):
        G4FProvider(model="", providers_list=[], cookies_dir=str(tmp_path))


def test_g4f_provider_no_providers_can_use_internal_selection(monkeypatch, tmp_path):
    fake = _install_fake_g4f(monkeypatch)
    fake.DeepInfra.working = False

    provider = G4FProvider(
        model="",
        providers_list=[],
        cookies_dir=str(tmp_path),
        allow_internal_provider_fallback=True,
    )

    assert provider.provider_names == []
    assert provider._provider is None


def test_g4f_provider_raises_clear_error_for_cookie_dir_permission_failure(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)

    def _raise_permission_error(*args, **kwargs):
        raise PermissionError("blocked")

    monkeypatch.setattr(
        "backend.providers.llm.g4f_provider.Path.mkdir",
        _raise_permission_error,
    )

    with pytest.raises(G4FInitializationError, match="Unable to prepare g4f cookie directory"):
        G4FProvider(
            model="",
            providers_list=["DeepInfra"],
            cookies_dir=str(tmp_path / "blocked"),
        )


def test_g4f_provider_explicit_provider_resolution_failure_raises(monkeypatch, tmp_path):
    fake = _install_fake_g4f(monkeypatch)
    fake.client_factory.create_provider.side_effect = RuntimeError("provider bootstrap failed")

    with pytest.raises(
        G4FInitializationError,
        match="None of the configured g4f providers could be initialized",
    ):
        G4FProvider(model="", providers_list=["MissingProvider"], cookies_dir=str(tmp_path))


def test_g4f_provider_generate_text(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(
        model="gpt-4o-mini", providers_list=["HuggingChat"], cookies_dir=str(tmp_path)
    )
    provider.client.chat.completions.create.return_value = _make_response("Mocked G4F Response")

    result = provider.generate_text("System", "User")

    assert result == "Mocked G4F Response"
    assert provider.client.chat.completions.create.call_args.kwargs["model"] == "gpt-4o-mini"


def test_g4f_provider_generate_text_omits_empty_model_and_passes_proxy(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(
        model="",
        providers_list=["DeepInfra"],
        proxies="http://localhost:8080",
        cookies_dir=str(tmp_path),
    )
    provider.client.chat.completions.create.return_value = _make_response("Mocked G4F Response")

    result = provider.generate_text("System", "User")

    assert result == "Mocked G4F Response"
    params = provider.client.chat.completions.create.call_args.kwargs
    assert "model" not in params
    assert params["proxy"] == "http://localhost:8080"


def test_g4f_provider_generate_json_parses_dirty_output(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(model="", providers_list=["HuggingChat"], cookies_dir=str(tmp_path))
    provider.client.chat.completions.create.return_value = _make_response(
        'Reasoning first\n```json\n{"hello": "world"}\n```'
    )

    result = provider.generate_json("System", "User")

    assert result == {"hello": "world"}


def test_g4f_provider_generate_json_falls_back_without_response_format(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(model="", providers_list=["DeepInfra"], cookies_dir=str(tmp_path))
    provider.client.chat.completions.create.side_effect = [
        RuntimeError("response_format unsupported"),
        _make_response('{"hello": "world"}'),
    ]

    result = provider.generate_json("System", "User")

    assert result == {"hello": "world"}
    first_call, second_call = provider.client.chat.completions.create.call_args_list
    assert first_call.kwargs["response_format"] == {"type": "json_object"}
    assert "Respond with valid JSON." in first_call.kwargs["messages"][0]["content"]
    assert "response_format" not in second_call.kwargs


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


@pytest.mark.asyncio
async def test_g4f_provider_generate_text_stream_async_falls_back_to_non_streaming(
    monkeypatch, tmp_path
):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(model="", providers_list=["DeepInfra"], cookies_dir=str(tmp_path))
    provider.async_client.chat.completions.stream.side_effect = RuntimeError("stream failed")
    provider.async_client.chat.completions.create.return_value = _make_response("Fallback response")

    tokens = []
    async for token in provider.generate_text_stream_async("System", "User"):
        tokens.append(token)

    assert tokens == ["Fallback response"]


@pytest.mark.asyncio
async def test_g4f_provider_generate_text_async_with_timeout_respects_budget_override(
    monkeypatch, tmp_path
):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(
        model="",
        providers_list=["DeepInfra"],
        cookies_dir=str(tmp_path),
        max_request_attempts=2,
        request_timeout_cap_seconds=3.0,
        timeout_buffer_seconds=0.5,
    )
    provider.async_client.chat.completions.create.return_value = _make_response(
        "Recovered response"
    )

    timeouts = []
    wait_for_calls = 0

    async def _capture_wait_for(coro, timeout):
        nonlocal wait_for_calls
        timeouts.append(timeout)
        wait_for_calls += 1
        if wait_for_calls == 1:
            coro.close()
            raise asyncio.TimeoutError()
        return await coro

    sleep_mock = AsyncMock()
    monkeypatch.setattr("backend.providers.llm.g4f_provider.asyncio.wait_for", _capture_wait_for)
    monkeypatch.setattr("backend.providers.llm.g4f_provider.asyncio.sleep", sleep_mock)

    result = await provider.generate_text_async_with_timeout(
        "System",
        "User",
        step="plan",
        timeout_override=2.5,
    )

    assert result == "Recovered response"
    assert len(timeouts) == 2
    assert timeouts[0] == pytest.approx(2.0, abs=0.05)
    assert all(0 < timeout <= 2.0 + 0.05 for timeout in timeouts)
    assert provider.async_client.chat.completions.create.call_count == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_g4f_provider_generate_text_async_retries_transient_failures(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(model="", providers_list=["DeepInfra"], cookies_dir=str(tmp_path))
    provider.async_client.chat.completions.create.side_effect = [
        RuntimeError("temporary connection reset"),
        _make_response("Recovered response"),
    ]

    sleep_mock = AsyncMock()
    monkeypatch.setattr("backend.providers.llm.g4f_provider.asyncio.sleep", sleep_mock)

    result = await provider.generate_text_async("System", "User")

    assert result == "Recovered response"
    assert provider.async_client.chat.completions.create.call_count == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_g4f_provider_generate_text_async_does_not_retry_nonretriable_model_error(
    monkeypatch, tmp_path
):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(
        model="gpt-4o-mini",
        providers_list=["DeepInfra"],
        cookies_dir=str(tmp_path),
        max_request_attempts=3,
    )
    provider.async_client.chat.completions.create.side_effect = RuntimeError("model not found")

    sleep_mock = AsyncMock()
    monkeypatch.setattr("backend.providers.llm.g4f_provider.asyncio.sleep", sleep_mock)

    with pytest.raises(RuntimeError, match="model not found"):
        await provider.generate_text_async("System", "User")

    assert provider.async_client.chat.completions.create.call_count == 1
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_msg",
    [
        "Response 401: {'detail': 'User is not authorized to access this resource'}",
        "HTTP 403 Forbidden",
        "unauthorized",
        "not authorized",
    ],
)
async def test_g4f_provider_does_not_retry_auth_failures(error_msg, monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(
        model="",
        providers_list=["DeepInfra"],
        cookies_dir=str(tmp_path),
        max_request_attempts=5,
    )
    provider.async_client.chat.completions.create.side_effect = RuntimeError(error_msg)

    sleep_mock = AsyncMock()
    monkeypatch.setattr("backend.providers.llm.g4f_provider.asyncio.sleep", sleep_mock)

    with pytest.raises(RuntimeError):
        await provider.generate_text_async("System", "User")

    assert provider.async_client.chat.completions.create.call_count == 1
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_msg",
    [
        "Request limit (100 per hour) exceeded for new tier. Made: 100 requests.",
        "Rate limit exceeded: too many requests per hour",
        "429: Too Many Requests",
        "RetryProvider failed:\nGroq: Request limit (100 per hour) exceeded",
    ],
)
async def test_g4f_provider_waits_rate_limit_wait_seconds_on_rate_limit(
    error_msg, monkeypatch, tmp_path
):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(
        model="",
        providers_list=["DeepInfra"],
        cookies_dir=str(tmp_path),
        max_request_attempts=3,
        rate_limit_wait_seconds=7200.0,
    )
    # First call rate-limited, second succeeds
    success_response = MagicMock()
    success_response.choices = [MagicMock()]
    success_response.choices[0].message.content = "ok"
    provider.async_client.chat.completions.create.side_effect = [
        RuntimeError(error_msg),
        success_response,
    ]

    sleep_mock = AsyncMock()
    monkeypatch.setattr("backend.providers.llm.g4f_provider.asyncio.sleep", sleep_mock)

    result = await provider.generate_text_async("System", "User")

    assert result == "ok"
    assert provider.async_client.chat.completions.create.call_count == 2
    # Must have slept the full rate-limit wait, not a short backoff
    sleep_mock.assert_awaited_once_with(7200.0)


@pytest.mark.asyncio
async def test_g4f_provider_rate_limit_backoff_honors_timeout_budget(monkeypatch, tmp_path):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(
        model="",
        providers_list=["DeepInfra"],
        cookies_dir=str(tmp_path),
        max_request_attempts=3,
        request_timeout_cap_seconds=20.0,
        timeout_buffer_seconds=0.5,
        rate_limit_wait_seconds=7200.0,
    )
    provider.async_client.chat.completions.create.side_effect = RuntimeError(
        "429: Too Many Requests"
    )

    sleep_mock = AsyncMock()
    monkeypatch.setattr("backend.providers.llm.g4f_provider.asyncio.sleep", sleep_mock)

    with pytest.raises(TimeoutError, match="retry backoff"):
        await provider.generate_text_async_with_timeout(
            "System",
            "User",
            step="match",
            timeout_override=5.0,
        )

    assert provider.async_client.chat.completions.create.call_count == 1
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_g4f_provider_json_timeout_budget_is_shared_with_response_format_fallback(
    monkeypatch, tmp_path
):
    _install_fake_g4f(monkeypatch)
    provider = G4FProvider(model="", providers_list=["DeepInfra"], cookies_dir=str(tmp_path))
    provider._create_completion_async = AsyncMock(
        side_effect=[
            RuntimeError("response_format unsupported"),
            _make_response('{"hello": "world"}'),
        ]
    )

    result = await provider.generate_json_async_with_timeout(
        "System",
        "User",
        step="normalize",
        timeout_override=12.0,
    )

    assert result == {"hello": "world"}
    assert provider._create_completion_async.await_count == 2
    first_call, second_call = provider._create_completion_async.await_args_list
    assert first_call.kwargs["call_deadline"] is not None
    assert second_call.kwargs["call_deadline"] == first_call.kwargs["call_deadline"]
