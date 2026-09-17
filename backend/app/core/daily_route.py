"""Order a small day's POI set using estimated distance and opening hours.

This is an open route (no hotel/depot) and does not use live road directions.
The optimizer caps each day at seven POIs, so enumerating orders is bounded.
"""
from datetime import datetime, timedelta
from itertools import permutations

from app.core.scoring import estimate_travel_time, haversine_distance, get_budget_threshold


def feasible_daily_candidates(activities, preferences):
    """POIs that can individually fit an existing daily budget/time window.

    Current catalog hours repeat daily; weekday exceptions are not modeled yet.
    Use the same 20% budget tolerance as the existing CP-SAT planner.
    """
    budget = get_budget_threshold(preferences.budget_level.value, preferences.budget_per_day)
    start = datetime.combine(preferences.start_date, datetime.min.time()).replace(hour=9)
    unique = {a.id: a for a in activities}
    return [a for a in unique.values() if a.base_cost <= budget * 1.2
            and schedule_daily_route([a], start, preferences.travel_mode)]


def schedule_daily_route(activities, day_start, travel_mode, must_visit_names=()):
    """Prefer feasible visits, then shorter travel, then less waiting.

Return (activity, start, end, estimated_travel_minutes) tuples. Opening-hour
waiting is permitted, but a visit must finish before closing and 22:00.
"""
    day_end = day_start.replace(hour=22, minute=0)
    best, best_key = [], None
    for order in permutations(sorted(activities, key=lambda a: a.id)):
        schedule = []
        now = day_start
        previous = None
        distance_total = 0.0
        waiting_total = 0.0
        for activity in order:
            distance = 0.0 if previous is None else haversine_distance(
                previous.latitude, previous.longitude, activity.latitude, activity.longitude
            )
            travel = estimate_travel_time(distance, travel_mode)
            arrival = now + timedelta(minutes=travel)
            start, closing = arrival, day_end
            if activity.open_time is not None and activity.close_time is not None:
                opening = datetime.combine(day_start.date(), activity.open_time)
                closing = datetime.combine(day_start.date(), activity.close_time)
                if closing < opening:
                    closing += timedelta(days=1)
                start = max(arrival, opening)
            end = start + timedelta(minutes=activity.avg_duration_minutes)
            if end > min(closing, day_end):
                continue
            schedule.append((activity, start, end, travel))
            distance_total += distance
            waiting_total += (start - arrival).total_seconds() / 60
            now, previous = end, activity
        key = (
            -sum(a.name in must_visit_names for a, *_ in schedule),
            -len(schedule),
            round(distance_total, 6),
            waiting_total,
            tuple(a.id for a, *_ in schedule),
        )
        if best_key is None or key < best_key:
            best, best_key = schedule, key
    return best
