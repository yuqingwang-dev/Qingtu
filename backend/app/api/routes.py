"""API route definitions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, timedelta, datetime
import secrets
import json
from app.db.session import get_db
from app.db.models import City, Activity, SavedItinerary, User
from app.api.schemas import (
    TripPreferences,
    ItineraryResponse,
    CityResponse,
    ActivitySummary,
    Coordinates,
    SaveItineraryRequest,
    SavedItineraryResponse,
    ItineraryListItem,
    UpdateItineraryRequest,
)
from app.core.session import get_session_id, require_session_id
from app.core.auth import get_current_user
from app.api.errors import (
    CityNotFoundError,
    NoActivitiesError,
    InvalidDateRangeError,
    InvalidBudgetError,
    ValidationError,
    InfeasibleConstraintsError,
)
from app.core.optimizer import build_itinerary
from app.llm.generator import generate_narrative
from app.api.pdf_export import generate_pdf
from app.config import settings
from fastapi.responses import Response

router = APIRouter()


@router.get("/cities", response_model=List[CityResponse])
async def get_cities(db: Session = Depends(get_db)):
    """Get list of supported cities."""
    cities = db.query(City).order_by(City.is_domestic.desc(), City.name_zh.asc().nullslast(), City.name.asc()).all()
    return cities


@router.get("/activities")
async def get_activities(city_id: int, db: Session = Depends(get_db)):
    """Get activities for a specific city (for testing/debug)."""
    activities = db.query(Activity).filter(Activity.city_id == city_id).all()
    return {
        "activities": [
            {
                "id": a.id,
                "name": a.name,
                "name_zh": a.name_zh,
                "category": a.category,
                "base_cost": a.base_cost,
                "avg_duration_minutes": a.avg_duration_minutes,
                "rating": a.rating,
                "latitude": a.latitude,
                "longitude": a.longitude,
                "description": a.description,
                "description_zh": a.description_zh,
            }
            for a in activities
        ]
    }


@router.post("/plan-itinerary/pdf")
async def export_itinerary_pdf(
    itinerary: ItineraryResponse,
):
    """Export itinerary as PDF."""
    pdf_buffer = generate_pdf(itinerary)
    return Response(
        content=pdf_buffer.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=itinerary.pdf"}
    )


# Saved Itinerary Routes
@router.post("/itineraries", response_model=SavedItineraryResponse)
async def save_itinerary(
    request: SaveItineraryRequest,
    session_id: str = Depends(get_session_id),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Save a generated itinerary."""
    # Convert schemas to JSON for storage
    trip_data = json.loads(request.trip_preferences.model_dump_json())
    itinerary_data = json.loads(request.itinerary.model_dump_json())
    city_ids = request.trip_preferences.get_city_ids()

    # Create new saved itinerary
    saved = SavedItinerary(
        session_id=session_id,
        user_id=user.id if user else None,  # Link to user if authenticated
        city_ids=city_ids,
        trip_data=trip_data,
        itinerary_data=itinerary_data,
        is_public=request.is_public,
    )

    db.add(saved)
    db.commit()
    db.refresh(saved)

    # Build response
    return SavedItineraryResponse(
        id=saved.id,
        session_id=saved.session_id,
        created_at=saved.created_at.isoformat(),
        updated_at=saved.updated_at.isoformat(),
        is_public=saved.is_public,
        share_token=saved.share_token,
        share_url=f"/share/{saved.share_token}" if saved.share_token else None,
        view_count=saved.view_count,
        trip_preferences=request.trip_preferences,
        itinerary=request.itinerary,
    )


