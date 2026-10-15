"""Non-secret dependency status checks used by the status API and CLI.

Checks are deliberately split into configuration and probe. Configuration is
free and safe to call from a dashboard; an LLM probe is opt-in because it may
consume quota and can expose an upstream account error.
"""
from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.cache import cache
from app.llm.provider import LLMRequestError, chat_completion, get_chat_provider


_ERROR_MESSAGES = {
    "missing_api_key": "未配置 API Key",
    "authentication_failed": "API Key 无效或认证失败（401）",
    "insufficient_balance": "账户余额或配额不足（402）",
    "access_denied": "账户没有调用权限（403）",
    "model_not_found": "模型不存在或当前账户不可用（404）",
    "invalid_request": "请求参数或模型配置无效",
    "rate_limited": "请求频率或配额受限（429）",
    "timeout": "请求超时",
    "connection_failed": "无法连接模型服务",
    "empty_response": "模型没有返回有效内容",
}


def _llm_config_status() -> dict[str, Any]:
    provider = get_chat_provider()
    if not provider.api_key:
        return {
            "status": "missing_api_key",
            "message": _ERROR_MESSAGES["missing_api_key"],
            "provider": provider.name,
            "model": provider.model,
            "key_configured": False,
            "probe_performed": False,
        }
    return {
        "status": "configured",
        "message": "已配置，尚未验证远程调用",
        "provider": provider.name,
        "model": provider.model,
        "key_configured": True,
        "probe_performed": False,
    }


async def check_llm(*, probe: bool = False) -> dict[str, Any]:
    result = _llm_config_status()
    if not probe or not result["key_configured"]:
        return result
    try:
        await asyncio.wait_for(
            chat_completion(
                messages=[{"role": "user", "content": "Reply with OK only."}],
                max_tokens=2,
                temperature=0,
            ),
            timeout=min(settings.LLM_TIMEOUT_SECONDS, 20),
        )
    except LLMRequestError as exc:
        result.update(status=exc.code, message=_ERROR_MESSAGES.get(exc.code, "模型服务返回错误"))
    except asyncio.TimeoutError:
        result.update(status="timeout", message=_ERROR_MESSAGES["timeout"])
    except Exception:
        result.update(status="connection_failed", message=_ERROR_MESSAGES["connection_failed"])
    else:
        result.update(status="healthy", message="模型调用验证成功")
    result["probe_performed"] = True
    return result


def check_database(db: Session | None = None) -> dict[str, Any]:
    if db is None:
        return {"status": "not_checked", "message": "未执行数据库连通性检查"}
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "message": "数据库连接正常"}
    except Exception:
        db.rollback()
        return {"status": "connection_failed", "message": "无法连接 PostgreSQL"}


def check_redis() -> dict[str, Any]:
    return {
        "status": "healthy" if cache._redis else "disconnected",
        "message": "Redis 连接正常" if cache._redis else "Redis 未连接，已使用无 Redis 降级模式",
    }


def check_optional_services() -> dict[str, Any]:
    return {
        "amap": {
            "status": "configured" if settings.AMAP_WEB_SERVICE_KEY else "not_configured",
            "message": "高德 Web 服务 Key 已配置" if settings.AMAP_WEB_SERVICE_KEY else "未配置高德 Key，将使用已有地点或估算路线",
            "key_configured": bool(settings.AMAP_WEB_SERVICE_KEY),
        },
        "live_poi": {
            "status": "enabled" if settings.LIVE_POI_ENABLED else "disabled",
            "message": "真实 POI 搜索已启用" if settings.LIVE_POI_ENABLED else "真实 POI 搜索已关闭",
        },
    }


async def build_status(db: Session | None = None, *, probe_llm: bool = False) -> dict[str, Any]:
    llm = await check_llm(probe=probe_llm)
    return {
        "status": "healthy" if llm["status"] in {"healthy", "configured"} else "degraded",
        "environment": settings.ENVIRONMENT,
        "checks": {
            "database": check_database(db),
            "redis": check_redis(),
            "llm": llm,
            **check_optional_services(),
        },
        "probe_warning": "LLM probe 会发起一次真实模型请求，可能消耗配额。" if probe_llm else None,
    }
