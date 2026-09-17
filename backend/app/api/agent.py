"""Agent planning endpoint — OpenAI function calling orchestration."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.schemas import AgentPlanRequest, AgentPlanResponse
from app.config import settings
from app.llm.provider import get_chat_provider, LLMRequestError
from app.api.routes import _check_and_increment_generation_limit
from app.core.session import get_session_id
from app.core.auth import get_current_user
from app.db.models import User
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/agent-plan", response_model=AgentPlanResponse)
async def agent_plan(
    request: AgentPlanRequest,
    db: Session = Depends(get_db),
    session_id: str = Depends(get_session_id),
    user: Optional[User] = Depends(get_current_user),
):
    """
    Plan an itinerary using an AI agent with tool calling.

    Unlike /plan-itinerary which runs a fixed pipeline, this endpoint uses an
    OpenAI function-calling agent that autonomously decides how to research
    and plan the trip by calling tools (semantic search, filtering, travel time
    estimation) before invoking the deterministic optimizer.

    The full agent_trace is returned showing every tool the agent called and
    why — making the reasoning process transparent and auditable.

    Note: This endpoint is more expensive (multiple LLM calls) and slower
    than /plan-itinerary. Use it for portfolio demos or when you want to
    show agentic reasoning.
    """
    if not get_chat_provider().api_key:
        raise HTTPException(status_code=503, detail="所选模型服务尚未配置密钥")

    preferences = request.preferences

    city_id = preferences.destination_city_id
    if not city_id and preferences.city_segments:
        city_id = preferences.city_segments[0].city_id

    if not city_id:
        raise HTTPException(status_code=400, detail="destination_city_id or city_segments required")

    from app.services.agent_service import run_agent
    await _check_and_increment_generation_limit(session_id, user)
    try:
        result = await run_agent(preferences, db, request.user_message)
        return result
    except HTTPException:
        raise
    except LLMRequestError as e:
        raise HTTPException(status_code=503, detail={"error_code": e.code, "message": "模型调用失败，请稍后重试"}) from None
    except Exception as e:
        logger.error("Agent planning failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Agent 规划失败，请稍后重试") from None
