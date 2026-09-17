import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.contracts.poi import PoiIdentifier, PoiPracticalInfo
from app.core.optimizer import build_itinerary
from app.db.models import City, Activity
from app.providers.amap_search import AmapSearchProvider
from app.services import live_poi_service as service
from tests.test_multiday_planning import preferences


@pytest.fixture
def catalog():
    engine = create_engine("sqlite://")
    City.__table__.create(engine)
    Activity.__table__.create(engine)
    with Session(engine) as db:
        city = City(name="Chengdu", name_zh="成都", is_domestic=True, country="China")
        db.add(city)
        db.flush()
        seed = Activity(city_id=city.id, name="Seed", name_zh="原有景点", category="culture", base_cost=20,
            avg_duration_minutes=60, rating=4.5, latitude=30.66, longitude=104.08)
        db.add(seed)
        db.commit()
        yield db, city, seed


def poi(identity="B001", name="真实公园"):
    return PoiPracticalInfo(identifier=PoiIdentifier(provider="amap", provider_poi_id=identity), name=name,
        latitude=30.67, longitude=104.08, coordinate_system="GCJ02", category="nature", city_name="成都市")


def test_upsert_is_idempotent_and_does_not_overwrite_seed(catalog):
    db, city, seed = catalog
    now = datetime.now(timezone.utc)
    first = service.persist_pois(db, city, [poi()], now, now+timedelta(hours=1), [seed])[0]
    stable_id = first.id
    second = service.persist_pois(db, city, [poi(name="更新公园名")], now, now+timedelta(hours=1), [seed])[0]
    assert second.id == stable_id
    assert db.query(Activity).count() == 2
    assert seed.name == "Seed" and seed.provider_name is None
    assert second.provider_metadata["hours_verified_for_trip"] is False
    assert second.provider_metadata["rating_known"] is False
    assert second.provider_metadata["cost_kind"] == "category_estimate"
    assert second.open_time is None


def test_live_candidates_reach_optimizer_and_preserve_metadata(catalog, monkeypatch):
    db, city, seed = catalog
    monkeypatch.setattr(settings, "LIVE_POI_ENABLED", True)
    result = AmapSearchProvider(api_key="test")._result([poi(str(i), f"公园{i}") for i in range(12)])
    monkeypatch.setattr(service, "search_city_pois", AsyncMock(return_value=(result, False)))
    prefs = preferences(8, destination_city_id=city.id)
    pool, report = asyncio.run(service.enrich_city_catalog(db, city, prefs, [seed]))
    assert report["status"] == "live" and len(pool) == 13
    plan = build_itinerary(prefs, pool, use_ortools=True)
    service.attach_poi_provenance(plan, pool)
    assert len(plan.days) == 8 and all(day.blocks for day in plan.days)
    external = [b for d in plan.days for b in d.blocks if b.activity.id != seed.id]
    assert external and all(b.activity.poi_source["provider"] == "amap" for b in external)


def test_provider_failure_keeps_original_catalog(catalog, monkeypatch):
    db, city, seed = catalog
    from app.contracts.common import ProviderError
    result = AmapSearchProvider(api_key="")._result([], [ProviderError(code="missing_key", message="未配置Key")])
    monkeypatch.setattr(settings, "LIVE_POI_ENABLED", True)
    monkeypatch.setattr(service, "search_city_pois", AsyncMock(return_value=(result, False)))
    pool, report = asyncio.run(service.enrich_city_catalog(db, city, preferences(), [seed]))
    assert pool == [seed] and report["status"] == "fallback"
    assert report["warnings"] and db.query(Activity).count() == 1


def test_foreign_cities_do_not_call_domestic_provider(monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(service, "search_city_pois", fetch)
    pool, report = asyncio.run(service.enrich_city_catalog(None, SimpleNamespace(is_domestic=False), preferences(), []))
    assert pool == [] and report["status"] == "local"
    fetch.assert_not_awaited()


def test_cached_search_is_keyed_by_city_and_keywords(monkeypatch):
    service._local_cache.clear()
    monkeypatch.setattr(settings, "AMAP_WEB_SERVICE_KEY", "test")
    monkeypatch.setattr(service.cache, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(service.cache, "set", AsyncMock())
    result = AmapSearchProvider(api_key="test")._result([poi()])
    fetch = AsyncMock(return_value=result)
    monkeypatch.setattr(AmapSearchProvider, "search_pois", fetch)
    city = SimpleNamespace(name="Chengdu", name_zh="成都")
    _, hit = asyncio.run(service.search_city_pois(city, "公园"))
    assert hit is False
    _, hit = asyncio.run(service.search_city_pois(city, "公园"))
    assert hit is True
    asyncio.run(service.search_city_pois(city, "博物馆"))
    assert fetch.await_count == 2
    service._local_cache.clear()
