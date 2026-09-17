"""
Hybrid refinement service: LLM parses intent, deterministic optimizer executes it.

Architecture:
    User message
        → LLM (intent parser) → RefinementIntent JSON
        → Backend validates candidates against DB
        → Fallback: RAG semantic search if LLM candidates invalid
        → Deterministic slot-filler (reuses scoring.py)
        → Updated itinerary + explanation
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.api.schemas import (
    TripPreferences,
    ItineraryResponse,
    ItineraryDay,
    ItineraryBlock,
    ActivitySummary,
    Coordinates,
    RefinementIntent,
    RefineResponse,
    VenueAlternative,
    SelectionExplanation,
)
from app.db.models import Activity, City
from app.config import settings
from app.core.scoring import score_activity, haversine_distance, estimate_travel_time, get_budget_threshold

logger = logging.getLogger(__name__)

# Maximum time we allow for a single slot when slot-filling (minutes)
MAX_SLOT_DURATION = 480


async def parse_refinement_intent(
    user_message: str,
    itinerary: ItineraryResponse,
    candidate_pool: list[dict],
) -> RefinementIntent:
    """
    Use LLM to extract structured RefinementIntent from user's natural language request.

    The candidate_pool (activity names + categories from the DB) is included in the prompt
    to reduce hallucination — the model knows what's actually available.
    """
    from app.llm.provider import chat_completion

    # Build compact itinerary text for the prompt
    itinerary_text = _format_itinerary_compact(itinerary)

    # Build candidate pool text (limit to avoid token bloat)
    pool_text = "\n".join(
        f"- {c['name']} ({c['category']}, ${c['cost']:.0f})"
        for c in candidate_pool[:80]
    )

    system_prompt = """You are a travel itinerary editor. Parse the user's refinement request and return ONLY valid JSON.
Do not include any text outside the JSON. The JSON must match this exact schema:
{
  "action": "replace" | "add" | "remove" | "reschedule",
  "target_day": <integer, 1-indexed, or null>,
  "target_activity_name": <string or null>,
  "desired_categories": [<strings from: food, culture, nightlife, nature, shopping, adventure, beaches>],
  "avoid_categories": [<strings>],
  "preferred_time_window": <"morning" | "afternoon" | "evening" | null>,
  "replacement_candidates": [<activity names from the candidate pool below, or empty list>],
  "venue_search_query": <a short Google Places search string capturing exactly what the user wants, e.g. "rooftop bar", "luxury indian restaurant", "jazz club", "art museum", "nightclub lounge". Be specific. Never null.>,
  "explanation": <one sentence explaining what the user wants>
}

Only suggest replacement_candidates from the provided activity pool. If unsure, leave it as [].
"""

    user_prompt = f"""User request: "{user_message}"

Current itinerary:
{itinerary_text}

Available activities in the city (choose replacement_candidates from these):
{pool_text}

