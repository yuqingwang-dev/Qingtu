"""Mock SearchProvider for tests and local development.

Returns a small canned, deterministic set of POIs with field-level evidence so
that downstream contract/consumer code can be exercised without any network or
real provider. No `httpx`, no clock drift (an injected `now` is used).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.contracts.common import ConfidenceKind, Evidence, ProviderResult
from app.contracts.poi import PoiIdentifier, PoiPracticalInfo, PoiSearchQuery


class MockSearchProvider:
    """A `SearchProvider` returning canned POIs (no network)."""

    SOURCE = "mock"

    def __init__(self, now: Optional[datetime] = None) -> None:
        self._now = now or datetime.now(timezone.utc)

    async def search_pois(self, query: PoiSearchQuery) -> ProviderResult[list[PoiPracticalInfo]]:
        pois = [self._mock_museum(), self._mock_cafe()]
        # Respect max_results for shape parity with a real provider.
        pois = pois[: max(query.max_results, 0)]
        return ProviderResult[list[PoiPracticalInfo]](
            data=pois,
            source=self.SOURCE,
            observed_at=self._now,
            expires_at=self._now + timedelta(hours=24),
            confidence_kind=ConfidenceKind.ESTIMATED,
            confidence_score=0.5,
            errors=[],
        )

    async def get_poi_details(self, poi_id: str) -> ProviderResult[PoiPracticalInfo]:
        poi = self._mock_museum() if poi_id == "mock-museum-001" else self._mock_cafe()
        return ProviderResult[PoiPracticalInfo](
            data=poi,
            source=self.SOURCE,
            observed_at=self._now,
            expires_at=self._now + timedelta(hours=24),
            confidence_kind=ConfidenceKind.ESTIMATED,
            confidence_score=0.5,
            errors=[],
        )

    # --- canned fixtures -------------------------------------------------

    def _mock_museum(self) -> PoiPracticalInfo:
        ev = self._evidence
        return PoiPracticalInfo(
            identifier=PoiIdentifier(
                provider=self.SOURCE, provider_poi_id="mock-museum-001",
                canonical_place_id=None,
            ),
            name="Mock Museum of Modern Art",
            latitude=37.7857,
            longitude=-122.4011,
            rating=4.4,
            user_ratings_total=1520,
            recommended_duration_minutes=150,
            ticket_price=25.0,
            currency="USD",
            restroom_available=True,
            indoor_ratio=1.0,
            evidence=[
                ev("mock-museum-001", "name", "Mock Museum of Modern Art", ConfidenceKind.VERIFIED),
                ev("mock-museum-001", "latitude", "37.7857", ConfidenceKind.VERIFIED),
                ev("mock-museum-001", "rating", "4.4", ConfidenceKind.VERIFIED),
                ev("mock-museum-001", "recommended_duration_minutes", "150", ConfidenceKind.ESTIMATED),
                ev("mock-museum-001", "ticket_price", "25.0", ConfidenceKind.ESTIMATED),
                ev("mock-museum-001", "restroom_available", "true", ConfidenceKind.VERIFIED),
            ],
        )

    def _mock_cafe(self) -> PoiPracticalInfo:
        ev = self._evidence
        return PoiPracticalInfo(
            identifier=PoiIdentifier(
                provider=self.SOURCE, provider_poi_id="mock-cafe-002",
                canonical_place_id=None,
            ),
            name="Mock Corner Café",
            latitude=37.7790,
            longitude=-122.4100,
            rating=4.6,
            user_ratings_total=210,
            estimated_queue_minutes=10,
            restroom_available=True,
            indoor_ratio=1.0,
            evidence=[
                ev("mock-cafe-002", "name", "Mock Corner Café", ConfidenceKind.VERIFIED),
                ev("mock-cafe-002", "latitude", "37.779", ConfidenceKind.VERIFIED),
                ev("mock-cafe-002", "rating", "4.6", ConfidenceKind.VERIFIED),
                ev("mock-cafe-002", "estimated_queue_minutes", "10", ConfidenceKind.ESTIMATED),
            ],
        )

    def _evidence(
        self, entity_id: str, field_name: str, value: str, kind: ConfidenceKind,
    ) -> Evidence:
        return Evidence(
            entity_type="poi",
            entity_id=entity_id,
            field_name=field_name,
            value_json=value,
            source=self.SOURCE,
            observed_at=self._now,
            confidence_kind=kind,
            confidence_score=1.0 if kind is ConfidenceKind.VERIFIED else 0.5,
        )
