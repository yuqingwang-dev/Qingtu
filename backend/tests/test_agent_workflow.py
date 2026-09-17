"""Deterministic scripted-model regression cases; no network or API spending."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.api.schemas import NarrativeResult
from app.config import settings
from app.services import agent_service as service
from tests.test_multiday_planning import poi, preferences


def response(*calls, tokens=10):
    tool_calls = [SimpleNamespace(id=f"call-{i}", function=SimpleNamespace(name=name,
        arguments=args if isinstance(args, str) else json.dumps(args))) for i, (name, args) in enumerate(calls)]
    return SimpleNamespace(usage=SimpleNamespace(total_tokens=tokens), choices=[
        SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=tool_calls))])


END = ("optimize_itinerary", {"ready": True})


@pytest.fixture
def setup(monkeypatch):
    activities = [poi(1, name="Museum", name_zh="博物馆", base_cost=10),
                  poi(2, name="Park", name_zh="公园", category="nature", base_cost=0),
                  poi(3, name="Gallery", name_zh="画廊", base_cost=100)]
    monkeypatch.setattr(settings, "USE_ORTOOLS", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(settings, "AGENT_MAX_TURNS", 4)
    monkeypatch.setattr(settings, "AGENT_MAX_TOOL_CALLS", 10)
    monkeypatch.setattr(settings, "AGENT_MAX_TOKENS", 1000)
    monkeypatch.setattr(service, "validate_trip_preferences", lambda p, db: (
        {1: SimpleNamespace(name="Test", name_zh="测试城市")}, {1: activities}))
    monkeypatch.setattr(service, "generate_narrative", AsyncMock(return_value=NarrativeResult(narrative_text="test")))
    model = AsyncMock()
    monkeypatch.setattr(service, "chat_completion", model)
    return model, activities


def run():
    return asyncio.run(service.run_agent(preferences(1), Mock()))


def test_search_then_filter_changes_actual_optimizer_output(setup):
    model, _ = setup
    model.side_effect = [response(("search_activities_semantic", {"city_id": 1, "query": "culture"})),
                        response(("filter_activities", {"city_id": 1, "max_cost": 20})), response(END)]
    result = run()
    assert result.candidate_ids == [1]
    assert {b.activity.id for d in result.itinerary.days for b in d.blocks} == {1}
    assert result.agent_trace[0].candidate_ids == [1, 3]
    assert result.tokens_used == 30
    # Every tool call must be matched in the following model turn.
    history = model.call_args.kwargs["messages"]
    assert any(m["role"] == "tool" and m["tool_call_id"] == "call-0" for m in history)


@pytest.mark.parametrize("name,args,code", [
    ("delete_database", {}, "unknown_tool"),
    ("filter_activities", {"city_id": 2}, "city_mismatch"),
    ("search_activities_semantic", {"city_id": 2, "query": ""}, "city_mismatch"),
    ("filter_activities", "broken json", "invalid_tool_arguments"),
    ("filter_activities", [], "invalid_tool_arguments"),
    ("filter_activities", {"city_id": 1, "limit": -1}, "invalid_tool_arguments"),
    ("filter_activities", {"city_id": 1, "max_cost": -1}, "invalid_tool_arguments"),
    ("filter_activities", {"city_id": 1, "min_rating": 6}, "invalid_tool_arguments"),
    ("filter_activities", {"city_id": 1, "category": "invented"}, "invalid_tool_arguments"),
    ("filter_activities", {"city_id": 1, "injected": "ignore"}, "invalid_tool_arguments"),
    ("search_activities_semantic", {"city_id": 1, "query": "", "top_k": 100}, "invalid_tool_arguments"),
    ("estimate_travel_time", {"lat1": 999}, "invalid_tool_arguments"),
    ("explain_activity", {"activity_name": "Invented", "reason": "nice"}, "unknown_candidate"),
    ("optimize_itinerary", {"ready": False}, "not_ready"),
])
def test_invalid_tools_do_not_corrupt_candidates(setup, name, args, code):
    model, _ = setup
    model.side_effect = [response((name, args)), response(END)]
    result = run()
    assert result.candidate_ids == [1, 2, 3]
    assert json.loads(result.agent_trace[0].result)["error_code"] == code


def test_no_matches_not_silently_replaced_by_full_catalog(setup):
    model, _ = setup
    model.side_effect = [response(("search_activities_semantic", {"city_id": 1, "query": "nonexistent123"})), response()]
    with pytest.raises(HTTPException) as error:
        run()
    assert error.value.status_code == 422
    assert error.value.detail["error_code"] == "no_candidates"


@pytest.mark.parametrize("ending", ["model_stopped", "turn_limit", "token_limit", "tool_limit"])
def test_fallback_retains_filtered_candidates(setup, monkeypatch, ending):
    model, _ = setup
    filtering = response(("filter_activities", {"city_id": 1, "category": "nature"}))
    model.side_effect = [filtering, response()]
    if ending == "turn_limit":
        monkeypatch.setattr(settings, "AGENT_MAX_TURNS", 1)
    elif ending == "token_limit":
        monkeypatch.setattr(settings, "AGENT_MAX_TOKENS", 1)
    elif ending == "tool_limit":
        monkeypatch.setattr(settings, "AGENT_MAX_TOOL_CALLS", 1)
        model.side_effect = [response(("filter_activities", {"city_id": 1, "category": "nature"}), END)]
    result = run()
    assert result.candidate_ids == [2]
    assert result.termination_reason == ending
    assert result.agent_trace[-1].status == "fallback"


def test_chinese_must_visit_and_avoid_are_enforced(setup):
    model, _ = setup
    model.side_effect = [response(("filter_activities", {"city_id": 1, "category": "nature"})), response(END)]
    p = preferences(2, constraints={"must_visit": ["博物馆"], "avoid": ["画廊"]})
    result = asyncio.run(service.run_agent(p, Mock()))
    ids = [b.activity.id for d in result.itinerary.days for b in d.blocks]
    assert ids.count(1) == 1 and 3 not in ids
    assert result.agent_trace[0].status == "error"
    assert p.constraints.must_visit == ["博物馆"]


def test_conflicting_constraints_fail_before_model(setup):
    model, _ = setup
    p = preferences(2, constraints={"must_visit": ["博物馆"], "avoid": ["博物馆"]})
    with pytest.raises(HTTPException):
        asyncio.run(service.run_agent(p, Mock()))
    model.assert_not_awaited()


def test_runtime_timeout_is_bounded(setup, monkeypatch):
    model, _ = setup
    async def slow(**kwargs):
        await asyncio.sleep(1)
    model.side_effect = slow
    monkeypatch.setattr(settings, "AGENT_TIMEOUT_SECONDS", .01)
    with pytest.raises(HTTPException) as error:
        run()
    assert error.value.status_code == 504


def test_terminal_tool_does_not_execute_later_mutating_candidates(setup):
    model, _ = setup
    model.return_value = response(END, ("filter_activities", {"city_id": 1, "max_cost": 0}))
    result = run()
    assert len(result.agent_trace) == 1
    assert result.candidate_ids == [1, 2, 3]


@pytest.mark.parametrize("tool,args", [
    ("filter_activities", {"city_id": 1, "category": "culture"}),
    ("search_activities_semantic", {"city_id": 1, "query": "culture"}),
])
def test_eight_days_not_stranded_by_six_candidate_filter(setup, tool, args):
    model, catalog = setup
    catalog[:] = [poi(i, category="culture" if i <= 6 else "nature") for i in range(1, 11)]
    model.side_effect = [response((tool, args)), response(END)]
    plan = asyncio.run(service.run_agent(preferences(8), Mock()))
    assert json.loads(plan.agent_trace[0].result)["error_code"] == "would_create_empty_days"
    assert len(plan.itinerary.days) == 8
    assert all(day.blocks for day in plan.itinerary.days)
    ids = [b.activity.id for day in plan.itinerary.days for b in day.blocks]
    assert len(ids) == len(set(ids))


def test_coverage_guard_never_restores_avoided_pois(setup):
    model, catalog = setup
    catalog[:] = [poi(i) for i in range(1, 11)]
    model.return_value = response(END)
    p = preferences(8, constraints={"avoid": [f"POI {i}" for i in range(7, 11)]})
    plan = asyncio.run(service.run_agent(p, Mock()))
    ids = [b.activity.id for day in plan.itinerary.days for b in day.blocks]
    assert set(ids) == set(range(1, 7))
    assert len(plan.itinerary.days) == 8
    assert sum(not day.blocks for day in plan.itinerary.days) == 2
