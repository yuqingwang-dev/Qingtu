"""Live domestic route check. Calls AMap and the configured LLM.

Start the API first, then run from backend: python scripts/smoke_routes.py
This is a measured sample, not a general shortest-route/quality benchmark.
"""
import json
import argparse
from datetime import date, datetime, timedelta
from uuid import uuid4

import httpx


HOTEL_QUERIES = {"Beijing": "王府井酒店", "Shanghai": "南京东路酒店", "Hangzhou": "湖滨酒店", "Chengdu": "春熙路酒店"}


def main(city_name="Chengdu", days=3):
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=240, trust_env=False) as client:
        cities = client.get("/api/v1/domestic/cities").json()
        city = next(c for c in cities if c["name"] == city_name)
        assert city["supports_real_routes"]
        search = client.get("/api/v1/domestic/pois", params={"city_id":city["id"], "keywords":HOTEL_QUERIES[city_name], "limit":5})
        search.raise_for_status()
        locations = search.json()["data"]
        assert locations, "No lodging search result"
        hotel = locations[0]
        start = date.today() + timedelta(days=7)
        preferences = {"destination_city_id":city["id"], "start_date":str(start), "end_date":str(start+timedelta(days=days-1)),
            "trip_type":"weekend", "budget_level":"medium", "budget_per_day":300,
            "preferred_categories":["culture","food"], "energy_level":"relaxed", "travel_mode":"public_transport",
            "use_real_routes":True, "daily_start_time":"10:00", "daily_end_time":"20:00", "return_to_lodging":True,
            "lodging":{"name":hotel["name"], "city_id":city["id"], "latitude":hotel["latitude"], "longitude":hotel["longitude"],
                       "provider_poi_id":hotel["identifier"]["provider_poi_id"], "coordinate_system":"GCJ02"}}
        response = client.post("/api/v1/domestic/plan", json=preferences, headers={"X-Session-ID":str(uuid4())})
        assert response.status_code == 200, response.text[:300]
        data = response.json()
        report = data["route_report"]
        assert report and len(data["days"]) == days and report["city_id"] == city["id"]
        identities = [b["activity"]["id"] for day in data["days"] for b in day["blocks"]]
        assert len(identities) == len(set(identities))
        day_results = []
        for day in data["days"]:
            route = day["route_summary"]
            assert day["blocks"] and route["legs"][0]["origin"]["id"] == 0
            assert route["legs"][-1]["destination"]["id"] == 0
            assert datetime.fromisoformat(route["finish_time"]).time().isoformat() <= "20:00:00"
            day_results.append({"date":day["date"], "visits":len(day["blocks"]), "travel_minutes":route["travel_minutes"],
                "return_time":route["finish_time"], "real_legs":sum(l["source"] == "amap" for l in route["legs"]),
                "estimated_legs":route["estimated_legs"], "geometries":sum(len(l["geometry"]) for l in route["legs"])})
        assert sum(d["real_legs"] for d in day_results) > 0
        print(json.dumps({"city":city_name, "hotel":hotel["name"], "days":day_results, "comparison":report,
                          "narrative_error":data["narrative"].get("error_code")},ensure_ascii=False), flush=True)
        print("LIVE_ROUTE_PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", choices=list(HOTEL_QUERIES), default="Chengdu")
    parser.add_argument("--days", type=int, choices=[1,2,3], default=3)
    args = parser.parse_args()
    main(args.city, args.days)
