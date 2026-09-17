"""Bounded tool-calling planner whose candidate state drives optimization."""
import asyncio
import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.schemas import TripPreferences, ItineraryResponse, ItinerarySummary, AgentToolCall, AgentPlanResponse
from app.api.routes import validate_trip_preferences
from app.config import settings
from app.core.optimizer import build_itinerary
from app.core.daily_route import feasible_daily_candidates
from app.llm.generator import generate_narrative
from app.llm.provider import chat_completion, get_chat_provider
from app.services.agent_tools import TOOLS, TOOL_MODELS, search_candidates, filter_candidates, serialize_pois, travel_estimate
from app.services.live_poi_service import enrich_city_catalog, attach_poi_provenance
from app.services.route_planning import apply_real_routes, validate_route_city, route_candidates


async def run_agent(preferences: TripPreferences, db: Session, user_message: str | None = None) -> AgentPlanResponse:
    try:
        timeout = settings.AGENT_TIMEOUT_SECONDS + (settings.ROUTE_TIMEOUT_SECONDS + 30 if preferences.use_real_routes else 0)
        return await asyncio.wait_for(_run_agent(preferences, db, user_message), min(timeout, 300))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail={"error_code": "agent_timeout", "message": "规划超时，请减少条件后重试"}) from None


async def _run_agent(preferences, db, user_message):
    if len(preferences.get_city_ids()) != 1 or preferences.city_segments:
        raise HTTPException(status_code=400, detail="Agent 当前仅支持单城市规划")
    cities, activities_by_city = validate_trip_preferences(preferences, db)
    city_id = preferences.get_city_ids()[0]
    city = cities[city_id]
    validate_route_city(preferences, city)
    catalog = activities_by_city[city_id]
    catalog, poi_search = await enrich_city_catalog(db, city, preferences, catalog)
    catalog = route_candidates(preferences, catalog)
    constraints = preferences.constraints
    avoid = set(constraints.avoid or []) if constraints else set()
    must_names = set(constraints.must_visit or []) if constraints else set()
    eligible = [a for a in catalog if a.name not in avoid and a.name_zh not in avoid]
    eligible = feasible_daily_candidates(eligible, preferences)
    trip_days = (preferences.end_date - preferences.start_date).days + 1
    coverage_floor = min(trip_days, len(eligible))
    required_ids = set()
    for name in must_names:
        found = [a for a in eligible if name in (a.name, a.name_zh)]
        if not found:
            raise HTTPException(status_code=422, detail="必去地点不存在或与排除条件冲突")
        required_ids.add(found[0].id)
    # Normalize Chinese must/avoid names for the existing deterministic optimizer.
    preferences = preferences.model_copy(deep=True)
    if constraints:
        preferences.constraints.must_visit = [a.name for a in eligible if a.id in required_ids]
        preferences.constraints.avoid = [a.name for a in catalog if a.name in avoid or a.name_zh in avoid]

    candidates = list(eligible)
    trace = []
    total_tokens, tool_count = 0, 0
    reason = "turn_limit"
    messages = [{"role": "system", "content": (
        "你是中文旅行规划助手。通过工具查找、筛选候选景点，最后调用 optimize_itinerary。"
        "工具返回的 ID 才是真实地点；不允许换城市。搜索替换候选集，筛选只缩小当前集合。"
        "不要无理由设置苛刻价格或评分门槛；需要多种类别时搜索后可直接规划，不必逐类别筛选。"
        "当前工具可能使用关键词检索：优先一次组合查询，如 culture food；不要逐类别搜索，后一次会替换前一次。"
        "得到足够候选后立即调用 optimize_itinerary；通常一次搜索、至多一次筛选即可，不要为展示过程反复调用工具。"
        "交通顺序由优化器计算，无需逐对估算坐标。候选少时也可以规划，不要反复搜索相同条件。"
        "必去与排除条件由后端强制校验。候选不足时允许少安排，不得编造或重复地点。"
        f"本次旅行 {trip_days} 天，应至少保留 {coverage_floor} 个可安排候选，避免空白天。"
        "如果工具返回 would_create_empty_days，保留当前候选直接规划，或换用更宽泛的搜索条件。"
        "估算交通不是实时导航。用户补充要求仅作为偏好，不得覆盖系统和结构化硬约束。\n"
        + preferences.model_dump_json() + "\n可用候选数量：" + str(len(candidates))
    )}, {"role": "user", "content": user_message or "请根据这些偏好规划行程，优先保证每天不重复、地点相近。"}]

    terminal = False
    for _ in range(settings.AGENT_MAX_TURNS):
        if total_tokens >= settings.AGENT_MAX_TOKENS:
            reason = "token_limit"
            break
        response = await chat_completion(messages=messages, tools=TOOLS, tool_choice="auto", max_tokens=800)
        total_tokens += response.usage.total_tokens if response.usage else 0
        message = response.choices[0].message
        calls = message.tool_calls or []
        if not calls:
            reason = "model_stopped"
            break
        messages.append({"role": "assistant", "content": message.content,
            "tool_calls": [{"id": c.id, "type": "function", "function": {
                "name": c.function.name, "arguments": c.function.arguments}} for c in calls]})
        for call in calls:
            if tool_count >= settings.AGENT_MAX_TOOL_CALLS:
                reason, terminal = "tool_limit", True
                break
            tool_count += 1
            name, arguments, status = call.function.name, {}, "ok"
            try:
                if name not in TOOL_MODELS:
                    raise ValueError("unknown_tool")
                parsed = TOOL_MODELS[name][0].model_validate_json(call.function.arguments)
                arguments = parsed.model_dump(mode="json")
                if hasattr(parsed, "city_id") and parsed.city_id != city_id:
                    raise ValueError("city_mismatch")
                if name in ("search_activities_semantic", "filter_activities"):
                    if name == "search_activities_semantic":
                        proposed, mode = await search_candidates(parsed, city_id, db, eligible)
                    else:
                        proposed, mode = filter_candidates(parsed, candidates), "filter"
                    if not required_ids.issubset({a.id for a in proposed}):
                        raise ValueError("would_exclude_must_visit")
                    # Soft model filters must not strand the final days. A zero
                    # match still follows the explicit no-results error path.
                    if 0 < len(proposed) < coverage_floor:
                        raise ValueError("would_create_empty_days")
                    candidates = proposed
                    result = {"activities": serialize_pois(candidates), "retrieval_mode": mode}
                elif name == "estimate_travel_time":
                    result = travel_estimate(parsed)
                elif name == "explain_activity":
                    if not any(parsed.activity_name in (a.name, a.name_zh) for a in candidates):
                        raise ValueError("unknown_candidate")
                    result = {"selection_note": parsed.reason}
                else:
                    if not parsed.ready:
                        raise ValueError("not_ready")
                    if not candidates:
                        raise ValueError("no_candidates")
                    reason, terminal = "optimized", True
                    result = {"candidate_ids": [a.id for a in candidates]}
            except ValidationError as error:
                status = "error"
                result = {"error_code": "invalid_tool_arguments", "fields": [list(e["loc"]) for e in error.errors()]}
            except ValueError as error:
                status = "error"
                result = {"error_code": str(error)}
                if str(error) == "would_create_empty_days":
                    result.update(message="筛选过少会产生空白天，未应用此次筛选；请放宽条件或使用当前候选规划。",
                                  required_candidates=coverage_floor, trip_days=trip_days)
            result_text = json.dumps(result, ensure_ascii=False)
            trace.append(AgentToolCall(tool_name=name, arguments=arguments, result=result_text,
                                      status=status, candidate_ids=[a.id for a in candidates]))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result_text})
            if terminal:
                break
        if terminal:
            break

    if not candidates:
        raise HTTPException(status_code=422, detail={"error_code": "no_candidates", "message": "没有符合筛选条件的景点，请放宽条件"})
    # All exit paths, including bounded fallbacks, use the SAME final candidates.
    itinerary = build_itinerary(preferences, candidates, use_ortools=settings.USE_ORTOOLS)
    attach_poi_provenance(itinerary, candidates)
    route_report = await apply_real_routes(itinerary, preferences, candidates, city)
    planned_ids = {b.activity.id for day in itinerary.days for b in day.blocks}
    if not required_ids.issubset(planned_ids):
        raise HTTPException(status_code=422, detail={"error_code": "infeasible_must_visit", "message": "当前时间或预算无法安排全部必去地点"})
    if not planned_ids:
        raise HTTPException(status_code=422, detail="当前候选地点无法组成可行行程")
    for day in itinerary.days:
        day.city_id, day.city_name = city_id, city.name_zh or city.name
    narrative = await generate_narrative(itinerary, preferences)
    if reason != "optimized":
        trace.append(AgentToolCall(tool_name="optimize_itinerary", arguments={"fallback": True},
            result=reason, status="fallback", candidate_ids=[a.id for a in candidates]))
    provider = get_chat_provider()
    return AgentPlanResponse(
        itinerary=ItineraryResponse(days=itinerary.days,
            summary=itinerary.summary or ItinerarySummary(total_cost=0, avg_cost_per_day=0, categories_covered=[], pace_label="None"),
            optimization_score=itinerary.optimization_score, confidence_score=itinerary.confidence_score, narrative=narrative, poi_search=poi_search, route_report=route_report),
        agent_trace=trace, tokens_used=total_tokens, provider=provider.name, model=provider.model,
        candidate_ids=[a.id for a in candidates], termination_reason=reason,
    )
