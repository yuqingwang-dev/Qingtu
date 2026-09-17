"""Bounded domestic POI enrichment with provenance, cache and seed fallback."""
import asyncio
import hashlib
import re
from collections import OrderedDict
from datetime import datetime, timezone

from app.config import settings
from app.contracts.common import ProviderResult
from app.contracts.poi import PoiPracticalInfo, PoiSearchQuery
from app.core.cache import cache
from app.core.scoring import haversine_distance
from app.db.models import Activity
from app.providers.amap_search import AmapSearchProvider

KEYWORDS = {"culture": "名胜古迹", "nature": "公园", "food": "餐饮", "shopping": "购物中心",
            "nightlife": "酒吧", "adventure": "户外运动", "beaches": "海滩"}
ASSUMPTIONS = {"culture": (50, 90), "nature": (30, 90), "food": (80, 60),
               "shopping": (100, 90), "nightlife": (100, 90), "adventure": (100, 120), "beaches": (30, 90)}
_local_cache = OrderedDict()


async def search_city_pois(city, keywords, limit=20):
    query = PoiSearchQuery(city_name=city.name_zh or city.name, text_query=keywords, max_results=limit)
    # Separate cache namespace for each credential without retaining its value.
    digest = hashlib.sha256((str(settings.AMAP_WEB_SERVICE_KEY or "") + query.model_dump_json()).encode()).hexdigest()
    key = "amap:poi:v1:" + digest
    payload = await cache.get(key)
    if payload is None:
        payload = _local_cache.get(key)
    if payload:
        try:
            result = ProviderResult[list[PoiPracticalInfo]].model_validate(payload)
            if result.expires_at and result.expires_at > datetime.now(timezone.utc):
                return result, True
        except (TypeError, ValueError):
            pass
    result = await AmapSearchProvider().search_pois(query)
    if result.data and not result.errors:
        payload = result.model_dump(mode="json")
        await cache.set(key, payload, settings.POI_CACHE_TTL_SECONDS)
        _local_cache[key] = payload
        _local_cache.move_to_end(key)
        while len(_local_cache) > 128:
            _local_cache.popitem(last=False)
    return result, False


def _canonical_name(name):
    return re.sub(r"[\s·（）()\-]", "", name or "").lower()


def persist_pois(db, city, pois, observed_at, expires_at, seeds):
    """Upsert by supplier ID; never overwrite seed/user-authored POIs."""
    imported = []
    for poi in pois:
        if poi.category not in ASSUMPTIONS or poi.latitude is None or poi.longitude is None:
            continue
        # Same-name/nearby seed remains the preferred curated record.
        if any(_canonical_name(poi.name) in {_canonical_name(a.name), _canonical_name(a.name_zh)}
               and haversine_distance(poi.latitude, poi.longitude, a.latitude, a.longitude) < 1
               for a in seeds):
            continue
        cost, duration = ASSUMPTIONS[poi.category]
        cost_kind = "category_estimate"
        if poi.average_spend is not None:
            cost, cost_kind = poi.average_spend, "provider_average_spend"
        metadata = {"provider": "amap", "provider_poi_id": poi.identifier.provider_poi_id,
            "coordinate_system": "GCJ02", "observed_at": observed_at.isoformat(),
            "expires_at": expires_at.isoformat(), "address": poi.address,
            "cost_kind": cost_kind, "duration_kind": "category_estimate",
            "rating_known": poi.rating is not None, "opening_hours": poi.opening_hours,
            "hours_verified_for_trip": False}
        values = dict(city_id=city.id, name=poi.name, name_zh=poi.name, category=poi.category,
            base_cost=cost, avg_duration_minutes=duration, rating=poi.rating if poi.rating is not None else 3.5,
            latitude=poi.latitude, longitude=poi.longitude, open_time=None, close_time=None,
            description=f"高德地点：{poi.name}。地址：{poi.address or '未提供'}。费用和停留时长为规划参考，出行前请核实门票与开放时间。",
            description_zh=f"{poi.address or '地址待确认'}。费用为规划参考，停留时长为估算；出行日期的开放时间和预约要求待确认。",
            tags=["real_poi", "planning_estimate"], provider_name="amap",
            provider_poi_id=poi.identifier.provider_poi_id, provider_metadata=metadata)
        if db.get_bind().dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            from sqlalchemy.dialects.postgresql import insert
        statement = insert(Activity).values(**values).on_conflict_do_update(
            index_elements=["city_id", "provider_name", "provider_poi_id"],
            set_={k: v for k, v in values.items() if k not in {"city_id", "provider_name", "provider_poi_id"}})
        db.execute(statement)
        imported.append(poi.identifier.provider_poi_id)
    db.commit()
    return db.query(Activity).filter(Activity.city_id == city.id, Activity.provider_name == "amap",
        Activity.provider_poi_id.in_(imported)).populate_existing().all() if imported else []


