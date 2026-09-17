"""POI practical-information contracts.

Field set follows docs/trippilot_architecture.md section 4 (`poi_practical_info`)
and docs/trippilot_product.md. Every practical field is optional: a provider that
cannot verify a field leaves it `None` rather than fabricating a value (ADR-007).
Field-level provenance is attached via the `evidence` list.
"""
from __future__ import annotations

from datetime import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.contracts.common import Evidence


class PoiIdentifier(BaseModel):
    """Stable cross-provider identifier for a place."""

    provider: str
    provider_poi_id: str
    canonical_place_id: Optional[str] = None


class PoiPracticalInfo(BaseModel):
    """Practical, execution-relevant info for a POI.

    Only `identifier` and `name` are required. All other fields default to `None`
    (unknown) so that downstream Engines and the Critic can distinguish "we do not
    know" from "we know it is unavailable". Each known field should have a matching
    entry in `evidence` describing its source and confidence.
    """

    identifier: PoiIdentifier
    name: str

    # Location
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coordinate_system: Optional[str] = None
    address: Optional[str] = None
    city_name: Optional[str] = None
    category: Optional[str] = None
    provider_type: Optional[str] = None
    average_spend: Optional[float] = None

    # Time windows
    opening_hours: Optional[dict[str, Any]] = None
    closing_time: Optional[time] = None
    last_entry_time: Optional[time] = None
    recommended_duration_minutes: Optional[int] = None

    # Cost / reservation
    ticket_price: Optional[float] = None
    currency: Optional[str] = None
    reservation_required: Optional[bool] = None
    reservation_url: Optional[str] = None

    # Crowding / load
    crowd_level: Optional[str] = None
    estimated_queue_minutes: Optional[int] = None
    walking_load: Optional[float] = None
    standing_load: Optional[float] = None
    stairs: Optional[bool] = None
    slope: Optional[bool] = None

    # Accessibility & facilities
    restroom_available: Optional[bool] = None
    luggage_storage: Optional[bool] = None
    accessibility: Optional[dict[str, Any]] = None
    taxi_accessibility: Optional[str] = None
    nearest_public_transport: Optional[dict[str, Any]] = None
    last_public_transport: Optional[dict[str, Any]] = None
    indoor_ratio: Optional[float] = None

    # Popularity (carried for scoring; provenance per field via evidence)
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None

    # Field-level provenance (ADR-007)
    evidence: list[Evidence] = Field(default_factory=list)


class PoiSearchQuery(BaseModel):
    """Provider-agnostic input to `SearchProvider.search_pois`."""

    text_query: Optional[str] = None
    city_name: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    near_lat: Optional[float] = None
    near_lon: Optional[float] = None
    city_lat: Optional[float] = None
    city_lon: Optional[float] = None
    max_results: int = 5
    explicit_query: Optional[str] = None
