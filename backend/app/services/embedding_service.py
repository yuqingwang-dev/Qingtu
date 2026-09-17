"""Embedding service for generating vector embeddings via OpenAI."""
import logging
from typing import Optional
from app.config import settings
from app.db.models import Activity

logger = logging.getLogger(__name__)


def build_activity_embedding_text(activity: Activity) -> str:
    """
    Build a rich text representation of an activity for embedding.

    This text is what gets embedded — it should capture the semantic
    meaning of the activity so that semantic search works well.
    """
    parts = [
        f"Activity: {activity.name}",
        f"Category: {activity.category}",
    ]

    if activity.description:
        parts.append(f"Description: {activity.description}")

    if activity.tags:
        parts.append(f"Tags: {', '.join(activity.tags)}")

    parts.append(f"Duration: {activity.avg_duration_minutes} minutes")
    parts.append(f"Cost: ${activity.base_cost:.2f}")
    parts.append(f"Rating: {activity.rating:.1f}/5")

    return "\n".join(parts)


def build_preference_query_text(
    trip_type: str,
    energy_level: str,
    categories: list[str],
    budget_level: str,
    constraints_text: Optional[str] = None,
) -> str:
    """
    Build a semantic query string from user preferences.

    This is embedded and compared against activity embeddings
    to find the most semantically relevant candidates.
    """
    parts = [
        f"Looking for activities for a {trip_type.replace('_', ' ')} trip.",
        f"Energy level: {energy_level}.",
    ]

    if categories:
        parts.append(f"Preferred categories: {', '.join(categories)}.")

    parts.append(f"Budget: {budget_level}.")

    if constraints_text:
        parts.append(constraints_text)

    return " ".join(parts)


async def generate_embedding(text: str) -> list[float]:
    """
    Generate a vector embedding for the given text using OpenAI.

    Returns a list of 1536 floats (text-embedding-3-small dimension).
    Raises RuntimeError if OpenAI key is not configured.
    """
    api_key = settings.EMBEDDING_API_KEY
    if not api_key and settings.EMBEDDING_BASE_URL.rstrip("/") == "https://api.openai.com/v1":
        api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise RuntimeError("Embedding provider key not configured")

    from openai import AsyncOpenAI
    async with AsyncOpenAI(api_key=api_key, base_url=settings.EMBEDDING_BASE_URL,
                          timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=1) as client:
        response = await client.embeddings.create(model=settings.EMBEDDING_MODEL, input=text)
    return response.data[0].embedding
