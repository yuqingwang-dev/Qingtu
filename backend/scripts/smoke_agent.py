"""Live smoke check. Uses running API and real model calls (provider charges apply).

Run from backend: .venv\Scripts\python.exe scripts/smoke_agent.py
Prints only a compact report, never reads/prints credentials.
"""
import json
from datetime import date, timedelta
from uuid import uuid4

import httpx


def main():
    report = []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=110, trust_env=False) as client:
        cities_response = client.get("/api/v1/cities")
        cities_response.raise_for_status()
        cities = cities_response.json()
        for name in ("Chengdu", "Paris"):
            city = next(c for c in cities if c["name"] == name)
            start = date.today() + timedelta(days=7)
            preferences = dict(destination_city_id=city["id"], start_date=str(start),
                end_date=str(start + timedelta(days=2)), trip_type="weekend", budget_level="medium",
                budget_per_day=300, preferred_categories=["culture", "food"], energy_level="moderate", travel_mode="mixed")
            response = client.post("/api/v1/agent-plan", headers={"X-Session-ID": str(uuid4())},
                json={"preferences": preferences, "user_message": "优先文化与美食，先查询候选景点再安排行程，不需要购物。"})
            if response.status_code != 200:
                raise RuntimeError(f"{name}: HTTP {response.status_code}: {response.text[:300]}")
            data = response.json()
            ids = [b["activity"]["id"] for d in data["itinerary"]["days"] for b in d["blocks"]]
            assert ids and len(ids) == len(set(ids)), "Duplicate or empty itinerary"
            assert set(ids).issubset(data["candidate_ids"]), "Optimizer escaped candidate state"
            assert len(data["itinerary"]["days"]) == 3
            assert any(t["tool_name"] == "search_activities_semantic" and t["status"] == "ok" for t in data["agent_trace"])
            item = {"city": name, "status": response.status_code, "provider": data["provider"],
                "termination": data["termination_reason"], "candidate_count": len(data["candidate_ids"]),
                "unique_visits": len(ids), "decision_tokens": data["tokens_used"],
                "tools": [t["tool_name"] for t in data["agent_trace"]],
                "narrative_source": data["itinerary"]["narrative"].get("source")}
            report.append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
        # Existing refinement entry point must accept the same selected provider.
        refinement = client.post("/api/v1/refine-itinerary", json={
            "preferences": preferences, "itinerary": data["itinerary"],
            "user_message": "删除第一天的第一个景点，其他安排保持不变。"})
        assert refinement.status_code == 200, refinement.text[:300]
        print(json.dumps({"refinement_status": refinement.status_code,
                          "changes": len(refinement.json()["changes_made"])}), flush=True)
    print("LIVE_SMOKE_PASS")


if __name__ == "__main__":
    main()
