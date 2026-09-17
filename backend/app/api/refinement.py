"""Refinement endpoint — hybrid LLM intent parsing + deterministic slot-filling."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Activity, City
from app.api.schemas import RefineRequest, RefineResponse
from app.config import settings
from app.llm.provider import get_chat_provider, LLMRequestError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/refine-itinerary", response_model=RefineResponse)
async def refine_itinerary(
    request: RefineRequest,
    db: Session = Depends(get_db),
):
    """
    Refine an existing itinerary using a natural language request.

    Flow:
    1. LLM parses user's intent into structured RefinementIntent JSON
    2. Backend validates LLM suggestions against real DB activities
    3. If invalid → semantic RAG fallback to find best candidates
    4. Deterministic slot-filler applies changes using scoring.py
    5. Returns updated itinerary + explanation of changes made

    Example requests:
    - "Replace the museum on Day 2 with something for nightlife"
    - "Add a food experience in the evening on Day 1"
    - "Remove the adventure activity from Day 3"
    - "Swap Day 2 morning with something cheaper"
    """
    if not get_chat_provider().api_key:
        raise HTTPException(status_code=503, detail="所选模型服务尚未配置密钥")

    from app.services.refinement_service import parse_refinement_intent, apply_refinement

    preferences = request.preferences
    itinerary = request.itinerary
    user_message = request.user_message

    # Determine city ID for candidate pool
    city_id = preferences.destination_city_id
    if not city_id and preferences.city_segments:
        city_id = preferences.city_segments[0].city_id

    if not city_id:
        raise HTTPException(status_code=400, detail="Could not determine city from preferences")

    # Build candidate pool from DB (compact, for LLM prompt)
    all_activities = db.query(Activity).filter(Activity.city_id == city_id).all()
    candidate_pool = [
        {"name": a.name, "category": a.category, "cost": a.base_cost}
        for a in all_activities
    ]

    # Step 1: Parse intent with LLM
    try:
        intent = await parse_refinement_intent(user_message, itinerary, candidate_pool)
        logger.info(f"Parsed refinement intent: action={intent.action}, day={intent.target_day}, target={intent.target_activity_name}")
    except LLMRequestError as e:
        raise HTTPException(status_code=503, detail={"error_code": e.code, "message": "模型调用失败，请稍后重试"}) from None
    except Exception as e:
        logger.error("LLM intent parsing failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="模型返回的修改指令无效") from None

    # Step 2: Apply refinement deterministically
    try:
        result = await apply_refinement(intent, itinerary, preferences, db, user_message=user_message)
        from app.services.live_poi_service import attach_poi_provenance
        attach_poi_provenance(result.itinerary, all_activities)
        if preferences.use_real_routes:
            from app.services.route_planning import apply_real_routes
            city = db.query(City).filter(City.id == city_id).first()
            result.itinerary.route_report = await apply_real_routes(result.itinerary, preferences, all_activities, city)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refinement application failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to apply refinement: {str(e)}")
