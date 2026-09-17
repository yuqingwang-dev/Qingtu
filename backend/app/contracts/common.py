"""Common trust/provenance contracts shared across all providers.

Per ADR-007 every execution-relevant field must carry field-level provenance and
one of three confidence kinds: VERIFIED, ESTIMATED, AI_SUGGESTION. Unknown values
stay unknown and are never fabricated by the LLM (see docs/trippilot_product.md
section 4 and docs/decisions.md ADR-007).

Each Provider method returns a structured `ProviderResult` envelope rather than
raw supplier JSON (see docs/trippilot_architecture.md section 3.1).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field


class ConfidenceKind(str, Enum):
    """Three-state confidence for execution-relevant data.

    - VERIFIED: from a traceable authoritative source, still within TTL.
    - ESTIMATED: derived via a stated algorithm or historical data; rationale required.
    - AI_SUGGESTION: model-proposed suggestion; never treated as fact (hours, price,
      transport, etc.).
    """

    VERIFIED = "VERIFIED"
    ESTIMATED = "ESTIMATED"
    AI_SUGGESTION = "AI_SUGGESTION"


class Evidence(BaseModel):
    """Field-level provenance record (mirrors the `data_evidence` table).

    A single POI's coordinate, hours, queue and price may come from different
    sources at different times, so provenance is recorded per field, not per
    entity (ADR-007).
    """

    entity_type: str
    entity_id: str
    field_name: str
    value_json: str
    source: str
    source_url: Optional[str] = None
    observed_at: datetime
    expires_at: Optional[datetime] = None
    confidence_kind: ConfidenceKind
    confidence_score: Optional[float] = None
    errors: list[str] = Field(default_factory=list)


class ProviderError(BaseModel):
    """A single error raised by a provider call (never raised as an exception)."""

    code: str
    message: str
    retryable: bool = False


T = TypeVar("T")


class ProviderResult(BaseModel, Generic[T]):
    """Generic envelope returned by every Provider method.

    `data` is the (optionally empty) payload; `source`, `observed_at`,
    `expires_at`, `confidence_kind` and `confidence_score` describe the call-level
    provenance; `errors` lists non-fatal degradations. On timeout/limit/empty
    results a provider returns a degraded `ProviderResult` (empty data + errors)
    rather than raising.
    """

    data: T
    source: str
    observed_at: datetime
    expires_at: Optional[datetime] = None
    confidence_kind: ConfidenceKind
    confidence_score: Optional[float] = None
    errors: list[ProviderError] = Field(default_factory=list)
