"""Shared chat-provider configuration; embeddings intentionally stay separate."""
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings


def AsyncOpenAI(**kwargs):
    # POI/health/catalog endpoints should not require eagerly importing the
    # entire model SDK. Keep the factory injectable for offline tests.
    from openai import AsyncOpenAI as SDKClient
    return SDKClient(**kwargs)


class LLMRequestError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ChatProvider:
    name: str
    model: str
    api_key: Optional[str] = field(repr=False)
    base_url: str

    def client_options(self):
        return dict(api_key=self.api_key, base_url=self.base_url,
                    timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=1)

    def request_options(self):
        return {"extra_body": {"thinking": {"type": "disabled"}}} if self.name == "deepseek" else {}


def get_chat_provider() -> ChatProvider:
    name = settings.LLM_PROVIDER
    if name == "auto":
        name = "deepseek" if settings.DEEPSEEK_API_KEY else "openai"
    if name == "deepseek":
        return ChatProvider(name, settings.DEEPSEEK_MODEL, settings.DEEPSEEK_API_KEY,
                            "https://api.deepseek.com")
    return ChatProvider(name, settings.OPENAI_MODEL, settings.OPENAI_API_KEY,
                        "https://api.openai.com/v1")


def classify_error(error: Exception) -> str:
    from openai import APIConnectionError, APITimeoutError
    if isinstance(error, LLMRequestError):
        return error.code
    if isinstance(error, APITimeoutError):
        return "timeout"
    if isinstance(error, APIConnectionError):
        return "connection_failed"
    return {401: "authentication_failed", 402: "insufficient_balance", 403: "access_denied",
            404: "model_not_found", 400: "invalid_request", 422: "invalid_request",
            429: "rate_limited"}.get(getattr(error, "status_code", None), "provider_error")


async def chat_completion(**kwargs):
    """Async, bounded call used by tools and structured intent parsing.

    Unlike narrative generation, this must never return demonstration text as
    if it were a valid tool decision or JSON payload.
    """
    provider = get_chat_provider()
    if not provider.api_key:
        raise LLMRequestError("missing_api_key")
    try:
        async with AsyncOpenAI(**provider.client_options()) as client:
            response = await client.chat.completions.create(
                model=provider.model, **provider.request_options(), **kwargs
            )
        if not response.choices:
            raise LLMRequestError("empty_response")
        return response
    except Exception as error:
        raise LLMRequestError(classify_error(error)) from None
