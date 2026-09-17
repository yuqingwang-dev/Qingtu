"""Regression coverage for repeated multi-day itineraries and route ordering."""
from datetime import date, datetime, time, timedelta

import pytest

from app.api.schemas import TripPreferences, TravelMode
from app.core.daily_route import schedule_daily_route
from app.core.optimizer import build_itinerary
from app.core.scoring import haversine_distance
from app.db.models import Activity


def poi(i, **kwargs):
    values = dict(id=i, city_id=1, name=f"POI {i}", category="culture",
                  base_cost=10, avg_duration_minutes=60, rating=4.5,
                  latitude=30.6 + i * .003, longitude=104.0,
                  open_time=time(9), close_time=time(21))
    values.update(kwargs)
    return Activity(**values)


def preferences(days=4, **kwargs):
    values = dict(destination_city_id=1, start_date=date(2026, 10, 1),
                  end_date=date(2026, 10, 1) + timedelta(days=days-1),
                  trip_type="long", budget_level="medium", budget_per_day=300,
                  preferred_categories=["culture"], energy_level="moderate",
                  travel_mode="mixed")
    values.update(kwargs)
    return TripPreferences(**values)


@pytest.mark.parametrize("days,count", [(3, 10), (4, 10), (4, 2)])
def test_entire_trip_unique_balanced_and_preserves_dates(days, count):
    plan = build_itinerary(preferences(days), [poi(i) for i in range(count)], True)
    ids = [b.activity.id for d in plan.days for b in d.blocks]
    counts = [len(d.blocks) for d in plan.days]
    assert len(plan.days) == days
    assert [d.date for d in plan.days] == [date(2026, 10, 1)+timedelta(days=i) for i in range(days)]
    assert len(ids) == len(set(ids)) == count
    assert max(counts) - min(counts) <= 1


def test_unaffordable_catalog_does_not_repeat_or_drop_dates():
    plan = build_itinerary(preferences(budget_per_day=0), [poi(1), poi(2)], True)
    assert len(plan.days) == 4
    assert all(not d.blocks for d in plan.days)


def test_must_visit_once_and_avoid_never():
    plan = build_itinerary(preferences(constraints={"must_visit": ["POI 1"], "avoid": ["POI 2"]}),
                           [poi(i) for i in range(10)], True)
    ids = [b.activity.id for d in plan.days for b in d.blocks]
    assert ids.count(1) == 1
    assert 2 not in ids


def test_nearby_clusters_stay_together():
    activities = [poi(i, latitude=30 + (i//3)*.3 + (i%3)*.001) for i in range(6)]
    plan = build_itinerary(preferences(2), activities, True)
    groups = {frozenset(b.activity.id for b in d.blocks) for d in plan.days}
    assert groups == {frozenset([0, 1, 2]), frozenset([3, 4, 5])}


def test_daily_route_avoids_backtracking_on_line():
    activities = [poi(1, longitude=104), poi(2, longitude=104.03),
                  poi(3, longitude=104.01), poi(4, longitude=104.02)]
    for a in activities:
        a.latitude = 30.6
    result = schedule_daily_route(activities, datetime(2026, 10, 1, 9), TravelMode.walking)
    longitudes = [a.longitude for a, *_ in result]
    assert longitudes in [sorted(longitudes), sorted(longitudes, reverse=True)]


def test_opening_hours_wait_and_finish_before_close():
    activities = [poi(1, open_time=time(14), close_time=time(16)),
                  poi(2, open_time=time(9), close_time=time(11)),
                  poi(3, open_time=time(9), close_time=time(9, 30))]
    result = schedule_daily_route(activities, datetime(2026, 10, 1, 9), TravelMode.mixed)
    assert {a.id for a, *_ in result} == {1, 2}
    for a, start, end, _ in result:
        assert start.time() >= a.open_time
        assert end.time() <= a.close_time


def test_eight_day_trip_has_no_empty_tail_when_enough_feasible_pois():
    activities = [poi(i) for i in range(10)]
    # This POI cannot fit its opening interval and must not occupy a day's slot.
    activities.append(poi(100, open_time=time(9), close_time=time(9, 15)))
    plan = build_itinerary(preferences(8), activities, True)
    assert len(plan.days) == 8
    assert all(day.blocks for day in plan.days)
    ids = [b.activity.id for day in plan.days for b in day.blocks]
    assert len(ids) == len(set(ids)) == 10
    assert 100 not in ids