Return JSON only."""

    response = await chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,  # Low temperature for structured output
        max_tokens=400,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    return RefinementIntent(
        action=data.get("action", "replace"),
        target_day=data.get("target_day"),
        target_activity_name=data.get("target_activity_name"),
        desired_categories=data.get("desired_categories", []),
        avoid_categories=data.get("avoid_categories", []),
        preferred_time_window=data.get("preferred_time_window"),
        replacement_candidates=data.get("replacement_candidates", []),
        venue_search_query=data.get("venue_search_query"),
        explanation=data.get("explanation", ""),
    )


async def apply_refinement(
    intent: RefinementIntent,
    itinerary: ItineraryResponse,
    preferences: TripPreferences,
    db: Session,
    user_message: str = "",
) -> RefineResponse:
    """
    Apply a parsed RefinementIntent to the itinerary using deterministic logic.

    Steps:
    1. Identify the target day and block
    2. Validate LLM's replacement_candidates against DB
    3. If none valid → RAG semantic fallback
    4. Slot-fill: find best replacement using scoring.py
    5. Return updated itinerary
    """
    city_id = preferences.destination_city_id
    if not city_id and preferences.city_segments:
        # For multi-city, use the target day's city
        day_idx = (intent.target_day or 1) - 1
        if day_idx < len(preferences.city_segments):
            city_id = preferences.city_segments[day_idx].city_id
        else:
            city_id = preferences.city_segments[-1].city_id

    if not city_id:
        return _graceful_error(intent, itinerary, "Could not determine city for refinement.")

    # Get city name and coordinates for Google Places
    city = db.query(City).filter(City.id == city_id).first()
    city_name = city.name if city else ""
    city_lat, city_lon = _get_city_center(city_id, db)

    # Get all activities for this city
    all_activities = db.query(Activity).filter(Activity.city_id == city_id).all()
    activity_by_name = {a.name: a for a in all_activities}

    changes_made = []
    google_venues = []  # Real venues from Google Places
    alternatives: list[VenueAlternative] = []

    # Handle global restructuring requests (e.g. "only 3 activities per day")
    if _is_global_restructure(intent, user_message):
        return _apply_global_trim(intent, itinerary, user_message)

    # Find the target day
    target_day_idx = (intent.target_day or 1) - 1
    if target_day_idx < 0 or target_day_idx >= len(itinerary.days):
        return _graceful_error(intent, itinerary, f"Day {intent.target_day} not found in itinerary.")

    # Work on a mutable copy of days
    days = [day.model_copy(deep=True) for day in itinerary.days]
    target_day = days[target_day_idx]

    if intent.action == "remove":
        result_day, change = _apply_remove(target_day, intent)
        if change:
            days[target_day_idx] = result_day
            changes_made.append(change)
        else:
            return _graceful_error(intent, itinerary, f"Activity '{intent.target_activity_name}' not found on Day {intent.target_day}.")

    elif intent.action in ("replace", "add", "reschedule"):
        # Find the target block (for replace/reschedule)
        target_block = None
        if intent.target_activity_name:
            target_block = next(
                (b for b in target_day.blocks if b.activity.name == intent.target_activity_name),
                None
            )

        # --- Google Places integration ---
        # Always use Google Places when API key is available — LLM provides the exact search query
        from app.services.places_service import fetch_real_venues, venues_to_activity_like
        use_places = bool(settings.GOOGLE_PLACES_API_KEY and intent.venue_search_query)

        if use_places:
            logger.info(f"Fetching real venues from Google Places for: '{user_message}'")
            # Use previous activity coordinates for proximity scoring
            near_lat, near_lon = city_lat, city_lon
            if target_block:
                idx = next((i for i, b in enumerate(target_day.blocks) if b.activity.name == target_block.activity.name), None)
                if idx and idx > 0:
                    prev = target_day.blocks[idx - 1].activity
                    if prev.coordinates:
                        near_lat = prev.coordinates.latitude
                        near_lon = prev.coordinates.longitude
            elif target_day.blocks:
                last = target_day.blocks[-1].activity
                if last.coordinates:
                    near_lat = last.coordinates.latitude
                    near_lon = last.coordinates.longitude

            raw_venues = await fetch_real_venues(
                city_lat=city_lat,
                city_lon=city_lon,
                user_message=user_message,
                desired_categories=intent.desired_categories,
                max_results=5,
                near_lat=near_lat,
                near_lon=near_lon,
                explicit_query=f"{intent.venue_search_query} in {city_name}" if city_name else intent.venue_search_query,
            )
            if raw_venues:
                google_venues = venues_to_activity_like(
                    raw_venues,
                    category=intent.desired_categories[0] if intent.desired_categories else "food",
                    avg_duration_minutes=90,
                )
                # Build alternatives list (all except the top pick)
                alternatives = [
                    VenueAlternative(
                        name=v["name"],
                        category=v["category"],
                        rating=v["rating"],
                        address=v["address"],
                        latitude=v["latitude"],
                        longitude=v["longitude"],
                        cost=v["cost"],
                        price_label=v.get("price_label", ""),
                        place_id=v["place_id"],
                    )
                    for v in google_venues[1:]  # Top pick goes into itinerary, rest are alternatives
                ]

        # Build candidate pool: Google Places first, then DB fallback
        if google_venues:
            # Use top Google Places result as the primary candidate
            best_venue = google_venues[0]
            best = _venue_dict_to_activity_like(best_venue)
            slot_info = _get_slot_info(target_day, target_block, intent)

            if intent.action == "replace" and target_block:
                new_day, change = _apply_replace_from_venue(target_day, target_block, best_venue)
                days[target_day_idx] = new_day
                changes_made.append(change)
            else:
                # "add", "reschedule", or "replace" without a specific target block → append to day
                new_day, change = _apply_add_from_venue(target_day, best_venue)
                days[target_day_idx] = new_day
                changes_made.append(change)
        else:
            # DB-based fallback path
            candidates = _resolve_candidates(intent, all_activities, activity_by_name, preferences)

            if not candidates:
                candidates = await _rag_fallback(intent, city_id, db, all_activities)

            if not candidates:
                return _graceful_error(
                    intent, itinerary,
                    f"No suitable activities found for categories: {intent.desired_categories or ['any']}. "
                    "Try a different request."
                )

            slot_info = _get_slot_info(target_day, target_block, intent)
            already_used = {b.activity.name for b in target_day.blocks}
            if target_block:
                already_used.discard(target_block.activity.name)

            prev_activity_obj = _get_previous_activity_obj(target_day, target_block, activity_by_name)
            best = _pick_best_candidate(candidates, slot_info, preferences, prev_activity_obj, already_used)

            if not best:
                return _graceful_error(
                    intent, itinerary,
                    "No candidates fit within the time/budget constraints for this slot. "
                    "Try a different time of day or relax budget constraints."
                )

            if intent.action == "replace" and target_block:
                new_day, change = _apply_replace(target_day, target_block, best, preferences)
                days[target_day_idx] = new_day
                changes_made.append(change)
            else:
                # "add", "reschedule", or "replace" without a specific target block → append to day
                new_day, change = _apply_add(target_day, best, preferences)
                days[target_day_idx] = new_day
                changes_made.append(change)

    if not changes_made:
        return _graceful_error(intent, itinerary, "No changes could be applied. Please try rephrasing your request.")

    # Rebuild updated itinerary response
    updated_itinerary = ItineraryResponse(
        days=days,
        summary=itinerary.summary,
        optimization_score=itinerary.optimization_score,
        confidence_score=itinerary.confidence_score,
        narrative=itinerary.narrative,
    )

    assistant_message = f"Done! {' '.join(changes_made)}"
    if alternatives:
        alt_names = ", ".join(v.name for v in alternatives[:2])
        assistant_message += f" You could also try: {alt_names}."

    return RefineResponse(
        itinerary=updated_itinerary,
        changes_made=changes_made,
        assistant_message=assistant_message,
        refinement_intent=intent,
        alternatives=alternatives if alternatives else None,
    )


# --- Internal helpers ---

def _format_itinerary_compact(itinerary: ItineraryResponse) -> str:
    lines = []
    for i, day in enumerate(itinerary.days, 1):
        lines.append(f"Day {i} ({day.date}):")
        for block in day.blocks:
            time_str = block.start_time.split("T")[1][:5] if "T" in block.start_time else block.start_time[:5]
            lines.append(f"  {time_str} - {block.activity.name} ({block.activity.category})")
    return "\n".join(lines)


def _apply_remove(day: ItineraryDay, intent: RefinementIntent):
    """Remove the target activity from the day."""
    original_len = len(day.blocks)
    day.blocks = [b for b in day.blocks if b.activity.name != intent.target_activity_name]
    if len(day.blocks) < original_len:
        return day, f"Removed '{intent.target_activity_name}' from Day {intent.target_day}."
    return day, None


def _apply_replace(
    day: ItineraryDay,
    target_block: ItineraryBlock,
    new_activity: Activity,
    preferences: TripPreferences,
) -> tuple[ItineraryDay, str]:
    """Replace target_block with new_activity, preserving the time slot."""
    new_block = ItineraryBlock(
        start_time=target_block.start_time,
        end_time=_add_minutes_to_iso(target_block.start_time, new_activity.avg_duration_minutes),
        activity=ActivitySummary(
            id=new_activity.id,
            name=new_activity.name,
            name_zh=new_activity.name_zh if hasattr(new_activity, "name_zh") else None,
            category=new_activity.category,
            cost=new_activity.base_cost,
            duration=new_activity.avg_duration_minutes,
            rating=new_activity.rating,
            coordinates=Coordinates(latitude=new_activity.latitude, longitude=new_activity.longitude),
            tags=new_activity.tags if hasattr(new_activity, 'tags') else None,
            description=new_activity.description if hasattr(new_activity, 'description') else None,
            description_zh=new_activity.description_zh if hasattr(new_activity, "description_zh") else None,
        ),
        travel_time_from_previous=target_block.travel_time_from_previous,
    )
    day.blocks = [new_block if b.activity.name == target_block.activity.name else b for b in day.blocks]
    change = f"Replaced '{target_block.activity.name}' with '{new_activity.name}' on Day {_day_number_from_date(day)}."
    return day, change


def _apply_add(
    day: ItineraryDay,
    new_activity: Activity,
    preferences: TripPreferences,
) -> tuple[ItineraryDay, str]:
    """Append a new activity to the end of the day."""
    last_end = day.blocks[-1].end_time if day.blocks else f"{day.date}T09:00:00"
    new_block = ItineraryBlock(
        start_time=last_end,
        end_time=_add_minutes_to_iso(last_end, new_activity.avg_duration_minutes),
        activity=ActivitySummary(
            id=new_activity.id,
            name=new_activity.name,
            name_zh=new_activity.name_zh if hasattr(new_activity, "name_zh") else None,
            category=new_activity.category,
            cost=new_activity.base_cost,
            duration=new_activity.avg_duration_minutes,
            rating=new_activity.rating,
            coordinates=Coordinates(latitude=new_activity.latitude, longitude=new_activity.longitude),
            tags=new_activity.tags if hasattr(new_activity, 'tags') else None,
            description=new_activity.description if hasattr(new_activity, 'description') else None,
            description_zh=new_activity.description_zh if hasattr(new_activity, "description_zh") else None,
        ),
        travel_time_from_previous=None,
    )
    day.blocks.append(new_block)
    change = f"Added '{new_activity.name}' to Day {_day_number_from_date(day)}."
    return day, change


def _resolve_candidates(
    intent: RefinementIntent,
    all_activities: list,
    activity_by_name: dict,
    preferences: TripPreferences,
) -> list:
    """
    Build candidate list:
    1. LLM-suggested names that exist in DB (highest priority)
    2. All activities matching desired_categories
    3. All activities if no category filter
    """
    candidates = []

    # Validate LLM suggestions against DB
    for name in intent.replacement_candidates:
        if name in activity_by_name:
            candidates.append(activity_by_name[name])

    if candidates:
        return candidates

    # Category filter
    if intent.desired_categories:
        candidates = [
            a for a in all_activities
            if a.category in intent.desired_categories
            and a.category not in intent.avoid_categories
        ]
    elif intent.avoid_categories:
        candidates = [a for a in all_activities if a.category not in intent.avoid_categories]
    else:
        candidates = list(all_activities)

    # Exclude the activity being replaced
    if intent.target_activity_name:
        candidates = [a for a in candidates if a.name != intent.target_activity_name]

    return candidates


async def _rag_fallback(
    intent: RefinementIntent,
    city_id: int,
    db: Session,
    all_activities: list,
) -> list:
    """Fall back to semantic retrieval if LLM candidates are invalid."""
    if not settings.RAG_ENABLED:
        # Simple category filter fallback
        if intent.desired_categories:
            return [a for a in all_activities if a.category in intent.desired_categories]
        return []

    try:
        from app.services.embedding_service import generate_embedding
        from sqlalchemy import text

        query_text = f"Activities for: {', '.join(intent.desired_categories or ['any'])}. {intent.explanation}"
        embedding = await generate_embedding(query_text)
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

        rows = db.execute(text("""
            SELECT a.id FROM activity_embeddings ae
            JOIN activities a ON ae.activity_id = a.id
            WHERE a.city_id = :city_id AND ae.embedding_vec IS NOT NULL
            ORDER BY ae.embedding_vec <=> CAST(:embedding AS vector) ASC
            LIMIT 20
        """), {"city_id": city_id, "embedding": embedding_str}).fetchall()

        ids = [r[0] for r in rows]
        id_set = set(ids)
        return [a for a in all_activities if a.id in id_set]

    except Exception as e:
        logger.warning(f"RAG fallback failed: {e}")
        if intent.desired_categories:
            return [a for a in all_activities if a.category in intent.desired_categories]
        return []


def _get_slot_info(day: ItineraryDay, target_block: Optional[ItineraryBlock], intent: RefinementIntent) -> dict:
    """Get time/budget info for the slot being filled."""
    if target_block:
        start = _parse_iso_to_dt(target_block.start_time)
        end = _parse_iso_to_dt(target_block.end_time)
        available_minutes = int((end - start).total_seconds() / 60) + 60  # Some slack
    else:
        # Adding at end of day
        if day.blocks:
            last_end = _parse_iso_to_dt(day.blocks[-1].end_time)
        else:
            last_end = datetime.fromisoformat(str(day.date) + "T09:00:00")
        day_end = last_end.replace(hour=22, minute=0)
        available_minutes = max(30, int((day_end - last_end).total_seconds() / 60))

    current_cost = day.total_cost
    return {"available_time_minutes": available_minutes, "current_cost": current_cost}


def _get_previous_activity_obj(
    day: ItineraryDay,
    target_block: Optional[ItineraryBlock],
    activity_by_name: dict,
) -> Optional[Activity]:
    """Get the Activity ORM object for the activity before the target slot."""
    if not target_block or not day.blocks:
        return None
    idx = next((i for i, b in enumerate(day.blocks) if b.activity.name == target_block.activity.name), None)
    if idx is None or idx == 0:
        return None
    prev_name = day.blocks[idx - 1].activity.name
    return activity_by_name.get(prev_name)


def _pick_best_candidate(
    candidates: list,
    slot_info: dict,
    preferences: TripPreferences,
    prev_activity: Optional[Activity],
    already_used: set,
) -> Optional[Activity]:
    """Score candidates and return the best fitting one for this slot."""
    best = None
    best_score = -1.0

    for activity in candidates:
        if activity.name in already_used:
            continue
        if activity.avg_duration_minutes > slot_info["available_time_minutes"]:
            continue

        score = score_activity(activity, preferences, slot_info, prev_activity, explain=False)
        if score > best_score:
            best_score = score
            best = activity

    return best


# Known city coordinates to avoid relying on potentially bad activity data
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "bangalore": (12.9716, 77.5946),
    "bengaluru": (12.9716, 77.5946),
    "london": (51.5074, -0.1278),
    "paris": (48.8566, 2.3522),
    "new york": (40.7128, -74.0060),
    "tokyo": (35.6762, 139.6503),
    "dubai": (25.2048, 55.2708),
    "singapore": (1.3521, 103.8198),
    "barcelona": (41.3851, 2.1734),
    "rome": (41.9028, 12.4964),
    "amsterdam": (52.3676, 4.9041),
    "sydney": (-33.8688, 151.2093),
    "bangkok": (13.7563, 100.5018),
    "istanbul": (41.0082, 28.9784),
    "bali": (-8.4095, 115.1889),
    "cairo": (30.0444, 31.2357),
    "cape town": (-33.9249, 18.4241),
    "toronto": (43.6532, -79.3832),
    "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "berlin": (52.5200, 13.4050),
    "madrid": (40.4168, -3.7038),
    "vienna": (48.2082, 16.3738),
    "prague": (50.0755, 14.4378),
    "lisbon": (38.7223, -9.1393),
    "seoul": (37.5665, 126.9780),
    "beijing": (39.9042, 116.4074),
    "shanghai": (31.2304, 121.4737),
    "mexico city": (19.4326, -99.1332),
    "rio de janeiro": (-22.9068, -43.1729),
    "buenos aires": (-34.6037, -58.3816),
}


def _get_city_center(city_id: int, db: Session) -> tuple[float, float]:
    """Get city coordinates — first tries known cities dict, then activity average."""
    from sqlalchemy import text

    # Look up city name first
    city = db.execute(text("SELECT name FROM cities WHERE id = :id"), {"id": city_id}).fetchone()
    if city:
        name_lower = city[0].lower()
        if name_lower in _CITY_COORDS:
            return _CITY_COORDS[name_lower]
        # Try partial match
        for key, coords in _CITY_COORDS.items():
            if key in name_lower or name_lower in key:
                return coords

    # Fall back to averaging activity coordinates — filter out obvious outliers
    # by only using activities within a reasonable bounding box of the median
    result = db.execute(text("""
        WITH stats AS (
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latitude) AS med_lat,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY longitude) AS med_lon
            FROM activities WHERE city_id = :city_id
        )
        SELECT AVG(latitude), AVG(longitude)
        FROM activities, stats
        WHERE city_id = :city_id
          AND ABS(latitude - med_lat) < 3
          AND ABS(longitude - med_lon) < 3
    """), {"city_id": city_id}).fetchone()

    if result and result[0]:
        return float(result[0]), float(result[1])
    return 51.5074, -0.1278  # Default to London


def _venue_dict_to_activity_like(venue: dict):
    """Wrap a Google Places venue dict into an object that looks like an Activity ORM object."""
    class VenueLike:
        pass
    v = VenueLike()
    v.id = -1  # Not a real DB ID
    v.name = venue["name"]
    v.category = venue["category"]
    v.base_cost = venue["cost"]
    v.avg_duration_minutes = venue["duration"]
    v.rating = venue["rating"]
    v.latitude = venue["latitude"]
    v.longitude = venue["longitude"]
    v.tags = None
    v.description = venue.get("address", "")
    v.open_time = None
    v.close_time = None
    return v


def _apply_replace_from_venue(
    day: ItineraryDay,
    target_block: ItineraryBlock,
    venue: dict,
) -> tuple[ItineraryDay, str]:
    """Replace target_block with a real Google Places venue."""
    new_block = ItineraryBlock(
        start_time=target_block.start_time,
        end_time=_add_minutes_to_iso(target_block.start_time, venue.get("duration", 90)),
        activity=ActivitySummary(
            id=-1,
            name=venue["name"],
            name_zh=None,
            category=venue["category"],
            cost=venue["cost"],
            duration=venue.get("duration", 90),
            rating=venue["rating"],
            coordinates=Coordinates(latitude=venue["latitude"], longitude=venue["longitude"]),
            description=venue.get("address", ""),
            description_zh=None,
        ),
        travel_time_from_previous=target_block.travel_time_from_previous,
    )
    day.blocks = [new_block if b.activity.name == target_block.activity.name else b for b in day.blocks]
    price_label = f" ({venue['price_label']})" if venue.get("price_label") else ""
    change = f"Replaced '{target_block.activity.name}' with '{venue['name']}'{price_label}, rated ⭐{venue['rating']} on Google."
    return day, change


def _apply_add_from_venue(
    day: ItineraryDay,
    venue: dict,
) -> tuple[ItineraryDay, str]:
    """Append a real Google Places venue to the day."""
    last_end = day.blocks[-1].end_time if day.blocks else f"{day.date}T09:00:00"
    new_block = ItineraryBlock(
        start_time=last_end,
        end_time=_add_minutes_to_iso(last_end, venue.get("duration", 90)),
        activity=ActivitySummary(
            id=-1,
            name=venue["name"],
            name_zh=None,
            category=venue["category"],
            cost=venue["cost"],
            duration=venue.get("duration", 90),
            rating=venue["rating"],
            coordinates=Coordinates(latitude=venue["latitude"], longitude=venue["longitude"]),
            description=venue.get("address", ""),
            description_zh=None,
        ),
        travel_time_from_previous=None,
    )
    day.blocks.append(new_block)
    price_label = f" ({venue['price_label']})" if venue.get("price_label") else ""
    change = f"Added '{venue['name']}'{price_label}, rated ⭐{venue['rating']} on Google."
    return day, change


def _graceful_error(intent: RefinementIntent, itinerary: ItineraryResponse, message: str) -> RefineResponse:
    """Return original itinerary unchanged with an explanation."""
    return RefineResponse(
        itinerary=itinerary,
        changes_made=[],
        assistant_message=message,
        refinement_intent=intent,
    )


def _is_global_restructure(intent: RefinementIntent, user_message: str) -> bool:
    """Detect requests that apply to all days, not a specific activity."""
    msg = user_message.lower()
    global_keywords = ["every day", "each day", "all days", "per day", "activities a day", "activities per day", "activities each day"]
    return any(kw in msg for kw in global_keywords)


def _apply_global_trim(intent: RefinementIntent, itinerary: ItineraryResponse, user_message: str) -> "RefineResponse":
    """Trim or pad all days to match a requested activity count."""
    import re
    msg = user_message.lower()
    # Extract the number from the message e.g. "3 activities per day"
    match = re.search(r'(\d+)\s*activit', msg)
    target_count = int(match.group(1)) if match else 3
    target_count = max(1, min(target_count, 8))  # Clamp 1-8

    days = [day.model_copy(deep=True) for day in itinerary.days]
    changes = []
    for day in days:
        original = len(day.blocks)
        if original > target_count:
            # Keep the best-rated activities, preserve time order
            kept = sorted(day.blocks, key=lambda b: b.activity.rating, reverse=True)[:target_count]
            kept_names = {b.activity.name for b in kept}
            day.blocks = [b for b in day.blocks if b.activity.name in kept_names]
            removed = original - len(day.blocks)
            changes.append(f"Day {day.date}: trimmed from {original} to {len(day.blocks)} activities (removed {removed} lowest-rated).")

    if not changes:
        return _graceful_error(intent, itinerary, f"All days already have {target_count} or fewer activities.")

    updated = ItineraryResponse(
        days=days,
        summary=itinerary.summary,
        optimization_score=itinerary.optimization_score,
        confidence_score=itinerary.confidence_score,
        narrative=itinerary.narrative,
    )
    return RefineResponse(
        itinerary=updated,
        changes_made=changes,
        assistant_message=f"Done! Trimmed all days to {target_count} activities, keeping the highest-rated ones.",
        refinement_intent=intent,
    )


def _add_minutes_to_iso(iso_str: str, minutes: int) -> str:
    dt = _parse_iso_to_dt(iso_str)
    return (dt + timedelta(minutes=minutes)).isoformat()


def _parse_iso_to_dt(iso_str: str) -> datetime:
    # Handle both "2026-03-12T10:00:00" and "2026-03-12T10:00:00+00:00"
    try:
        return datetime.fromisoformat(iso_str)
    except ValueError:
        return datetime.strptime(iso_str[:19], "%Y-%m-%dT%H:%M:%S")


def _day_number_from_date(day: ItineraryDay) -> str:
    return str(day.date)
