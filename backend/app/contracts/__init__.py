"""TripPilot domain contracts.

Provider-agnostic Pydantic models for data trust and provenance. These are the
shared, type-safe contracts consumed by future Engines (Retrieval, Optimization,
Agent, Critic). They are deliberately kept separate from `app/api/schemas`
(API DTOs) and `app/db/models` (SQLAlchemy ORM).
"""
from app.contracts.common import (
    ConfidenceKind,
    Evidence,
    ProviderError,
    ProviderResult,
)
from app.contracts.poi import (
    PoiIdentifier,
    PoiPracticalInfo,
    PoiSearchQuery,
)

__all__ = [
    "ConfidenceKind",
    "Evidence",
    "ProviderError",
    "ProviderResult",
    "PoiIdentifier",
    "PoiPracticalInfo",
    "PoiSearchQuery",
]