@router.get("/itineraries", response_model=List[ItineraryListItem])
async def list_itineraries(
    session_id: str = Depends(require_session_id),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Get list of user's saved itineraries."""
    # Query for itineraries - if user is authenticated, get both user's and session's itineraries
    if user:
        saved_items = db.query(SavedItinerary).filter(
            (SavedItinerary.user_id == user.id) | (SavedItinerary.session_id == session_id)
        ).order_by(SavedItinerary.created_at.desc()).all()
    else:
        saved_items = db.query(SavedItinerary).filter(
            SavedItinerary.session_id == session_id
        ).order_by(SavedItinerary.created_at.desc()).all()

    results = []
    for item in saved_items:
        # Extract city names from trip_data
        city_ids = item.city_ids
        cities = db.query(City).filter(City.id.in_(city_ids)).all()
        city_names = [c.name for c in cities]

        # Extract summary info from itinerary_data
        trip_data = item.trip_data
        itinerary_data = item.itinerary_data

        results.append(ItineraryListItem(
            id=item.id,
            created_at=item.created_at.isoformat(),
            city_names=city_names,
            start_date=trip_data.get("start_date", ""),
            end_date=trip_data.get("end_date", ""),
            total_cost=itinerary_data.get("summary", {}).get("total_cost", 0.0),
            days_count=len(itinerary_data.get("days", [])),
            is_public=item.is_public,
            view_count=item.view_count,
        ))

    return results


@router.get("/itineraries/{itinerary_id}", response_model=SavedItineraryResponse)
async def get_itinerary(
    itinerary_id: str,
    session_id: str = Depends(require_session_id),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Get a specific saved itinerary."""
    # Verify ownership - check both user_id and session_id
    if user:
        saved = db.query(SavedItinerary).filter(
            SavedItinerary.id == itinerary_id,
            (SavedItinerary.user_id == user.id) | (SavedItinerary.session_id == session_id)
        ).first()
    else:
        saved = db.query(SavedItinerary).filter(
            SavedItinerary.id == itinerary_id,
            SavedItinerary.session_id == session_id
        ).first()

    if not saved:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    # Parse JSON data back to Pydantic models
    trip_preferences = TripPreferences(**saved.trip_data)
    itinerary = ItineraryResponse(**saved.itinerary_data)

    return SavedItineraryResponse(
        id=saved.id,
        session_id=saved.session_id,
        created_at=saved.created_at.isoformat(),
        updated_at=saved.updated_at.isoformat(),
        is_public=saved.is_public,
        share_token=saved.share_token,
        share_url=f"/share/{saved.share_token}" if saved.share_token else None,
        view_count=saved.view_count,
        trip_preferences=trip_preferences,
        itinerary=itinerary,
    )


@router.put("/itineraries/{itinerary_id}", response_model=SavedItineraryResponse)
async def update_itinerary(
    itinerary_id: str,
    request: UpdateItineraryRequest,
    session_id: str = Depends(require_session_id),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Update an existing saved itinerary."""
    # Verify ownership
    if user:
        saved = db.query(SavedItinerary).filter(
            SavedItinerary.id == itinerary_id,
            (SavedItinerary.user_id == user.id) | (SavedItinerary.session_id == session_id)
        ).first()
    else:
        saved = db.query(SavedItinerary).filter(
            SavedItinerary.id == itinerary_id,
            SavedItinerary.session_id == session_id
        ).first()

    if not saved:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    # Update fields if provided
    if request.is_public is not None:
        saved.is_public = request.is_public

    if request.trip_preferences:
        saved.trip_data = json.loads(request.trip_preferences.model_dump_json())
        saved.city_ids = request.trip_preferences.get_city_ids()

    if request.itinerary:
        saved.itinerary_data = json.loads(request.itinerary.model_dump_json())

    db.commit()
    db.refresh(saved)

    # Parse for response
    trip_preferences = TripPreferences(**saved.trip_data)
    itinerary = ItineraryResponse(**saved.itinerary_data)

    return SavedItineraryResponse(
        id=saved.id,
        session_id=saved.session_id,
        created_at=saved.created_at.isoformat(),
        updated_at=saved.updated_at.isoformat(),
        is_public=saved.is_public,
        share_token=saved.share_token,
        share_url=f"/share/{saved.share_token}" if saved.share_token else None,
        view_count=saved.view_count,
        trip_preferences=trip_preferences,
        itinerary=itinerary,
    )


@router.delete("/itineraries/{itinerary_id}")
async def delete_itinerary(
    itinerary_id: str,
    session_id: str = Depends(require_session_id),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Delete a saved itinerary."""
    # Verify ownership
    if user:
        saved = db.query(SavedItinerary).filter(
            SavedItinerary.id == itinerary_id,
            (SavedItinerary.user_id == user.id) | (SavedItinerary.session_id == session_id)
        ).first()
    else:
        saved = db.query(SavedItinerary).filter(
            SavedItinerary.id == itinerary_id,
            SavedItinerary.session_id == session_id
        ).first()

    if not saved:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    db.delete(saved)
    db.commit()

    return {"message": "Itinerary deleted successfully"}


@router.post("/itineraries/{itinerary_id}/share")
async def share_itinerary(
    itinerary_id: str,
    session_id: str = Depends(require_session_id),
    db: Session = Depends(get_db),
):
    """Generate a public share link for an itinerary."""
    saved = db.query(SavedItinerary).filter(
        SavedItinerary.id == itinerary_id,
        SavedItinerary.session_id == session_id
    ).first()

    if not saved:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    # Generate share token if not exists
    if not saved.share_token:
        saved.share_token = secrets.token_urlsafe(32)

    # Make it public
    saved.is_public = True

    db.commit()
    db.refresh(saved)

    return {
        "share_token": saved.share_token,
        "share_url": f"/share/{saved.share_token}",
        "message": "Itinerary is now public"
    }


@router.get("/share/{share_token}", response_model=SavedItineraryResponse)
async def get_shared_itinerary(
    share_token: str,
    db: Session = Depends(get_db),
):
    """Get a publicly shared itinerary (no authentication required)."""
    saved = db.query(SavedItinerary).filter(
        SavedItinerary.share_token == share_token,
        SavedItinerary.is_public == True
    ).first()

    if not saved:
        raise HTTPException(status_code=404, detail="Shared itinerary not found")

    # Increment view count
    saved.view_count += 1
    db.commit()
    db.refresh(saved)

    # Parse JSON data
    trip_preferences = TripPreferences(**saved.trip_data)
    itinerary = ItineraryResponse(**saved.itinerary_data)

    return SavedItineraryResponse(
        id=saved.id,
        session_id=saved.session_id,  # Still included but frontend can hide
        created_at=saved.created_at.isoformat(),
        updated_at=saved.updated_at.isoformat(),
        is_public=saved.is_public,
        share_token=saved.share_token,
        share_url=f"/share/{saved.share_token}",
        view_count=saved.view_count,
        trip_preferences=trip_preferences,
        itinerary=itinerary,
    )


def validate_trip_preferences(preferences: TripPreferences, db: Session):
    """Validate trip preferences and return city information."""
    # Validate date range
    if preferences.end_date < preferences.start_date:
        raise InvalidDateRangeError("End date must not be before start date")
    
    # Validate trip length (max 30 days for v2)
    trip_days = (preferences.end_date - preferences.start_date).days + 1
    if trip_days > 30:
        raise ValidationError(
            f"Trip duration cannot exceed 30 days (got {trip_days} days)",
            field="end_date"
        )
    if trip_days < 1:
        raise InvalidDateRangeError("Trip must be at least 1 day")
    
    # Validate budget
    if preferences.budget_per_day is not None and preferences.budget_per_day < 0:
        raise InvalidBudgetError("Budget per day must be non-negative")
    
    # Validate city/city segments
    try:
        city_ids = preferences.get_city_ids()
    except ValueError as e:
        raise ValidationError(str(e), field="destination_city_id")
    
    if not city_ids:
        raise ValidationError(
            "Either destination_city_id or city_segments must be provided",
            field="destination_city_id"
        )
    
    # Validate all cities exist
    cities = {}
    for city_id in city_ids:
        city = db.query(City).filter(City.id == city_id).first()
        if not city:
            raise CityNotFoundError(city_id)
        cities[city_id] = city
    
    # Validate activities exist for all cities
    all_activities = {}
    for city_id in city_ids:
        activities = db.query(Activity).filter(Activity.city_id == city_id).all()
        if not activities:
            raise NoActivitiesError(city_id)
        all_activities[city_id] = activities
    
    return cities, all_activities


ANON_GENERATION_LIMIT = 3
AUTH_GENERATION_LIMIT = 5
GENERATION_WINDOW_SECONDS = 24 * 60 * 60  # 24-hour rolling window


def _raise_limit_error(limit: int, user: Optional[User]) -> None:
    if user:
        raise HTTPException(
            status_code=429,
            detail=f"You have reached the limit of {limit} itinerary generations per day. "
                   "Please try again tomorrow.",
        )
    raise HTTPException(
        status_code=429,
        detail=f"Guests can only generate {limit} itineraries per day. "
               "Sign in to get up to 5 generations per day.",
    )


async def _check_and_increment_generation_limit(
    session_id: str,
    user: Optional[User],
) -> None:
    """
    Enforce per-session/per-user generation limits using Redis counters
    (24-hour rolling window). If Redis is unavailable, allows the request
    through (fail-open) so users are never blocked by infrastructure issues.
    Raises HTTP 429 only when the limit is confirmed exceeded in Redis.
    """
    if not settings.GENERATION_LIMIT_ENABLED:
        return

    from app.core.cache import cache

    if user:
        limit = AUTH_GENERATION_LIMIT
        redis_key = f"gen_count:user:{user.id}"
    else:
        limit = ANON_GENERATION_LIMIT
        redis_key = f"gen_count:session:{session_id}"

    # Attempt lazy reconnect if Redis went down and came back up
    if not cache._redis:
        try:
            await cache.connect()
        except Exception:
            pass  # Still unavailable — fail open

    if not cache._redis:
        return  # Redis unavailable: fail open, allow the request

    try:
        count = await cache._redis.incr(redis_key)
        if count == 1:
            await cache._redis.expire(redis_key, GENERATION_WINDOW_SECONDS)
        if count > limit:
            await cache._redis.decr(redis_key)  # keep counter accurate
            _raise_limit_error(limit, user)
    except HTTPException:
        raise
    except Exception:
        return  # Redis error: fail open, allow the request


@router.post("/plan-itinerary", response_model=ItineraryResponse)
async def plan_itinerary(
    preferences: TripPreferences,
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
    user: Optional[User] = Depends(get_current_user),
):
    """Generate a personalized travel itinerary."""
    # Enforce generation limits before any expensive LLM/RAG calls
    await _check_and_increment_generation_limit(session_id, user)

    # Validate preferences
    cities, all_activities = validate_trip_preferences(preferences, db)
    
    # For v2: Support both single-city (backward compatible) and multi-city
    # For now, we'll handle single city, multi-city will be added with OR-Tools
    city_ids = preferences.get_city_ids()
    
    if len(city_ids) == 1:
        # Single city (backward compatible)
        city_id = city_ids[0]

        # RAG: semantic retrieval if enabled, else full SQL
        if settings.RAG_ENABLED:
            try:
                from app.services.retrieval_service import retrieve_activities_semantic
                activities = await retrieve_activities_semantic(preferences, city_id, db)
            except Exception as rag_err:
                import logging
                logging.getLogger(__name__).warning(f"RAG failed, using SQL fallback: {rag_err}")
                activities = all_activities[city_id]
        else:
            activities = all_activities[city_id]

        from app.services.live_poi_service import enrich_city_catalog, attach_poi_provenance
        from app.services.route_planning import apply_real_routes, validate_route_city, route_candidates
        validate_route_city(preferences, cities[city_id])
        activities, poi_search = await enrich_city_catalog(db, cities[city_id], preferences, activities)
        activities = route_candidates(preferences, activities)

        # Build itinerary using optimizer
        itinerary = build_itinerary(preferences, activities, use_ortools=settings.USE_ORTOOLS)
        attach_poi_provenance(itinerary, activities)
        route_report = await apply_real_routes(itinerary, preferences, activities, cities[city_id])
        
        # Check for infeasible must-visit activities
        if hasattr(itinerary, 'infeasible_must_visits') and itinerary.infeasible_must_visits:
            raise InfeasibleConstraintsError(
                "Some must-visit activities could not be included in the itinerary",
                infeasible_items=itinerary.infeasible_must_visits
            )
        
        # Generate narrative using LLM
        narrative = await generate_narrative(itinerary, preferences)
        
        # Combine into response
        return ItineraryResponse(
            days=itinerary.days,
            summary=itinerary.summary,
            optimization_score=itinerary.optimization_score,
            confidence_score=itinerary.confidence_score,
            narrative=narrative,
            poi_search=poi_search,
            route_report=route_report,
        )
    else:
        # Multi-city (will be implemented with OR-Tools)
        # For now, return error indicating it's coming soon
        raise ValidationError(
            "Multi-city trips are coming in v2.1. Please use single city for now.",
            field="city_segments"
        )

