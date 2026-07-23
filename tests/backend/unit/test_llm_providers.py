from unittest.mock import MagicMock, patch

from backend.inference.ollama import OllamaProvider


def test_ollama_provider_uses_native_chat_contract():
    response = MagicMock()
    response.json.return_value = {"message": {"content": "Local response"}}
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response

    provider = OllamaProvider(endpoint="http://localhost:11434", model="qwen3:4b")
    with patch("backend.inference.ollama.httpx.Client", return_value=client):
        result = provider.generate_text("System", "User", max_tokens=64)

    assert result == "Local response"
    path, = client.post.call_args.args
    payload = client.post.call_args.kwargs["json"]
    assert path == "/api/chat"
    assert payload["model"] == "qwen3:4b"
    assert payload["think"] is False
    assert payload["options"]["num_predict"] == 64
    assert payload["options"]["num_ctx"] == 8192
    assert "api_key" not in payload


def test_ollama_provider_parses_structured_local_response():
    response = MagicMock()
    response.json.return_value = {"message": {"content": '{"ok": true}'}}
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response

    provider = OllamaProvider(endpoint="http://127.0.0.1:11434", model="qwen3:4b")
    with patch("backend.inference.ollama.httpx.Client", return_value=client):
        result = provider.generate_json("System", "User")

    assert result == {"ok": True}
    assert client.post.call_args.kwargs["json"]["format"] == "json"
