"""Itinerary optimization engine using greedy algorithm."""
from datetime import date, datetime, timedelta
from typing import List, Optional
from app.config import settings
from app.api.schemas import (
    TripPreferences,
    ItineraryDay,
    ItineraryBlock,
    ItinerarySummary,
    ActivitySummary,
    Coordinates,
    EnergyLevel,
    SelectionExplanation,
)
from app.db.models import Activity
from app.core.scoring import (
    score_activity,
    haversine_distance,
    estimate_travel_time,
    get_budget_threshold,
)


class Itinerary:
    """Internal itinerary representation."""
    def __init__(self):
        self.days: List[ItineraryDay] = []
        self.summary: Optional[ItinerarySummary] = None
        self.optimization_score: float = 0.0
        self.confidence_score: float = 0.0
        self.infeasible_must_visits: Optional[dict] = None  # For error reporting


def get_activities_per_day(energy_level: EnergyLevel) -> tuple[int, int]:
    """Get min and max activities per day based on energy level."""
    ranges = {
        EnergyLevel.relaxed: (2, 3),
        EnergyLevel.moderate: (3, 5),
        EnergyLevel.active: (5, 7),
    }
    return ranges.get(energy_level, (3, 5))


def get_day_start_time() -> datetime:
    """Get default start time for a day (9:00 AM)."""
    return datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)


def is_activity_available(
    activity: Activity, current_time: datetime
) -> bool:
    """Check if activity is available at the given time."""
    if activity.open_time is None or activity.close_time is None:
        return True  # Always open
    
    open_dt = current_time.replace(
        hour=activity.open_time.hour,
        minute=activity.open_time.minute,
        second=0,
        microsecond=0,
    )
    close_dt = current_time.replace(
        hour=activity.close_time.hour,
        minute=activity.close_time.minute,
        second=0,
        microsecond=0,
    )
    
    # Handle activities that close after midnight
    if close_dt < open_dt:
        close_dt += timedelta(days=1)
    
    return open_dt <= current_time <= close_dt


def check_must_visit_feasibility(
    preferences: TripPreferences,
    activities: List[Activity],
    must_visit_names: set
) -> tuple[bool, dict]:
    """
    Check if must-visit activities are feasible.
    
    Returns:
        (is_feasible, infeasible_items) where infeasible_items contains
        reasons why items couldn't be included
    """
    if not must_visit_names:
        return True, {}
    
    infeasible_items = {}
    available_activity_names = {act.name for act in activities}
    
    for name in must_visit_names:
        if name not in available_activity_names:
            infeasible_items[name] = "Activity not found in city"
            continue
        
        # Find the activity
        activity = next((a for a in activities if a.name == name), None)
        if not activity:
            infeasible_items[name] = "Activity not found"
            continue
        
        # Check if it's in avoid list (conflict)
        if (
            preferences.constraints
            and preferences.constraints.avoid
            and name in preferences.constraints.avoid
        ):
            infeasible_items[name] = "Activity is in avoid list (conflict)"
            continue
        
        # Check budget feasibility (rough check)
        daily_budget = get_budget_threshold(
            preferences.budget_level.value, preferences.budget_per_day
        )
        if activity.base_cost > daily_budget * 1.5:  # Allow some flexibility
            infeasible_items[name] = f"Activity cost (${activity.base_cost:.2f}) exceeds budget significantly"
    
    is_feasible = len(infeasible_items) == 0
    return is_feasible, infeasible_items


