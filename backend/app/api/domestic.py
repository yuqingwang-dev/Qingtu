"""Domestic travel planning endpoints for the Phase 1 China-first MVP."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes import _check_and_increment_generation_limit, validate_trip_preferences
from app.api.schemas import CityResponse, ItineraryResponse, TripPreferences
from app.core.auth import get_current_user
from app.core.session import get_session_id
from app.core.optimizer import build_itinerary
from app.db.models import City, User
from app.db.session import get_db
from app.llm.generator import generate_narrative
from app.config import settings
from app.services.live_poi_service import enrich_city_catalog, attach_poi_provenance
from app.services.route_planning import apply_real_routes, validate_route_city, route_candidates

router = APIRouter()


@router.get("/domestic/cities", response_model=List[CityResponse])
async def get_domestic_cities(db: Session = Depends(get_db)):
    """Return only domestic cities for the China-first planner."""
    return (
        db.query(City)
        .filter(City.is_domestic.is_(True))
        .order_by(City.name_zh.asc().nullslast(), City.name.asc())
        .all()
    )


@router.post("/domestic/plan", response_model=ItineraryResponse)
async def plan_domestic_itinerary(
    preferences: TripPreferences,
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
    user: Optional[User] = Depends(get_current_user),
):
    """Generate an itinerary restricted to domestic cities."""
    await _check_and_increment_generation_limit(session_id, user)

    cities, all_activities = validate_trip_preferences(preferences, db)
    city_ids = preferences.get_city_ids()

    if len(city_ids) != 1:
        raise HTTPException(status_code=400, detail="Domestic planner currently supports single-city trips only.")

    city = cities[city_ids[0]]
    if not city.is_domestic:
        raise HTTPException(status_code=400, detail="Please select a supported domestic city.")
    validate_route_city(preferences, city)

    city_id = city_ids[0]
    activities = all_activities[city_id]
    activities, poi_search = await enrich_city_catalog(db, city, preferences, activities)
    activities = route_candidates(preferences, activities)

    itinerary = build_itinerary(preferences, activities, use_ortools=settings.USE_ORTOOLS)
    attach_poi_provenance(itinerary, activities)
    route_report = await apply_real_routes(itinerary, preferences, activities, city)
    city_display_name = city.name_zh or city.name
    for day in itinerary.days:
        day.city_id = city.id
        day.city_name = city_display_name

    narrative = await generate_narrative(itinerary, preferences)

    return ItineraryResponse(
        days=itinerary.days,
        summary=itinerary.summary,
        optimization_score=itinerary.optimization_score,
        confidence_score=itinerary.confidence_score,
        narrative=narrative,
        poi_search=poi_search,
        route_report=route_report,
    )
