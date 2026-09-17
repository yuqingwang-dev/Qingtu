"""Domestic route-aware refinement of the existing optimizer's POI set.

Uses directed travel snapshots, exact within-day ordering (<=3 POIs) and two
local-swap passes between days. This is not a global shortest-path guarantee.
"""
import asyncio
from datetime import datetime, timedelta, time
from itertools import permutations

from fastapi import HTTPException

from app.config import settings
from app.core.scoring import haversine_distance, get_budget_threshold
from app.providers.amap_routes import AmapRouteProvider, estimate_leg
from app.services.live_poi_service import search_city_pois, _canonical_name
from app.core.route_cities import ROUTE_CITIES, supports_real_routes


def validate_route_city(preferences, city):
    if preferences.use_real_routes and not supports_real_routes(city.name, getattr(city, "is_domestic", False)):
        raise HTTPException(status_code=422, detail="真实路线当前支持北京、上海、杭州、成都，请关闭该选项或选择支持的城市")


def route_candidates(preferences, activities):
    """Prefer verified coordinates before initial selection, keeping must-visits.

    Generic seed experiences such as 'hotpot dinner' are not a verified venue.
    If the verified catalog is too small, retain the existing fallback pool.
    """
    if not preferences.use_real_routes:
        return activities
    verified = [a for a in activities if (a.provider_metadata or {}).get("coordinate_system") == "GCJ02"]
    if len(verified) < (preferences.end_date - preferences.start_date).days + 1:
        return activities
    names = set(preferences.constraints.must_visit or []) if preferences.constraints else set()
    known_ids = {a.id for a in verified}
    return verified + [a for a in activities if a.id not in known_ids and (a.name in names or a.name_zh in names)]


def evaluate_order(order, day_date, preferences, matrix, activities):
    start = datetime.combine(day_date, time.fromisoformat(preferences.daily_start_time))
    deadline = datetime.combine(day_date, time.fromisoformat(preferences.daily_end_time))
    now, previous, cost = start, 0, 0.0
    legs, visits = [], []
    budget = get_budget_threshold(preferences.budget_level.value, preferences.budget_per_day) * 1.2
    for block in order:
        identity = block.activity.id
        leg = matrix[previous, identity]
        arrival = now + timedelta(minutes=leg["duration_minutes"])
        visit_start = arrival
        activity = activities[identity]
        closing = deadline
        if activity.open_time is not None and activity.close_time is not None:
            opening = datetime.combine(day_date, activity.open_time)
            closing = datetime.combine(day_date, activity.close_time)
            if closing < opening:
                closing += timedelta(days=1)
            visit_start = max(arrival, opening)
        finish = visit_start + timedelta(minutes=block.activity.duration)
        return_minutes = matrix[identity, 0]["duration_minutes"] if preferences.return_to_lodging else 0
        if (cost + block.activity.cost > budget or finish > closing
                or finish + timedelta(minutes=return_minutes) > deadline):
            continue
        visits.append((block, visit_start, finish, leg))
        legs.append(leg)
        now, previous = finish, identity
        cost += block.activity.cost
    if visits and preferences.return_to_lodging:
        returning = matrix[previous, 0]
        legs.append(returning)
        now += timedelta(minutes=returning["duration_minutes"])
    return dict(visits=visits, legs=legs, finish=now, start=start, cost=cost,
                travel=sum(leg["duration_minutes"] for leg in legs),
                distance=sum(leg["distance_meters"] for leg in legs))


def best_day(blocks, day_date, preferences, matrix, activities, must_ids):
    choices = [evaluate_order(order, day_date, preferences, matrix, activities) for order in permutations(blocks)]
    return min(choices, key=lambda result: (
        -sum(b.activity.id in must_ids for b, *_ in result["visits"]),
        -len(result["visits"]), result["travel"], result["distance"], result["finish"]))