def build_itinerary(
    preferences: TripPreferences, activities: List[Activity], use_ortools: bool = False
) -> Itinerary:
    """
    Build an optimized itinerary using greedy algorithm or OR-Tools.
    
    Args:
        preferences: User trip preferences
        activities: List of available activities for the city
        use_ortools: If True, use OR-Tools optimizer (experimental)
    
    Returns:
        Itinerary object with days, summary, and scores
    """
    # Use OR-Tools if requested and available
    if use_ortools:
        try:
            from app.core.ortools_optimizer import build_itinerary_ortools
            return build_itinerary_ortools(preferences, activities)
        except ImportError:
            # Fallback to greedy if OR-Tools not available
            pass
    
    itinerary = Itinerary()
    
    # Calculate trip duration
    trip_days = (preferences.end_date - preferences.start_date).days + 1
    min_activities, max_activities = get_activities_per_day(
        preferences.energy_level
    )
    
    # Track used activities to avoid duplicates (unless must-visit requires repeats)
    used_activity_ids = set()
    used_coordinates = set()  # Track (lat_rounded, lng_rounded) to prevent near-duplicate locations
    must_visit_names = set()
    if preferences.constraints and preferences.constraints.must_visit:
        must_visit_names = set(preferences.constraints.must_visit)
        
        # Check feasibility of must-visit activities
        is_feasible, infeasible_items = check_must_visit_feasibility(
            preferences, activities, must_visit_names
        )
        if not is_feasible:
            # Store infeasible items in itinerary for error reporting
            itinerary.infeasible_must_visits = infeasible_items
            return itinerary
    
    # Build itinerary for each day
    for day_offset in range(trip_days):
        current_date = preferences.start_date + timedelta(days=day_offset)
        day_start = get_day_start_time().replace(
            year=current_date.year,
            month=current_date.month,
            day=current_date.day,
        )
        
        blocks: List[ItineraryBlock] = []
        current_time = day_start
        daily_cost = 0.0
        daily_duration = 0
        previous_activity: Optional[Activity] = None
        
        daily_budget = get_budget_threshold(
            preferences.budget_level.value, preferences.budget_per_day
        )
        
        # Greedy selection for this day
        activities_added = 0
        max_iterations = max_activities * 2  # Safety limit
        categories_used_today: List[str] = []  # Track category order for diversity

        for iteration in range(max_iterations):
            if activities_added >= max_activities:
                break

            # Calculate available time (assume day ends at 10 PM)
            day_end = day_start.replace(hour=22, minute=0)
            available_time = (day_end - current_time).total_seconds() / 60

            if available_time < 30:  # Less than 30 minutes left
                break

            # Score all remaining activities
            best_activity: Optional[Activity] = None
            best_score = -1.0
            best_explanation: Optional[SelectionExplanation] = None

            # Determine category diversity penalty context
            last_category = categories_used_today[-1] if categories_used_today else None
            # For morning slots (before 11am), restaurants are inappropriate
            is_morning = current_time.hour < 11

            day_state = {
                "current_cost": daily_cost,
                "available_time_minutes": int(available_time),
            }

            # Check for must-visit activities that haven't been included yet
            must_visit_remaining = {
                name for name in must_visit_names
                if not any(
                    a.name == name and a.id in used_activity_ids
                    for a in activities
                )
            }

            for activity in activities:
                # Skip if already used (unless it's a must-visit that needs to be included)
                if activity.id in used_activity_ids:
                    if activity.name not in must_visit_names:
                        continue
                    # Allow must-visit to be included even if already used (if needed)
                    if activity.name not in must_visit_remaining:
                        continue

                # Skip near-duplicate locations (within ~100m = 0.001 degrees)
                coord_key = (round(activity.latitude, 3), round(activity.longitude, 3))
                if coord_key in used_coordinates and activity.name not in must_visit_names:
                    continue

                # Skip if in avoid list
                if (
                    preferences.constraints
                    and preferences.constraints.avoid
                    and activity.name in preferences.constraints.avoid
                ):
                    continue

                # Check if activity fits in time window
                if not is_activity_available(activity, current_time):
                    continue

                # Calculate travel time if not first activity
                travel_time = 0
                if previous_activity:
                    distance = haversine_distance(
                        previous_activity.latitude,
                        previous_activity.longitude,
                        activity.latitude,
                        activity.longitude,
                    )
                    travel_time = estimate_travel_time(
                        distance, preferences.travel_mode
                    )

                # Check if we have time for travel + activity
                total_time_needed = travel_time + activity.avg_duration_minutes
                if total_time_needed > available_time:
                    continue

                # Score the activity (with explanation)
                result = score_activity(
                    activity, preferences, day_state, previous_activity, explain=True
                )
                score, explanation = result

                # Category diversity penalty: heavily discourage same category back-to-back
                if activity.name not in must_visit_names:
                    if activity.category == last_category:
                        score -= 40.0  # Strong penalty for immediate repeat category
                    elif activity.category in categories_used_today[-2:]:
                        score -= 15.0  # Mild penalty if same category appeared recently

                    # Morning penalty: food before 11am doesn't make sense
                    if is_morning and activity.category == "food":
                        score -= 25.0

                    # Nightlife hard cutoff: never before 6pm
                    if activity.category == "nightlife" and current_time.hour < 18:
                        score -= 80.0

                if score > best_score:
                    best_score = score
                    best_activity = activity
                    best_explanation = explanation
            
            # If no suitable activity found, break
            if best_activity is None:
                break
            
            # Add travel time if not first activity
            travel_time = 0
            if previous_activity:
                distance = haversine_distance(
                    previous_activity.latitude,
                    previous_activity.longitude,
                    best_activity.latitude,
                    best_activity.longitude,
                )
                travel_time = estimate_travel_time(
                    distance, preferences.travel_mode
                )
                current_time += timedelta(minutes=travel_time)
            
            # Create block for this activity
            start_time = current_time
            end_time = start_time + timedelta(
                minutes=best_activity.avg_duration_minutes
            )
            
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
                tags=list(best_activity.tags) if hasattr(best_activity, 'tags') and isinstance(best_activity.tags, (list, set)) else None,
                description=best_activity.description if hasattr(best_activity, 'description') else None,
                description_zh=best_activity.description_zh if hasattr(best_activity, "description_zh") else None,
                explanation=best_explanation,
            )
            
            block = ItineraryBlock(
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                activity=activity_summary,
                travel_time_from_previous=travel_time if travel_time > 0 else None,
            )
            
            blocks.append(block)
            
            # Update state
            current_time = end_time
            daily_cost += best_activity.base_cost
            daily_duration += best_activity.avg_duration_minutes + travel_time
            previous_activity = best_activity
            used_activity_ids.add(best_activity.id)
            coord_key = (round(best_activity.latitude, 3), round(best_activity.longitude, 3))
            used_coordinates.add(coord_key)
            categories_used_today.append(best_activity.category)
            activities_added += 1
        
        # Create day if we have at least one activity
        if blocks:
            day = ItineraryDay(
                date=current_date,
                total_cost=daily_cost,
                total_duration_minutes=daily_duration,
                blocks=blocks,
            )
            itinerary.days.append(day)
    
    # Calculate summary
    if itinerary.days:
        total_cost = sum(day.total_cost for day in itinerary.days)
        avg_cost_per_day = total_cost / len(itinerary.days)
        
        # Collect unique categories
        categories_covered = set()
        for day in itinerary.days:
            for block in day.blocks:
                categories_covered.add(block.activity.category)
        
        # Determine pace label
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
        
        # Calculate optimization score (0-1)
        # Based on: budget utilization, category coverage, activity ratings
        budget_utilization = min(1.0, total_cost / (daily_budget * len(itinerary.days)))
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
        
        # Confidence score (based on how well preferences were met)
        confidence = 0.7  # Base confidence
        if preferences.preferred_categories:
            matched_categories = len(
                set(categories_covered) & set(cat.value for cat in preferences.preferred_categories)
            )
            confidence += (matched_categories / len(preferences.preferred_categories)) * 0.3
        itinerary.confidence_score = min(1.0, confidence)
    else:
        # No activities scheduled
        itinerary.summary = ItinerarySummary(
            total_cost=0.0,
            avg_cost_per_day=0.0,
            categories_covered=[],
            pace_label="None",
        )
        itinerary.optimization_score = 0.0
        itinerary.confidence_score = 0.0
    
    return itinerary

