"""Real pgvector/BGE vs BM25 smoke benchmark; no LLM call or fake vectors.

Small hand-labelled development set, NOT an independent production-quality eval.
Run from backend: python -m scripts.evaluate_knowledge
"""
import json
from pathlib import Path
from statistics import mean
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env")


def main():
    from app.config import settings
    from app.db.session import SessionLocal
    from app.services.knowledge_service import retrieve
    cases = json.loads((ROOT / "data/knowledge/eval_cases.json").read_text(encoding="utf-8"))
    report = {"dataset": "chengdu-reviewed-development-v1", "cases": len(cases), "results": {}}
    original = settings.KNOWLEDGE_VECTOR_ENABLED
    try:
        for name, enabled in (("bm25", False), ("hybrid", True)):
            settings.KNOWLEDGE_VECTOR_ENABLED = enabled
            recalls, reciprocal_ranks, negatives, modes, failures = [], [], [], set(), []
            with SessionLocal() as db:
                for case in cases:
                    result = retrieve(db, "成都", case["question"])
                    if "gold" in case:
                        modes.add(result["retrieval_mode"])
                        ids = [c["id"] for c in result["citations"]]
                        gold = set(case["gold"])
                        recalls.append(len(gold.intersection(ids)) / len(gold))
                        rank = next((i for i, key in enumerate(ids, 1) if key in gold), None)
                        reciprocal_ranks.append(1 / rank if rank else 0)
                        if not rank:
                            failures.append({"question": case["question"], "actual": ids, "status": result["status"]})
                    else:
                        ok = result["status"] == case["status"] and not result["citations"]
                        negatives.append(ok)
                        if not ok:
                            failures.append({"question": case["question"], "actual_status": result["status"]})
            if enabled and modes != {"hybrid_bm25_vector_rrf"}:
                raise RuntimeError("Vector benchmark degraded; cannot report this as hybrid retrieval")
            report["results"][name] = {"answerable": len(recalls), "negative_cases": len(negatives),
                "recall_at_3": round(mean(recalls), 4), "mrr_at_3": round(mean(reciprocal_ranks), 4),
                "negative_status_accuracy": round(mean(negatives), 4), "failures": failures}
    finally:
        settings.KNOWLEDGE_VECTOR_ENABLED = original
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