def optimize_groups(groups, dates, preferences, matrix, activities, must_ids):
    def evaluate(grouping):
        return [best_day(group, date, preferences, matrix, activities, must_ids) for group, date in zip(grouping, dates)]
    def score(results):
        return (-sum(b.activity.id in must_ids for r in results for b, *_ in r["visits"]),
                -sum(len(r["visits"]) for r in results), sum(r["travel"] for r in results),
                sum(r["distance"] for r in results))
    best = evaluate(groups)
    for _ in range(2):
        improved = False
        for first in range(len(groups)):
            for second in range(first + 1, len(groups)):
                for i in range(len(groups[first])):
                    for j in range(len(groups[second])):
                        trial = [list(group) for group in groups]
                        trial[first][i], trial[second][j] = trial[second][j], trial[first][i]
                        result = evaluate(trial)
                        if score(result) < score(best):
                            groups, best, improved = trial, result, True
        if not improved:
            break
    return best


async def apply_real_routes(itinerary, preferences, activities, city):
    if not preferences.use_real_routes:
        return None
    validate_route_city(preferences, city)
    route_city = ROUTE_CITIES[city.name]
    lodging = preferences.lodging
    if haversine_distance(lodging.latitude, lodging.longitude, city.latitude, city.longitude) > 150:
        raise HTTPException(status_code=422, detail=f"住宿位置距离{route_city}过远，请重新选择")
    by_id = {a.id: a for a in activities}
    names = set(preferences.constraints.must_visit or []) if preferences.constraints else set()
    must_ids = {a.id for a in activities if a.name in names or a.name_zh in names}
    warnings = ["交通方案为查询时快照，未来路况、公交班次和地点开放状态可能变化；请出发前再次核实。"]
    skipped, groups = [], []
    for day in itinerary.days:
        mandatory = [b for b in day.blocks if b.activity.id in must_ids]
        if len(mandatory) > 3:
            raise HTTPException(status_code=422, detail="本版每天最多安排3个主要地点，必去地点超过容量，请调整条件")
        chosen = mandatory + [b for b in day.blocks if b.activity.id not in must_ids][:3-len(mandatory)]
        chosen_ids = {b.activity.id for b in chosen}
        groups.append([b for b in day.blocks if b.activity.id in chosen_ids])
        skipped.extend({"id": b.activity.id, "name": b.activity.name_zh or b.activity.name,
                        "reason": "真实路线首版每天最多3个主要地点"} for b in day.blocks if b.activity.id not in chosen_ids)
    blocks = {b.activity.id: b for group in groups for b in group}
    points = {0: {"id": 0, "name": lodging.name, "latitude": lodging.latitude,
                  "longitude": lodging.longitude, "verified": True, "coordinate_system": "GCJ02"}}
    for identity, block in blocks.items():
        point = {"id": identity, "name": block.activity.name_zh or block.activity.name,
                 **block.activity.coordinates.model_dump(), "verified": False, "coordinate_system": "unknown"}
        if (block.activity.poi_source or {}).get("coordinate_system") == "GCJ02":
            point.update(verified=True, coordinate_system="GCJ02")
        else:
            result, _ = await search_city_pois(city, point["name"], 5)
            matches = [p for p in result.data if _canonical_name(p.name) == _canonical_name(point["name"])
                       and p.latitude is not None and p.longitude is not None
                       and haversine_distance(point["latitude"], point["longitude"], p.latitude, p.longitude) < 1.5]
            if matches:
                poi = matches[0]
                point.update(latitude=poi.latitude, longitude=poi.longitude, verified=True, coordinate_system="GCJ02")
                block.activity.coordinates.latitude, block.activity.coordinates.longitude = poi.latitude, poi.longitude
                block.activity.poi_source = {**(block.activity.poi_source or {}), "coordinate_system": "GCJ02", "coordinate_provider": "amap"}
        points[identity] = point
    matrix = {}
    provider = AmapRouteProvider(city_name=route_city)
    semaphore = asyncio.Semaphore(3)
    async def fetch(first, second):
        async with semaphore:
            matrix[first, second] = await provider.route(points[first], points[second], preferences.travel_mode.value)
    pairs = [(a, b) for a in points for b in points if a != b]
    try:
        await asyncio.wait_for(asyncio.gather(*(fetch(a, b) for a, b in pairs)), settings.ROUTE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        warnings.append("路线查询达到时间上限，未完成的区间已标记为估算")
    for first, second in pairs:
        if (first, second) not in matrix:
            matrix[first, second] = estimate_leg(points[first], points[second], preferences.travel_mode.value, "query_timeout")

    def ordered_travel(group):
        ids = [0] + [b.activity.id for b in group] + ([0] if preferences.return_to_lodging and group else [])
        return sum(matrix[a, b]["duration_minutes"] for a, b in zip(ids, ids[1:]))
    baseline = sum(ordered_travel(group) for group in groups)
    results = optimize_groups(groups, [day.date for day in itinerary.days], preferences, matrix, by_id, must_ids)
    planned = {b.activity.id for result in results for b, *_ in result["visits"]}
    if not must_ids.issubset(planned):
        raise HTTPException(status_code=422, detail="在指定出发/返程时间和交通条件下，无法安排全部必去地点，请放宽条件")
    for day, result in zip(itinerary.days, results):
        new_blocks = []
        for block, start, end, leg in result["visits"]:
            updated = block.model_copy(deep=True)
            updated.start_time, updated.end_time = start.isoformat(), end.isoformat()
            updated.travel_time_from_previous = leg["duration_minutes"]
            new_blocks.append(updated)
        day.blocks = new_blocks
        day.total_cost = result["cost"]
        day.total_duration_minutes = int((result["finish"] - result["start"]).total_seconds() / 60)
        day.route_summary = {"lodging": points[0], "legs": result["legs"],
            "departure_time": result["start"].isoformat(), "finish_time": result["finish"].isoformat(),
            "return_to_lodging": preferences.return_to_lodging, "travel_minutes": result["travel"],
            "distance_meters": result["distance"], "estimated_legs": sum(l["source"] == "estimated" for l in result["legs"]),
            "deadline_satisfied": True, "deadline_is_forecast": True}
    for identity in set(blocks) - planned:
        skipped.append({"id": identity, "name": points[identity]["name"], "reason": "交通、开放时间或预算无法满足当天时间窗"})
    actual = sum(r["travel"] for r in results)
    estimates = sum(leg["source"] == "estimated" for result in results for leg in result["legs"])
    if estimates:
        warnings.append(f"最终路线有 {estimates} 段使用估算，请勿将其当作已核验的道路导航")
    if skipped:
        warnings.append(f"有 {len(skipped)} 个原候选未排入，原因见未安排地点列表")
    itinerary.summary.total_cost = sum(d.total_cost for d in itinerary.days)
    itinerary.summary.avg_cost_per_day = itinerary.summary.total_cost / max(1, len(itinerary.days))
    itinerary.summary.categories_covered = sorted({b.activity.category for d in itinerary.days for b in d.blocks})
    itinerary.summary.pace_label = "Relaxed"
    return {"provider": "amap", "coordinate_system": "GCJ02", "warnings": warnings,
        "city_id": city.id, "city_name": route_city,
        "candidate_policy": "有足够数据时优先使用坐标已核验的真实地点；保留用户必去地点",
        "status": "partial" if estimates else "live", "unplanned": skipped,
        "baseline_travel_minutes": baseline if planned == set(blocks) else None,
        "optimized_travel_minutes": actual,
        "saved_travel_minutes": baseline - actual if planned == set(blocks) else None,
        "comparison_scope": "同一批选定地点、住宿起终点、交通模式和查询快照；含估算段时比较也是估算",
        "matrix_pairs": len(matrix), "live_requests": provider.requests, "cache_hits": provider.cache_hits,
        "search_method": "每日全排列 + 跨天两轮局部交换，不保证全局最优"}
