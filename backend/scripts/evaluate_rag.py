"""
RAG vs SQL Retrieval Evaluation — Precision@K Comparison

Measures whether semantic RAG retrieval surfaces more relevant activities
than a simple SQL category filter, for the same user preference profiles.

Metric: Precision@K
    For each test case, take the top-K retrieved activities.
    Count how many are "relevant" (match preferred categories OR are must-visit).
    Precision@K = relevant_in_top_k / K

Usage:
    cd backend
    source venv/bin/activate
    python scripts/evaluate_rag.py --city-id 1 --top-k 10

Results are printed as a comparison table and saved to rag_eval_results.json.
"""
import asyncio
import argparse
import json
import sys
import os

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import Activity
from app.api.schemas import TripPreferences, BudgetLevel, EnergyLevel, TravelMode, Category
from app.services.embedding_service import build_preference_query_text, generate_embedding
from app.config import settings


# ─── Test Cases ──────────────────────────────────────────────────────────────
# Each test case defines:
#   - A user preference profile (what they asked for)
#   - Relevant categories (ground truth: what results should match)
#
# Ground truth is intentionally simple: relevant = activity.category in relevant_categories
# This is a fair baseline because the SQL filter also uses category — so if RAG wins,
# it means it's finding semantically relevant activities BEYOND what SQL finds by category alone.

TEST_CASES = [
    {
        "name": "Culture & Food Weekend",
        "preferences": {
            "trip_type": "weekend",
            "energy_level": "moderate",
            "categories": ["culture", "food"],
            "budget_level": "medium",
        },
        "relevant_categories": {"culture", "food"},
    },
    {
        "name": "Active Adventure Trip",
        "preferences": {
            "trip_type": "adventure",
            "energy_level": "active",
            "categories": ["adventure", "nature"],
            "budget_level": "medium",
        },
        "relevant_categories": {"adventure", "nature"},
    },
    {
        "name": "Luxury Nightlife",
        "preferences": {
            "trip_type": "city_break",
            "energy_level": "active",
            "categories": ["nightlife", "food"],
            "budget_level": "high",
        },
        "relevant_categories": {"nightlife", "food"},
    },
    {
        "name": "Relaxed Nature Retreat",
        "preferences": {
            "trip_type": "relaxation",
            "energy_level": "relaxed",
            "categories": ["nature", "beaches"],
            "budget_level": "low",
        },
        "relevant_categories": {"nature", "beaches"},
    },
    {
        "name": "Budget Culture Tour",
        "preferences": {
            "trip_type": "cultural",
            "energy_level": "moderate",
            "categories": ["culture", "shopping"],
            "budget_level": "low",
        },
        "relevant_categories": {"culture", "shopping"},
    },
]


# ─── SQL Baseline ─────────────────────────────────────────────────────────────

def sql_retrieve(city_id: int, categories: list[str], top_k: int, db: Session) -> list[Activity]:
    """
    Baseline: SQL category filter, ordered by rating DESC.
    This is what the system used before RAG.
    """
    query = db.query(Activity).filter(Activity.city_id == city_id)
    if categories:
        query = query.filter(Activity.category.in_(categories))
    return query.order_by(Activity.rating.desc()).limit(top_k).all()


# ─── RAG Retrieval ────────────────────────────────────────────────────────────

async def rag_retrieve(city_id: int, test_case: dict, top_k: int, db: Session) -> list[Activity]:
    """
    RAG: embed the preference query and do cosine similarity search via pgvector.
    Falls back to SQL if embeddings are missing.
    """
    from sqlalchemy import text

    pref = test_case["preferences"]
    query_text = build_preference_query_text(
        trip_type=pref["trip_type"],
        energy_level=pref["energy_level"],
        categories=pref["categories"],
        budget_level=pref["budget_level"],
    )

    try:
        embedding = await generate_embedding(query_text)
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

        rows = db.execute(text("""
            SELECT a.id, ae.embedding_vec <=> CAST(:embedding AS vector) AS distance
            FROM activity_embeddings ae
            JOIN activities a ON ae.activity_id = a.id
            WHERE a.city_id = :city_id
              AND ae.embedding_vec IS NOT NULL
            ORDER BY distance ASC
            LIMIT :top_k
        """), {"embedding": embedding_str, "city_id": city_id, "top_k": top_k}).fetchall()

        if not rows:
            print(f"  [RAG] No embeddings found for city {city_id} — falling back to SQL")
            return sql_retrieve(city_id, pref["categories"], top_k, db)

        activity_ids = [r[0] for r in rows]
        activities = db.query(Activity).filter(Activity.id.in_(activity_ids)).all()
        id_order = {aid: idx for idx, aid in enumerate(activity_ids)}
        activities.sort(key=lambda a: id_order.get(a.id, 999))
        return activities

    except Exception as e:
        print(f"  [RAG] Error: {e} — falling back to SQL")
        return sql_retrieve(city_id, pref["categories"], top_k, db)


# ─── Precision@K ─────────────────────────────────────────────────────────────

