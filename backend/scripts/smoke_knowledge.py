"""Verify a running local backend; --ai additionally makes one paid chat request."""
import argparse
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ai", action="store_true")
    args = parser.parse_args()
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=35, trust_env=False) as client:
        status = client.get("/api/v1/knowledge/status")
        status.raise_for_status()
        print("index:", status.json()["documents"], "sources,", status.json()["chunks"], "chunks")
        cities = client.get("/api/v1/cities")
        cities.raise_for_status()
        city_id = next(c["id"] for c in cities.json() if c.get("name_zh") == "成都")
        for question, expected in [("武侯祠行李在哪里寄存", "answered"),
                                   ("熊猫基地明天还有票吗", "requires_live_data"),
                                   ("人民公园有行李寄存吗", "not_found")]:
            r = client.post("/api/v1/knowledge/ask", json={"city_id": city_id, "question": question})
            r.raise_for_status()
            data = r.json()
            assert data["status"] == expected, data
            if expected == "answered":
                assert data["retrieval_mode"] == "hybrid_bm25_vector_rrf", data
                assert data["citations"][0]["id"] == "wuhou-visit:luggage", data
            print(question, "=>", data["status"], data["retrieval_mode"])
        if args.ai:
            r = client.post("/api/v1/knowledge/ask", json={"city_id": city_id, "question": "武侯祠寄存行李", "use_ai": True})
            r.raise_for_status()
            data = r.json()
            assert data["citations"], "AI failure must not discard retrieved evidence"
            print("AI:", data["answer_mode"], data["warnings"])


if __name__ == "__main__":
    main()
