"""OpenAI client wrapper."""
import asyncio
import logging
from app.llm.provider import get_chat_provider, classify_error
from app.config import settings
from typing import Optional, Any


def OpenAI(**kwargs):
    from openai import OpenAI as SDKClient
    return SDKClient(**kwargs)


class LLMClient:
    """Wrapper for OpenAI client with optional stub mode."""
    
    def __init__(self):
        self.client: Optional[Any] = None
        self.use_stub = False
        self.failure_code: Optional[str] = None
        
        # Try to initialize the real OpenAI client if we have an API key.
        # If anything goes wrong (version mismatch, bad env, network issues),
        # we gracefully fall back to stub mode instead of crashing the API.
        self.provider = get_chat_provider()
        self.using_deepseek = self.provider.name == "deepseek"
        api_key = self.provider.api_key
        if api_key:
            try:
                self.client = OpenAI(**self.provider.client_options())
            except Exception as exc:  # pragma: no cover - defensive fallback
                self.failure_code = "client_initialization_failed"
                logging.getLogger(__name__).warning("LLM initialization failed (%s)", type(exc).__name__)
                self.client = None
                self.use_stub = True
        else:
            self.use_stub = True
            self.failure_code = "missing_api_key"
    
    def is_available(self) -> bool:
        """Check if real LLM is available."""
        return not self.use_stub
    
    async def generate_completion(
        self, system_prompt: str, user_prompt: str, model: Optional[str] = None
    ) -> str:
        """
        Generate text completion using OpenAI API or stub.
        
        Args:
            system_prompt: System message for the LLM
            user_prompt: User message/content
            model: Model name (defaults to config setting)
        
        Returns:
            Generated text response
        """
        if self.use_stub:
            return self._generate_stub_response(system_prompt, user_prompt)
        
        model_name = model or self.provider.model
        
        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=1200,
                extra_body=(
                    {"thinking": {"type": "disabled"}}
                    if self.using_deepseek
                    else None
                ),
            )
            content = response.choices[0].message.content if response.choices else None
            if not content or not content.strip():
                self.failure_code = "empty_response"
                return self._generate_stub_response(system_prompt, user_prompt)
            self.failure_code = None
            return content
        except Exception as e:
            status = getattr(e, "status_code", None)
            self.failure_code = classify_error(e)
            # Do not log raw upstream errors: they can contain credentials/request data.
            logging.getLogger(__name__).warning(
                "LLM request failed: provider=%s code=%s status=%s",
                "deepseek" if self.using_deepseek else "openai", self.failure_code, status,
            )
            return self._generate_stub_response(system_prompt, user_prompt)
    
    def _generate_stub_response(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        """Generate a stub response when LLM is not available."""
        reasons = {
            "missing_api_key": "尚未配置 AI 服务密钥。",
            "client_initialization_failed": "AI 服务客户端初始化失败。",
            "authentication_failed": "AI 服务密钥校验失败（401），请检查密钥。",
            "insufficient_balance": "AI 服务返回余额不足（402），请检查 API 账户余额。",
            "access_denied": "AI 服务拒绝访问（403），请检查账户权限。",
            "model_not_found": "AI 服务未找到所请求的模型或接口（404）。",
            "invalid_request": "AI 服务不接受当前模型或请求参数，请检查模型配置。",
            "rate_limited": "AI 服务请求过于频繁或配额受限（429），请稍后重试。",
            "timeout": "连接 AI 服务超时，请检查网络后重试。",
            "connection_failed": "无法连接 AI 服务，请检查后端网络或代理设置；这不代表余额不足。",
            "empty_response": "AI 服务未返回有效的文字解读，请稍后重试。",
        }
        reason = reasons.get(self.failure_code, "AI 服务暂时不可用，请稍后重试。")
        return f"AI 行程解读暂不可用：{reason}\n\n下方行程由规划算法生成，仍可查看；本次未生成 AI 解读。"
