import asyncio
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.schemas import ItineraryBlock, ActivitySummary, Coordinates, LodgingLocation
from app.core.optimizer import build_itinerary
from app.services import route_planning as routing
from tests.test_multiday_planning import poi, preferences


def prefs(**kwargs):
    return preferences(2, use_real_routes=True, lodging=LodgingLocation(name="酒店",city_id=1,latitude=30.66,longitude=104.08), **kwargs)


def block(i):
    return ItineraryBlock(start_time="2026-10-01T09:00:00", end_time="2026-10-01T10:00:00",
        activity=ActivitySummary(id=i,name=f"POI {i}",category="culture",cost=10,duration=60,rating=4,
                                 coordinates=Coordinates(latitude=30.66,longitude=104.08+i*.001)))


def matrix(n, minutes=10):
    return {(a,b): {"duration_minutes":minutes,"distance_meters":1000,"source":"amap","geometry":[],
        "origin":{"id":a},"destination":{"id":b},"instructions":[]} for a in range(n+1) for b in range(n+1) if a!=b}


@pytest.mark.parametrize("kwargs", [dict(lodging=None), dict(daily_start_time="20:00",daily_end_time="10:00"),
                                    dict(daily_start_time="25:00"), dict(end_date=date(2026,10,8))])
def test_invalid_route_preferences(kwargs):
    values = preferences(2).model_dump()
    values.update(use_real_routes=True,lodging=dict(name="酒店",city_id=1,latitude=30.66,longitude=104.08))
    values.update(kwargs)
    with pytest.raises(ValidationError):
        type(preferences(2))(**values)


def test_return_leg_is_included_and_deadline_is_respected():
    p = prefs(daily_start_time="10:00",daily_end_time="12:00")
    m = matrix(2, minutes=20)
    result = routing.evaluate_order([block(1),block(2)],date(2026,10,1),p,m,{1:poi(1),2:poi(2)})
    assert len(result["visits"]) == 1 and len(result["legs"]) == 2
    assert result["finish"] == datetime(2026,10,1,11,40)
    assert result["travel"] == 40


def test_no_return_uses_last_poi_as_end():
    p = prefs(return_to_lodging=False)
    result = routing.evaluate_order([block(1)],date(2026,10,1),p,matrix(1),{1:poi(1)})
    assert len(result["legs"]) == 1 and result["finish"].hour == 11


def test_wait_for_opening_and_visit_finishes_before_close():
    p = prefs()
    a = poi(1,open_time=time(14),close_time=time(16))
    result = routing.evaluate_order([block(1)],date(2026,10,1),p,matrix(1),{1:a})
    assert result["visits"][0][1].hour == 14
    a.close_time = time(14,30)
    assert routing.evaluate_order([block(1)],date(2026,10,1),p,matrix(1),{1:a})["visits"] == []


def test_cross_day_swap_reduces_same_set_travel():
    p = prefs()
    m = matrix(4, minutes=10)
    # Two distant clusters, deliberately interleaved across days.
    for a in [1,2]:
        for b in [3,4]:
            m[a,b]["duration_minutes"] = m[b,a]["duration_minutes"] = 90
    groups = [[block(1),block(3)],[block(2),block(4)]]
    result = routing.optimize_groups(groups,[date(2026,10,1),date(2026,10,2)],p,m,{i:poi(i) for i in range(1,5)},set())
    assert {frozenset(b.activity.id for b,*_ in r["visits"]) for r in result} == {frozenset([1,2]),frozenset([3,4])}
    assert sum(r["travel"] for r in result) == 60


@pytest.mark.parametrize("name,region", [("Beijing","北京市"),("Shanghai","上海市"),("Hangzhou","杭州市"),("Chengdu","成都市")])
def test_integration_rebuilds_days_totals_and_reports_skipped(monkeypatch, name, region):
    activities = [poi(i) for i in range(1,9)]
    p = prefs()
    plan = build_itinerary(p,activities,use_ortools=True)
    for day in plan.days:
        for b in day.blocks:
            b.activity.poi_source = {"coordinate_system":"GCJ02"}
    class FakeProvider:
        requests = cache_hits = 0
        def __init__(self, *, city_name):
            assert city_name == region
        async def route(self,a,b,mode):
            return {**matrix(8)[a["id"],b["id"]],"origin":a,"destination":b,"mode":mode,"observed_at":"test","cache_hit":False}
    monkeypatch.setattr(routing,"AmapRouteProvider",FakeProvider)
    report = asyncio.run(routing.apply_real_routes(plan,p,activities,SimpleNamespace(id=1,name=name,is_domestic=True,latitude=30.66,longitude=104.08)))
    assert report["city_name"] == region
    ids = [b.activity.id for day in plan.days for b in day.blocks]
    assert len(ids) == len(set(ids)) == 6
    assert len(report["unplanned"]) == 2
    assert all(d.route_summary and d.route_summary["finish_time"] <= f"{d.date}T20:00:00" for d in plan.days)
    assert plan.summary.total_cost == sum(d.total_cost for d in plan.days)


def test_unsupported_city_is_rejected():
    with pytest.raises(HTTPException):
        routing.validate_route_city(prefs(),SimpleNamespace(name="Paris"))


def test_verified_coordinate_preference_preserves_must_visits():
    activities = [poi(i) for i in range(1,5)]
    for activity in activities[:2]:
        activity.provider_metadata = {"coordinate_system":"GCJ02"}
    p = prefs(constraints={"must_visit":["POI 3"]})
    assert {a.id for a in routing.route_candidates(p,activities)} == {1,2,3}
    assert routing.route_candidates(preferences(2),activities) == activities
