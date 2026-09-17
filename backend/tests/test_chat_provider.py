import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.config import settings
from app.llm import provider


@pytest.mark.parametrize("selection,deepseek,openai,expected,key", [
    ("auto", "ds", "oa", "deepseek", "ds"),
    ("auto", None, "oa", "openai", "oa"),
    ("auto", None, None, "openai", None),
    ("deepseek", None, "oa", "deepseek", None),
    ("openai", "ds", "oa", "openai", "oa"),
    ("openai", "ds", None, "openai", None),
])
def test_provider_selection(monkeypatch, selection, deepseek, openai, expected, key):
    monkeypatch.setattr(settings, "LLM_PROVIDER", selection)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", deepseek)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", openai)
    result = provider.get_chat_provider()
    assert result.name == expected and result.api_key == key
    assert "api_key=" not in repr(result)


def test_async_client_closes_and_passes_deepseek_options(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "test-only")
    client = AsyncMock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[1])
    context = AsyncMock()
    context.__aenter__.return_value = client
    factory = Mock(return_value=context)
    monkeypatch.setattr(provider, "AsyncOpenAI", factory)
    asyncio.run(provider.chat_completion(messages=[], max_tokens=100))
    assert factory.call_args.kwargs["base_url"] == "https://api.deepseek.com"
    assert client.chat.completions.create.call_args.kwargs["extra_body"]["thinking"]["type"] == "disabled"
    context.__aexit__.assert_awaited_once()


def test_missing_selected_key_has_no_network_call(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", None)
    factory = Mock()
    monkeypatch.setattr(provider, "AsyncOpenAI", factory)
    with pytest.raises(provider.LLMRequestError, match="missing_api_key"):
        asyncio.run(provider.chat_completion(messages=[]))
    factory.assert_not_called()
