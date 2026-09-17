"""OR-Tools based optimizer for advanced itinerary planning."""
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Tuple
from ortools.sat.python import cp_model
from app.api.schemas import (
    TripPreferences,
    ItineraryDay,
    ItineraryBlock,
    ItinerarySummary,
    ActivitySummary,
    Coordinates,
    EnergyLevel,
)
from app.db.models import Activity
from app.core.scoring import (
    score_activity,
    haversine_distance,
    estimate_travel_time,
    get_budget_threshold,
)
from app.core.optimizer import (
    Itinerary,
    get_activities_per_day,
    get_day_start_time,
    is_activity_available,
)
from app.core.daily_route import schedule_daily_route, feasible_daily_candidates


def build_itinerary_ortools(
    preferences: TripPreferences, activities: List[Activity]
) -> Itinerary:
    """
    Build an optimized itinerary using OR-Tools CP-SAT solver.
    
    This is a more advanced optimizer that uses constraint programming
    to find optimal solutions considering multiple objectives.
    """
    itinerary = Itinerary()
    
    # Calculate trip duration
    trip_days = (preferences.end_date - preferences.start_date).days + 1
    min_activities, max_activities = get_activities_per_day(
        preferences.energy_level
    )
    
    if not activities:
        return itinerary
    
    # For now, use greedy as fallback for complex cases
    # OR-Tools implementation for full optimization would be very complex
    # This is a simplified version that demonstrates the approach
    
    # Filter activities based on constraints
    available_activities = []
    must_visit_names = set()
    if preferences.constraints and preferences.constraints.must_visit:
        must_visit_names = set(preferences.constraints.must_visit)
    
    for activity in activities:
        # Skip if in avoid list
        if (
            preferences.constraints
            and preferences.constraints.avoid
            and activity.name in preferences.constraints.avoid
        ):
            continue
        available_activities.append(activity)
    
    # Do not reserve a day's slot for a POI that cannot be visited at all.
    available_activities = feasible_daily_candidates(available_activities, preferences)

    # If we have must-visit activities, ensure they're included
    must_visit_activities = [
        a for a in available_activities if a.name in must_visit_names
    ]
    
    # For v2, we'll use a hybrid approach:
    # 1. Use OR-Tools for day-level optimization (which activities per day)
    # 2. Use greedy for ordering within each day (simpler and faster)
    
    # Create model
    model = cp_model.CpModel()
    
    # Decision variables: activity_selected[day][activity_idx] = 1 if activity is selected for that day
    activity_selected = {}
    for day in range(trip_days):
        for act_idx, activity in enumerate(available_activities):
            activity_selected[(day, act_idx)] = model.NewBoolVar(
                f"activity_{day}_{act_idx}"
            )
    
    # Constraints
    daily_budget = get_budget_threshold(
        preferences.budget_level.value, preferences.budget_per_day
    )

    # Scale budget to cents (integers) for OR-Tools CP-SAT solver
    daily_budget_cents = int(daily_budget * 100)

    # 1. Budget constraint per day (using cents to avoid floats)
    for day in range(trip_days):
        daily_cost = sum(
            activity_selected[(day, act_idx)] * int(available_activities[act_idx].base_cost * 100)
            for act_idx in range(len(available_activities))
        )
        model.Add(daily_cost <= int(daily_budget_cents * 1.2))  # Allow 20% flexibility
    
    # 2. Spread scarce POIs across the requested days, without requiring repeats.
    # Under-filled days are allowed (e.g. an unaffordable or small catalog).
    daily_counts = []
    shortfalls = []
    target_min = min(min_activities, len(available_activities) // trip_days)
    daily_cap = min(max_activities, (len(available_activities) + trip_days - 1) // trip_days)
    for day in range(trip_days):
        daily_count = model.NewIntVar(0, daily_cap, f"count_{day}")
        model.Add(daily_count == sum(
            activity_selected[(day, act_idx)]
            for act_idx in range(len(available_activities))
        ))
        daily_counts.append(daily_count)
        if len(available_activities) >= trip_days:
            model.Add(daily_count >= 1)
        shortfall = model.NewIntVar(0, target_min, f"shortfall_{day}")
        model.Add(shortfall >= target_min - daily_count)
        shortfalls.append(shortfall)
        model.Add(sum(
            activity_selected[(day, i)] * a.avg_duration_minutes
            for i, a in enumerate(available_activities)
        ) <= 13 * 60)
    for day in range(1, trip_days):
        # Days are interchangeable at this stage; keep the fuller days first.
        model.Add(daily_counts[day - 1] >= daily_counts[day])
    model.Add(daily_counts[0] - daily_counts[-1] <= 1)
    
    # 3. Must-visit activities must be included somewhere
    for must_visit_name in must_visit_names:
        must_visit_indices = [
            act_idx
            for act_idx, act in enumerate(available_activities)
            if act.name == must_visit_name
        ]
        if must_visit_indices:
            # At least one day must include this activity
            model.Add(
                sum(
                    activity_selected[(day, act_idx)]
                    for day in range(trip_days)
                    for act_idx in must_visit_indices
                ) >= 1
            )
    
    # 4. Each POI may appear at most once over the ENTIRE trip.
    indices_by_id = {}
    for act_idx, activity in enumerate(available_activities):
        indices_by_id.setdefault(activity.id, []).append(act_idx)
    for indices in indices_by_id.values():
        model.Add(sum(activity_selected[(day, i)]
                      for day in range(trip_days) for i in indices) <= 1)
    
    # Objective: Maximize total utility score
    # Utility = sum of activity scores weighted by rating, category match, etc.
    total_utility = []
    for day in range(trip_days):
        current_date = preferences.start_date + timedelta(days=day)
        day_start = get_day_start_time().replace(
            year=current_date.year,
            month=current_date.month,
            day=current_date.day,
        )
        
        day_state = {
            "current_cost": 0.0,
            "available_time_minutes": 480,  # 8 hours
        }
        
        for act_idx, activity in enumerate(available_activities):
            # Calculate base score for this activity
            score = score_activity(activity, preferences, day_state, None)
            # Weight by selection (ensure integer for OR-Tools)
            score_int = int(round(score * 100))
            total_utility.append(
                activity_selected[(day, act_idx)] * score_int  # Scale for integer solver
            )
    
    # Prefer nearby POIs on the same day. Bound the quadratic model size;
    # larger catalogs still retain global uniqueness and daily route ordering.
    spread_penalties = []
    if len(available_activities) <= 60:
        for i, first in enumerate(available_activities):
            for j in range(i + 1, len(available_activities)):
                second = available_activities[j]
                distance = haversine_distance(
                    first.latitude, first.longitude, second.latitude, second.longitude
                )
                weight = round(min(distance, 50) * 60)
                for day in range(trip_days):
                    together = model.NewBoolVar(f"pair_{day}_{i}_{j}")
                    model.AddMultiplicationEquality(together, [
                        activity_selected[(day, i)], activity_selected[(day, j)]
                    ])
                    spread_penalties.append(weight * together)
    model.Maximize(sum(total_utility) - sum(spread_penalties) - 20000 * sum(shortfalls))
    
    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0  # Limit solve time
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.Solve(model)
    
    # If solution found, build itinerary
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        # Build days from solution
        for day in range(trip_days):
            current_date = preferences.start_date + timedelta(days=day)
            day_start = get_day_start_time().replace(
                year=current_date.year,
                month=current_date.month,
                day=current_date.day,
            )
            
            # Get selected activities for this day
            selected_activities = [
                available_activities[act_idx]
                for act_idx in range(len(available_activities))
                if solver.Value(activity_selected[(day, act_idx)]) == 1
            ]
            
            # Order today's selected set by distance, respecting opening hours.
            blocks = []
            daily_cost = 0.0
            daily_duration = 0
            schedule = schedule_daily_route(
                selected_activities, day_start, preferences.travel_mode, must_visit_names
            )
            for best_activity, start_time, end_time, best_travel_time in schedule:
                activity_summary = ActivitySummary(
                    id=best_activity.id,
                    name=best_activity.name,
                    name_zh=best_activity.name_zh if hasattr(best_activity, "name_zh") else None,
                    category=best_activity.category,
                    cost=best_activity.base_cost,
                    duration=best_activity.avg_duration_minutes,
                    rating=best_activity.rating,
                    coordinates=Coordinates(
                        latitude=best_activity.latitude,
                        longitude=best_activity.longitude,
                    ),
                    tags=best_activity.tags if hasattr(best_activity, 'tags') else None,
                    description=best_activity.description if hasattr(best_activity, 'description') else None,
                    description_zh=best_activity.description_zh if hasattr(best_activity, "description_zh") else None,
                )
                
                block = ItineraryBlock(
                    start_time=start_time.isoformat(),
                    end_time=end_time.isoformat(),
                    activity=activity_summary,
                    travel_time_from_previous=best_travel_time if best_travel_time > 0 else None,
                )
                
                blocks.append(block)
                daily_cost += best_activity.base_cost
                daily_duration = int((end_time - day_start).total_seconds() / 60)

            itinerary.days.append(ItineraryDay(
                date=current_date,
                total_cost=daily_cost,
                total_duration_minutes=daily_duration,
                blocks=blocks,
            ))
    else:
        # Preserve the established fallback instead of returning a blank plan.
        from app.core.optimizer import build_itinerary
        return build_itinerary(preferences, activities, use_ortools=False)
    
    # Calculate summary (same as greedy optimizer)
    if itinerary.days:
        total_cost = sum(day.total_cost for day in itinerary.days)
        avg_cost_per_day = total_cost / len(itinerary.days)
        
        categories_covered = set()
        for day in itinerary.days:
            for block in day.blocks:
                categories_covered.add(block.activity.category)
        
        avg_activities_per_day = sum(
            len(day.blocks) for day in itinerary.days
        ) / len(itinerary.days)
        if avg_activities_per_day <= 3:
            pace_label = "Relaxed"
        elif avg_activities_per_day <= 5:
            pace_label = "Moderate"
        else:
            pace_label = "Active"
        
        itinerary.summary = ItinerarySummary(
            total_cost=total_cost,
            avg_cost_per_day=avg_cost_per_day,
            categories_covered=sorted(list(categories_covered)),
            pace_label=pace_label,
        )
        
        # Calculate scores
        budget_utilization = min(1.0, total_cost / max(1, daily_budget * len(itinerary.days)))
        category_coverage = len(categories_covered) / max(1, len(preferences.preferred_categories) if preferences.preferred_categories else 7)
        avg_rating = sum(
            block.activity.rating
            for day in itinerary.days
            for block in day.blocks
        ) / max(1, sum(len(day.blocks) for day in itinerary.days))
        rating_score = avg_rating / 5.0
        
        itinerary.optimization_score = (
            budget_utilization * 0.3 + category_coverage * 0.4 + rating_score * 0.3
        )
        
        confidence = 0.7
        if preferences.preferred_categories:
            matched_categories = len(
                set(categories_covered) & set(cat.value for cat in preferences.preferred_categories)
            )
            confidence += (matched_categories / len(preferences.preferred_categories)) * 0.3
        itinerary.confidence_score = min(1.0, confidence)
    else:
        itinerary.summary = ItinerarySummary(
            total_cost=0.0,
            avg_cost_per_day=0.0,
            categories_covered=[],
            pace_label="None",
        )
        itinerary.optimization_score = 0.0
        itinerary.confidence_score = 0.0
    
    return itinerary

