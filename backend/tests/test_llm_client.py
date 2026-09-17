"""No-network tests for provider selection and truthful failure reporting."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.config import settings
from app.llm.client import LLMClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "test-key-not-real")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    mock = Mock()
    monkeypatch.setattr("app.llm.client.OpenAI", mock)
    return LLMClient()


def test_deepseek_success(client):
    client.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="中文行程解读"))])
    assert asyncio.run(client.generate_completion("system", "test")) == "中文行程解读"
    assert client.failure_code is None
    params = client.client.chat.completions.create.call_args.kwargs
    assert params["model"] == settings.DEEPSEEK_MODEL
    assert params["extra_body"]["thinking"]["type"] == "disabled"


@pytest.mark.parametrize("status,code", [(401,"authentication_failed"), (402,"insufficient_balance"),
                                        (404,"model_not_found"), (429,"rate_limited"), (503,"provider_error")])
def test_status_errors_are_distinguished_without_leaking_payload(client, status, code, caplog):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"))
    client.client.chat.completions.create.side_effect = APIStatusError(
        "sensitive-value-must-not-be-logged", response=response, body=None)
    text = asyncio.run(client.generate_completion("system", "test"))
    assert client.failure_code == code
    assert "OPENAI_API_KEY" not in text
    assert "sensitive-value" not in text + caplog.text


@pytest.mark.parametrize("error,code", [(APIConnectionError,"connection_failed"), (APITimeoutError,"timeout")])
def test_network_errors_not_mislabeled_as_balance(client, error, code):
    client.client.chat.completions.create.side_effect = error(request=httpx.Request("POST", "https://api.deepseek.com"))
    text = asyncio.run(client.generate_completion("system", "test"))
    assert client.failure_code == code
    assert "返回余额不足" not in text


def test_missing_key(monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    client = LLMClient()
    assert "尚未配置" in asyncio.run(client.generate_completion("system", "test"))
    assert client.failure_code == "missing_api_key"


def test_empty_response(client):
    client.client.chat.completions.create.return_value = SimpleNamespace(choices=[])
    asyncio.run(client.generate_completion("system", "test"))
    assert client.failure_code == "empty_response"
