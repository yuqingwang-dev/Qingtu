import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.schemas import ItineraryResponse, TripPreferences
from app.config import settings
from app.core.optimizer import build_itinerary
from app.core.session import get_session_id
from app.db.session import get_db
from app.llm.generator import generate_narrative

logger = logging.getLogger(__name__)

router = APIRouter()


async def stream_itinerary_generation(
    preferences: TripPreferences,
    session_id: str,
    db: Session
):
    """
    Stream itinerary generation progress as Server-Sent Events.

    Yields progress updates:
    - Fetching activities
    - Running optimization
    - Generating narrative
    - Final result
    """
    try:
        yield _sse({"step": "fetching", "message": "Fetching activities...", "progress": 20})

        # Import here to avoid a module-level circular import: routes imports this router in main.py.
        from app.api.routes import validate_trip_preferences

        cities, all_activities = validate_trip_preferences(preferences, db)
        city_ids = preferences.get_city_ids()
        if len(city_ids) != 1:
            yield _sse({
                "step": "error",
                "message": "Streaming currently supports single-city trips only.",
            })
            return

        city_id = city_ids[0]
        city = cities[city_id]
        yield _sse({
            "step": "city_found",
            "message": f"Planning trip to {city.name}",
            "progress": 30,
        })

        activities = all_activities[city_id]
        if settings.RAG_ENABLED:
            try:
                from app.services.retrieval_service import retrieve_activities_semantic

                activities = await retrieve_activities_semantic(preferences, city_id, db)
            except Exception as rag_err:
                logger.warning("RAG failed in streaming endpoint, using SQL fallback: %s", rag_err)

        yield _sse({
            "step": "activities",
            "message": f"Found {len(activities)} activities",
            "progress": 40,
        })

        # Step 2: Run optimizer
        yield _sse({
            "step": "optimizing",
            "message": "Optimizing your itinerary...",
            "progress": 50,
        })

        itinerary = build_itinerary(preferences, activities, use_ortools=settings.USE_ORTOOLS)
        yield _sse({"step": "optimized", "message": "Itinerary optimized!", "progress": 70})

        # Step 3: Generate narrative (if using AI)
        yield _sse({
            "step": "narrative",
            "message": "Generating travel narrative...",
            "progress": 80,
        })

        narrative = await generate_narrative(itinerary, preferences)
        yield _sse({"step": "narrative_done", "message": "Narrative ready!", "progress": 90})

        # Step 4: Send final result
        result = ItineraryResponse(
            days=itinerary.days,
            summary=itinerary.summary,
            optimization_score=itinerary.optimization_score,
            confidence_score=itinerary.confidence_score,
            narrative=narrative,
        )
        yield _sse({
            "step": "complete",
            "message": "Itinerary generated!",
            "progress": 100,
            "result": json.loads(result.model_dump_json()),
        })

    except Exception as e:
        logger.exception("Error streaming itinerary")
        yield _sse({"step": "error", "message": str(e)})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/plan-itinerary/stream")
async def stream_plan_itinerary(
    preferences: TripPreferences,
    session_id: str = Depends(get_session_id),
    db: Session = Depends(get_db),
):
    """
    Stream itinerary generation with real-time progress updates.

    Returns Server-Sent Events (SSE) with progress information.
    """
    return StreamingResponse(
        stream_itinerary_generation(preferences, session_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
