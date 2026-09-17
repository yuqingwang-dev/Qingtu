"""Bounded, directed AMap travel-time snapshots with explicit estimates."""
import asyncio
import hashlib
import math
import time
import weakref
from collections import OrderedDict
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.core.cache import cache
from app.core.scoring import haversine_distance
from app.providers.amap_search import _RedactKey

import logging
for _name in ("httpx", "httpx2"):
    logging.getLogger(_name).addFilter(_RedactKey())

_memory = OrderedDict()
_limiters = weakref.WeakKeyDictionary()


def estimate_leg(origin, destination, mode, reason):
    distance = haversine_distance(origin["latitude"], origin["longitude"], destination["latitude"], destination["longitude"])
    speed = 4 if mode == "walking" else 18 if mode in ("public_transport", "mixed") else 25
    return dict(origin=origin, destination=destination, mode=mode, source="estimated", error_code=reason,
        duration_minutes=max(1, math.ceil(distance / speed * 60 + (10 if mode in ("public_transport", "mixed") else 0))),
        distance_meters=round(distance * 1000), geometry=[], instructions=["接口未返回可用路线，按直线距离和平均速度估算"],
        observed_at=datetime.now(timezone.utc).isoformat(), cache_hit=False)


def _positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def _polyline(value):
    if not isinstance(value, str):
        return []
    try:
        points = [list(map(float, point.split(","))) for point in value.split(";")]
        return points if len(points) > 1 and all(len(p) == 2 and 73 <= p[0] <= 135 and 18 <= p[1] <= 54 for p in points) else []
    except (ValueError, TypeError):
        return []


def _has_transport(value):
    # AMap emits empty collection fields even on subway-only journeys.
    return isinstance(value, dict) and any(value.get(key) for key in ("id", "name", "trip", "duration", "distance"))


