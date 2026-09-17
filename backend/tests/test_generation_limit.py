"""Daily quota configuration is independent from general rate limiting."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.routes import _check_and_increment_generation_limit
from app.config import Settings, settings
from app.core.cache import cache


@pytest.mark.parametrize("user", [None, SimpleNamespace(id="test-user")])
def test_disabled_quota_does_not_read_or_mutate_existing_counters(monkeypatch, user):
    redis = SimpleNamespace(incr=AsyncMock(return_value=999), expire=AsyncMock(), decr=AsyncMock())
    monkeypatch.setattr(cache, "_redis", redis)
    monkeypatch.setattr(settings, "GENERATION_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    for _ in range(6):
        asyncio.run(_check_and_increment_generation_limit("test-session", user))
    redis.incr.assert_not_awaited()
    redis.expire.assert_not_awaited()
    redis.decr.assert_not_awaited()


def test_disabled_quota_does_not_reconnect_redis(monkeypatch):
    monkeypatch.setattr(settings, "GENERATION_LIMIT_ENABLED", False)
    monkeypatch.setattr(cache, "_redis", None)
    connect = AsyncMock()
    monkeypatch.setattr(cache, "connect", connect)
    asyncio.run(_check_and_increment_generation_limit("test-session", None))
    connect.assert_not_awaited()


@pytest.mark.parametrize("user,limit,key", [
    (None, 3, "gen_count:session:test-session"),
    (SimpleNamespace(id="test-user"), 5, "gen_count:user:test-user"),
])
def test_enabled_quota_accepts_limit_and_rejects_next_request(monkeypatch, user, limit, key):
    redis = SimpleNamespace(incr=AsyncMock(side_effect=range(1, limit + 2)),
                            expire=AsyncMock(), decr=AsyncMock())
    monkeypatch.setattr(cache, "_redis", redis)
    monkeypatch.setattr(settings, "GENERATION_LIMIT_ENABLED", True)
    for _ in range(limit):
        asyncio.run(_check_and_increment_generation_limit("test-session", user))
    with pytest.raises(HTTPException) as error:
        asyncio.run(_check_and_increment_generation_limit("test-session", user))
    assert error.value.status_code == 429
    redis.expire.assert_awaited_once_with(key, 86400)
    redis.decr.assert_awaited_once_with(key)


def test_settings_default_enabled_and_explicit_false(monkeypatch):
    monkeypatch.delenv("GENERATION_LIMIT_ENABLED", raising=False)
    assert Settings(_env_file=None, ENVIRONMENT="production").GENERATION_LIMIT_ENABLED is True
    assert Settings(_env_file=None, GENERATION_LIMIT_ENABLED="False").GENERATION_LIMIT_ENABLED is False