async def enrich_city_catalog(db, city, preferences, existing):
    report = {"status": "local", "provider": None, "fetched_count": 0, "candidate_count": len(existing),
              "cache_hit": False, "warnings": []}
    if not getattr(city, "is_domestic", False):
        return existing, report
    seeds = [a for a in existing if a.provider_name != "amap"]
    if not settings.LIVE_POI_ENABLED:
        report["status"] = "disabled"
        report["candidate_count"] = len(seeds)
        return seeds, report
    report["provider"] = "amap"
    categories = [c.value for c in preferences.preferred_categories] or ["culture", "nature", "food"]
    categories = list(dict.fromkeys(categories))[:3]
    limit = max(1, settings.POI_MAX_RESULTS // len(categories))
    results = await asyncio.gather(*(search_city_pois(city, KEYWORDS[cat], limit) for cat in categories))
    pois, seen = [], set()
    for result, _ in results:
        report["warnings"].extend(error.message + " (" + error.code + ")" for error in result.errors)
        for poi in result.data:
            if poi.identifier.provider_poi_id not in seen:
                seen.add(poi.identifier.provider_poi_id)
                pois.append(poi)
    report["fetched_count"] = len(pois)
    report["cache_hit"] = all(hit for _, hit in results)
    if pois:
        observed_at = min(r.observed_at for r, _ in results)
        expires_at = min(r.expires_at for r, _ in results if r.expires_at)
        try:
            external = persist_pois(db, city, pois, observed_at, expires_at, seeds)
        except Exception:
            db.rollback()
            external = []
            report["warnings"].append("地点保存失败，暂时使用已有资料")
        report["status"] = "partial" if report["warnings"] else "cached" if report["cache_hit"] else "live"
    else:
        external = []
        report["status"] = "fallback"
        report["warnings"].append("本次未取得新的地点，已使用本地资料")
        # Only unexpired snapshots are eligible for automatic reuse.
        for activity in existing:
            meta = activity.provider_metadata or {}
            try:
                if activity.provider_name == "amap" and datetime.fromisoformat(meta["expires_at"]) > datetime.now(timezone.utc):
                    external.append(activity)
            except (KeyError, ValueError, TypeError):
                continue
    # Explicitly cap planner work; no unbounded quadratic optimization growth.
    pool = seeds + external[:max(0, 60 - len(seeds))]
    report["candidate_count"] = len(pool)
    report["warnings"] = list(dict.fromkeys(report["warnings"]))
    return pool, report


def attach_poi_provenance(itinerary, activities):
    by_id = {a.id: a for a in activities}
    for day in itinerary.days:
        for block in day.blocks:
            original = by_id.get(block.activity.id)
            if original is not None and original.provider_name == "amap":
                block.activity.poi_source = original.provider_metadata
                block.notes = "真实地点来源：高德。费用/时长用于估算，开放时间及预约要求请出行前核实。"