class AmapRouteProvider:
    def __init__(self, transport=None, interval=.55, *, city_name: str):
        if not city_name.strip():
            raise ValueError("city_name is required")
        self.city_name = city_name
        self.transport, self.interval = transport, interval
        self.requests = 0
        self.cache_hits = 0
        self.unavailable_reason = None

    async def _throttle(self):
        loop = asyncio.get_running_loop()
        limiter = _limiters.setdefault(loop, {"lock": asyncio.Lock(), "last": 0.0})
        async with limiter["lock"]:
            await asyncio.sleep(max(0, self.interval - (time.monotonic() - limiter["last"])))
            limiter["last"] = time.monotonic()

    async def route(self, origin, destination, mode):
        # Mixed mode has a deterministic policy, exposed in the returned leg.
        distance = haversine_distance(origin["latitude"], origin["longitude"], destination["latitude"], destination["longitude"])
        effective_mode = ("walking" if distance <= 1 else "public_transport") if mode == "mixed" else mode
        if not origin.get("verified") or not destination.get("verified"):
            return estimate_leg(origin, destination, effective_mode, "unverified_coordinates")
        if not settings.AMAP_WEB_SERVICE_KEY:
            return estimate_leg(origin, destination, effective_mode, "missing_key")
        if self.unavailable_reason:
            return estimate_leg(origin, destination, effective_mode, self.unavailable_reason)
        coordinates = lambda p: f"{p['longitude']:.6f},{p['latitude']:.6f}"
        descriptor = f"{coordinates(origin)}>{coordinates(destination)}:{effective_mode}:{self.city_name}:snapshot"
        key = "route:v1:" + hashlib.sha256((settings.AMAP_WEB_SERVICE_KEY + descriptor).encode()).hexdigest()
        saved = await cache.get(key) or _memory.get(key)
        if saved and saved.get("expires", 0) > time.time():
            self.cache_hits += 1
            return {**saved["leg"], "origin": origin, "destination": destination, "cache_hit": True}
        if self.requests >= settings.ROUTE_MAX_REQUESTS:
            return estimate_leg(origin, destination, effective_mode, "request_budget")
        self.requests += 1
        await self._throttle()
        params = {"key": settings.AMAP_WEB_SERVICE_KEY, "origin": coordinates(origin), "destination": coordinates(destination)}
        if effective_mode == "public_transport":
            path = "transit/integrated"
            params.update(city=self.city_name, cityd=self.city_name, strategy="0", extensions="all")
        else:
            path = "walking" if effective_mode == "walking" else "driving"
            if path == "driving":
                params.update(strategy="0", extensions="all")
        try:
            async with httpx.AsyncClient(timeout=settings.POI_TIMEOUT_SECONDS, transport=self.transport) as client:
                response = await client.get("https://restapi.amap.com/v3/direction/" + path, params=params)
            if response.status_code != 200:
                return estimate_leg(origin, destination, effective_mode, "http_error")
            data = response.json()
            if str(data.get("status")) != "1":
                code = str(data.get("infocode", "unknown"))
                if code in {"10001", "10002", "10003", "10004", "10009", "10010", "10021"}:
                    self.unavailable_reason = "amap_" + code
                return estimate_leg(origin, destination, effective_mode, "amap_" + code if code.isdigit() else "amap_error")
            field = "transits" if effective_mode == "public_transport" else "paths"
            paths = data.get("route", {}).get(field, [])
            valid = [p for p in paths if isinstance(p, dict) and _positive(p.get("duration")) is not None]
            if effective_mode == "public_transport":
                # This MVP handles walking + bus/subway; do not present partial
                # railway/taxi geometry as a complete local transit route.
                valid = [p for p in valid if not any(_has_transport(s.get("railway")) or _has_transport(s.get("taxi")) for s in p.get("segments", []))]
            if not valid:
                if effective_mode == "public_transport" and distance <= 1.5:
                    walking = await self.route(origin, destination, "walking")
                    walking["instructions"] = ["短途未提供公交方案，改查步行方案"] + walking["instructions"]
                    return walking
                return estimate_leg(origin, destination, effective_mode, "no_route")
            chosen = min(valid, key=lambda p: float(p["duration"]))
            geometry, instructions, meters = [], [], 0.0
            if effective_mode == "public_transport":
                for segment in chosen.get("segments", []):
                    walking = segment.get("walking") or {}
                    if isinstance(walking, dict):
                        meters += _positive(walking.get("distance")) or 0
                        for step in walking.get("steps", []):
                            line = _polyline(step.get("polyline"))
                            if line:
                                geometry.append(line)
                            if step.get("instruction"):
                                instructions.append(str(step["instruction"]))
                    bus = segment.get("bus") or {}
                    for busline in (bus.get("buslines", []) if isinstance(bus, dict) else [])[:1]:
                        meters += _positive(busline.get("distance")) or 0
                        line = _polyline(busline.get("polyline"))
                        if line:
                            geometry.append(line)
                        instructions.append("乘坐 " + str(busline.get("name", "公交")))
            else:
                meters = _positive(chosen.get("distance")) or 0
                for step in chosen.get("steps", []):
                    line = _polyline(step.get("polyline"))
                    if line:
                        geometry.append(line)
                    if step.get("instruction"):
                        instructions.append(str(step["instruction"]))
            leg = dict(origin=origin, destination=destination, mode=effective_mode, source="amap",
                duration_minutes=math.ceil(float(chosen["duration"]) / 60), distance_meters=round(meters),
                geometry=geometry, instructions=instructions[:12], error_code=None,
                observed_at=datetime.now(timezone.utc).isoformat(), cache_hit=False)
            saved = {"expires": time.time() + settings.ROUTE_CACHE_TTL_SECONDS, "leg": leg}
            await cache.set(key, saved, settings.ROUTE_CACHE_TTL_SECONDS)
            _memory[key] = saved
            _memory.move_to_end(key)
            while len(_memory) > 512:
                _memory.popitem(last=False)
            return leg
        except httpx.TimeoutException:
            return estimate_leg(origin, destination, effective_mode, "timeout")
        except Exception:
            return estimate_leg(origin, destination, effective_mode, "connection_or_payload_error")
