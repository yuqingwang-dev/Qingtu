"""Validated read-only planning tools and explicit candidate-set semantics."""
import logging
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.api.schemas import Category, TravelMode
from app.config import settings
from app.core.scoring import haversine_distance, estimate_travel_time


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchArgs(ToolArgs):
    city_id: int = Field(gt=0)
    query: str = Field(max_length=500)
    top_k: int = Field(default=20, ge=1, le=50)


class FilterArgs(ToolArgs):
    city_id: int = Field(gt=0)
    category: Optional[Category] = None
    max_cost: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    min_rating: Optional[float] = Field(default=None, ge=0, le=5, allow_inf_nan=False)
    limit: int = Field(default=20, ge=1, le=50)


class TravelArgs(ToolArgs):
    lat1: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon1: float = Field(ge=-180, le=180, allow_inf_nan=False)
    lat2: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon2: float = Field(ge=-180, le=180, allow_inf_nan=False)
    travel_mode: TravelMode


class OptimizeArgs(ToolArgs):
    ready: bool


class ExplainArgs(ToolArgs):
    activity_name: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


TOOL_MODELS = {
    "search_activities_semantic": (SearchArgs, "Search this city's allowed POIs. Replaces candidates. Empty query explicitly lists available POIs. Returns IDs and retrieval mode; empty matches are not replaced with unrelated POIs."),
    "filter_activities": (FilterArgs, "Narrow CURRENT candidates by category/cost/rating; never restart from the full catalog."),
    "estimate_travel_time": (TravelArgs, "Estimate travel time from straight-line distance, NOT real road navigation."),
    "optimize_itinerary": (OptimizeArgs, "Build final plan using ONLY current candidates. Call once with ready=true, after gathering enough candidates."),
    "explain_activity": (ExplainArgs, "Record a selection explanation for an existing candidate, not a factual verification."),
}
TOOLS = [{"type": "function", "function": {"name": name, "description": desc,
          "parameters": schema.model_json_schema()}} for name, (schema, desc) in TOOL_MODELS.items()]


def serialize_pois(activities):
    return [{"id": a.id, "name": a.name, "name_zh": a.name_zh,
             "category": a.category, "cost": a.base_cost, "rating": a.rating} for a in activities]


async def search_candidates(args, city_id, db, eligible):
    if settings.RAG_ENABLED and args.query.strip():
        try:
            from sqlalchemy import text
            from app.services.embedding_service import generate_embedding
            embedding = await generate_embedding(args.query)
            rows = db.execute(text("""
                SELECT a.id FROM activity_embeddings ae
                JOIN activities a ON ae.activity_id = a.id
                WHERE a.city_id = :city_id AND ae.embedding_vec IS NOT NULL
                ORDER BY ae.embedding_vec <=> CAST(:embedding AS vector) ASC
                LIMIT :top_k
            """), {"city_id": city_id, "embedding": str(embedding), "top_k": args.top_k}).fetchall()
            by_id = {a.id: a for a in eligible}
            return [by_id[row[0]] for row in rows if row[0] in by_id], "vector"
        except Exception as error:
            db.rollback()
            logging.getLogger(__name__).warning("Agent retrieval degraded: %s", type(error).__name__)
            mode = "keyword_fallback"
    else:
        mode = "keyword"
    query = args.query.strip().lower()
    labels = {"文化": "culture", "博物馆": "culture", "美食": "food", "自然": "nature",
              "购物": "shopping", "夜生活": "nightlife", "海滩": "beaches", "冒险": "adventure"}
    tokens = query.split() + [value for label, value in labels.items() if label in query]
    matches = []
    for activity in eligible:
        text = " ".join(str(x or "") for x in [activity.name, activity.name_zh,
            activity.description, activity.description_zh, activity.category]).lower()
        if not query or any(token in text for token in tokens):
            matches.append(activity)
    return sorted(matches, key=lambda a: (-a.rating, a.id))[:args.top_k], mode


def filter_candidates(args, candidates):
    return sorted([a for a in candidates
        if (args.category is None or a.category == args.category.value)
        and (args.max_cost is None or a.base_cost <= args.max_cost)
        and (args.min_rating is None or a.rating >= args.min_rating)
    ], key=lambda a: (-a.rating, a.id))[:args.limit]


def travel_estimate(args):
    distance = haversine_distance(args.lat1, args.lon1, args.lat2, args.lon2)
    return {"minutes": estimate_travel_time(distance, args.travel_mode),
            "distance_km": round(distance, 2), "source": "straight_line_estimate"}
