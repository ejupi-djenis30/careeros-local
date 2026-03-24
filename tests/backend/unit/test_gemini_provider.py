import pytest
import json
from unittest.mock import MagicMock, patch
from backend.providers.llm.gemini import GeminiProvider

def test_gemini_config_thinking():
    with patch("google.genai.Client"):
        provider = GeminiProvider(api_key="key", model="m", thinking_level="LOW")
        provider.types = MagicMock()
        config = provider._get_config()
        provider.types.ThinkingConfig.assert_called_once_with(thinking_level="LOW")

def test_gemini_generate_text_success():
    with patch("google.genai.Client") as mock_client:
        mock_gen = mock_client.return_value.models.generate_content
        mock_gen.return_value.text = "Hello"
        
        provider = GeminiProvider(api_key="key", model="m")
        provider.types = MagicMock()
        text = provider.generate_text("sys", "user")
        assert text == "Hello"

def test_gemini_generate_json_failure():
    with patch("google.genai.Client") as mock_client:
        mock_gen = mock_client.return_value.models.generate_content
        mock_gen.side_effect = Exception("API Error")
        
        provider = GeminiProvider(api_key="key", model="m")
        provider.types = MagicMock()
        with pytest.raises(Exception):
            provider.generate_json("sys", "user")

@pytest.mark.asyncio
async def test_gemini_async_wrappers():
    with patch("google.genai.Client"):
        provider = GeminiProvider(api_key="key", model="m")
        with patch.object(provider, "generate_text", return_value="async text") as mock_gen:
            res = await provider.generate_text_async("sys", "user")
            assert res == "async text"
            mock_gen.assert_called_once()