def precision_at_k(activities: list[Activity], relevant_categories: set[str], k: int) -> float:
    """
    Precision@K: fraction of top-K results that are relevant.
    Relevant = activity.category is in relevant_categories.
    """
    top_k = activities[:k]
    if not top_k:
        return 0.0
    relevant = sum(1 for a in top_k if a.category in relevant_categories)
    return relevant / len(top_k)


# ─── Main Evaluation Loop ─────────────────────────────────────────────────────

async def evaluate(city_id: int, top_k: int):
    db: Session = SessionLocal()

    # Check activity count for this city
    total_activities = db.query(Activity).filter(Activity.city_id == city_id).count()
    if total_activities == 0:
        print(f"No activities found for city_id={city_id}. Check your city ID.")
        db.close()
        return

    print(f"\nQingtu — RAG vs SQL Retrieval Evaluation")
    print(f"City ID: {city_id} | Total activities: {total_activities} | K={top_k}")
    print("=" * 72)

    results = []
    sql_precisions = []
    rag_precisions = []

    for tc in TEST_CASES:
        print(f"\nTest: {tc['name']}")
        print(f"  Preferences: {tc['preferences']['categories']} | {tc['preferences']['energy_level']} energy | {tc['preferences']['budget_level']} budget")
        print(f"  Relevant categories: {tc['relevant_categories']}")

        # SQL baseline
        sql_results = sql_retrieve(city_id, tc["preferences"]["categories"], top_k, db)
        sql_p = precision_at_k(sql_results, tc["relevant_categories"], top_k)
        sql_precisions.append(sql_p)

        # RAG
        rag_results = await rag_retrieve(city_id, tc, top_k, db)
        rag_p = precision_at_k(rag_results, tc["relevant_categories"], top_k)
        rag_precisions.append(rag_p)

        delta = rag_p - sql_p
        winner = "RAG ✓" if rag_p > sql_p else ("TIE" if rag_p == sql_p else "SQL ✓")

        print(f"  SQL  Precision@{top_k}: {sql_p:.2f}  ({int(sql_p * top_k)}/{top_k} relevant)")
        print(f"  RAG  Precision@{top_k}: {rag_p:.2f}  ({int(rag_p * top_k)}/{top_k} relevant)")
        print(f"  Delta: {delta:+.2f}  →  {winner}")

        # Show what RAG retrieved that SQL missed
        sql_names = {a.name for a in sql_results}
        rag_only = [a for a in rag_results if a.name not in sql_names and a.category in tc["relevant_categories"]]
        if rag_only:
            print(f"  RAG-only relevant finds: {[a.name for a in rag_only[:3]]}")

        results.append({
            "test_case": tc["name"],
            "preferences": tc["preferences"],
            "relevant_categories": list(tc["relevant_categories"]),
            "sql_precision_at_k": round(sql_p, 4),
            "rag_precision_at_k": round(rag_p, 4),
            "delta": round(delta, 4),
            "winner": winner,
            "sql_top_k": [{"name": a.name, "category": a.category} for a in sql_results[:top_k]],
            "rag_top_k": [{"name": a.name, "category": a.category} for a in rag_results[:top_k]],
        })

    # Summary
    avg_sql = sum(sql_precisions) / len(sql_precisions)
    avg_rag = sum(rag_precisions) / len(rag_precisions)
    avg_delta = avg_rag - avg_sql
    rag_wins = sum(1 for r, s in zip(rag_precisions, sql_precisions) if r > s)

    print("\n" + "=" * 72)
    print("SUMMARY")
    print(f"  Avg SQL  Precision@{top_k}: {avg_sql:.3f}")
    print(f"  Avg RAG  Precision@{top_k}: {avg_rag:.3f}")
    print(f"  Avg Delta:               {avg_delta:+.3f}")
    print(f"  RAG wins: {rag_wins}/{len(TEST_CASES)} test cases")

    if avg_delta > 0:
        improvement_pct = (avg_delta / avg_sql * 100) if avg_sql > 0 else 0
        print(f"\n  RAG improves precision by {avg_delta:+.3f} ({improvement_pct:.1f}% relative improvement)")
    elif avg_delta == 0:
        print("\n  RAG and SQL perform equally on this city's activity set.")
    else:
        print(f"\n  SQL outperforms RAG by {-avg_delta:.3f} on this city. Check embedding quality.")

    # Save results
    output = {
        "city_id": city_id,
        "total_activities": total_activities,
        "top_k": top_k,
        "avg_sql_precision": round(avg_sql, 4),
        "avg_rag_precision": round(avg_rag, 4),
        "avg_delta": round(avg_delta, 4),
        "rag_wins": f"{rag_wins}/{len(TEST_CASES)}",
        "test_cases": results,
    }

    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rag_eval_results.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Full results saved to: rag_eval_results.json")

    db.close()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate RAG vs SQL retrieval precision")
    parser.add_argument("--city-id", type=int, default=1, help="City ID to evaluate (default: 1)")
    parser.add_argument("--top-k", type=int, default=10, help="K for Precision@K (default: 10)")
    args = parser.parse_args()

    if not settings.OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY not set. RAG requires embeddings — set your key in .env")
        sys.exit(1)

    asyncio.run(evaluate(args.city_id, args.top_k))
