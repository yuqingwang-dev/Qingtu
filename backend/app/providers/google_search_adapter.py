"""Non-breaking Google Places adapter implementing `SearchProvider`.

This adapter wraps the existing `app.services.places_service.fetch_real_venues`
(which calls the Google Places API (New) Text Search) and maps its raw venue
dicts into structured `PoiPracticalInfo` with field-level evidence. It is purely
additive: it does not modify `places_service.py` or its single caller
(`refinement_service.py`), which keep using `places_service` directly. New v2
code consumes the adapter via the `SearchProvider` port.

Per ADR-007, only the fields Google actually returns are filled (VERIFIED or
ESTIMATED). All other practical fields (opening_hours, last_entry, queue,
reservation, restroom, transport, ...) stay `None` — never fabricated.

The adapter never raises: on empty results, missing API key, HTTP non-200 or
exceptions from `places_service` (which itself returns `[]` and logs on error),
it returns a degraded `ProviderResult` with `data=[]` and a `ProviderError`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from app.contracts.common import ConfidenceKind, Evidence, ProviderError, ProviderResult
from app.contracts.poi import PoiIdentifier, PoiPracticalInfo, PoiSearchQuery

# Reuse the existing price-level -> cost mapping (constant read, no behavior change).
from app.services.places_service import COST_FROM_PRICE_LEVEL

# Type of the injectable fetch function (matches places_service.fetch_real_venues).
FetchVenuesFn = Callable[..., Awaitable[list[dict[str, Any]]]]


class GoogleSearchAdapter:
    """`SearchProvider` backed by the existing Google Places service."""

    SOURCE = "google_places"

    def __init__(
        self,
        fetch_venues_fn: Optional[FetchVenuesFn] = None,
        now: Optional[datetime] = None,
    ) -> None:
        # Lazy default: use the real places_service.fetch_real_venues when no
        # function is injected (keeps tests network-free by injecting a fake).
        self._fetch_venues_fn = fetch_venues_fn
        self._now = now or datetime.now(timezone.utc)

    async def search_pois(
        self, query: PoiSearchQuery,
    ) -> ProviderResult[list[PoiPracticalInfo]]:
        # Without a search centre we cannot call Places Text Search; degrade.
        if query.city_lat is None or query.city_lon is None:
            return self._degraded([], "missing_search_center")

        fetch = self._fetch_venues_fn or self._default_fetch
        try:
            venues = await fetch(
                city_lat=query.city_lat,
                city_lon=query.city_lon,
                user_message=query.text_query or "",
                desired_categories=list(query.categories),
                max_results=query.max_results,
                near_lat=query.near_lat,
                near_lon=query.near_lon,
                explicit_query=query.explicit_query,
            )
        except Exception as exc:  # noqa: BLE001 - degrade, never raise
            return self._degraded([], f"google_places_error: {exc}")

        if not venues:
            # places_service returns [] on no API key, non-200, or empty results.
            return self._degraded([], "places_unavailable")

        pois = [self._map_venue(v) for v in venues]
        return ProviderResult[list[PoiPracticalInfo]](
            data=pois,
            source=self.SOURCE,
            observed_at=self._now,
            expires_at=self._now + timedelta(hours=1),
            confidence_kind=ConfidenceKind.VERIFIED,
            confidence_score=1.0,
            errors=[],
        )

    async def get_poi_details(self, poi_id: str) -> ProviderResult[PoiPracticalInfo]:
        # Google Places Text Search does not support fetch-by-id in the current
        # places_service surface. Degrade honestly rather than fabricate.
        return ProviderResult[PoiPracticalInfo](
            data=PoiPracticalInfo(
                identifier=PoiIdentifier(
                    provider=self.SOURCE, provider_poi_id=poi_id,
                ),
                name="",
            ),
            source=self.SOURCE,
            observed_at=self._now,
            expires_at=self._now + timedelta(minutes=15),
            confidence_kind=ConfidenceKind.ESTIMATED,
            errors=[ProviderError(
                code="not_implemented",
                message="Google Places Text Search does not support get-by-id.",
                retryable=False,
            )],
        )

    # --- helpers --------------------------------------------------------

    @staticmethod
    async def _default_fetch(**kwargs: Any) -> list[dict[str, Any]]:
        # Imported lazily so that simply constructing the adapter never triggers
        # an HTTP client or requires a real API key at import time.
        from app.services.places_service import fetch_real_venues
        return await fetch_real_venues(**kwargs)

    def _map_venue(self, venue: dict[str, Any]) -> PoiPracticalInfo:
        place_id = str(venue.get("place_id", ""))
        name = str(venue.get("name", ""))
        lat = venue.get("latitude")
        lon = venue.get("longitude")
        rating = venue.get("rating")
        reviews = venue.get("user_ratings_total")
        price_level = venue.get("price_level")

        evidence: list[Evidence] = []
        if name:
            evidence.append(self._ev(place_id, "name", name, ConfidenceKind.VERIFIED))
        if lat is not None:
            evidence.append(self._ev(place_id, "latitude", str(lat), ConfidenceKind.VERIFIED))
        if lon is not None:
            evidence.append(self._ev(place_id, "longitude", str(lon), ConfidenceKind.VERIFIED))
        if rating is not None:
            evidence.append(self._ev(place_id, "rating", str(rating), ConfidenceKind.VERIFIED))
        if reviews is not None:
            evidence.append(self._ev(place_id, "user_ratings_total", str(reviews), ConfidenceKind.VERIFIED))
        if price_level is not None:
            evidence.append(self._ev(place_id, "ticket_price", str(price_level), ConfidenceKind.ESTIMATED))

        estimated_cost = COST_FROM_PRICE_LEVEL.get(price_level) if price_level is not None else None

        return PoiPracticalInfo(
            identifier=PoiIdentifier(
                provider=self.SOURCE, provider_poi_id=place_id,
            ),
            name=name,
            latitude=lat,
            longitude=lon,
            rating=rating,
            user_ratings_total=reviews,
            # Cost from Google price_level is an ESTIMATED bucket, not a real price.
            ticket_price=estimated_cost,
            currency="USD" if estimated_cost is not None else None,
            # All other practical fields stay None — Google Places Text Search
            # does not reliably return them, and we must not fabricate (ADR-007).
            evidence=evidence,
        )

    def _ev(
        self, entity_id: str, field_name: str, value: str, kind: ConfidenceKind,
    ) -> Evidence:
        return Evidence(
            entity_type="poi",
            entity_id=entity_id,
            field_name=field_name,
            value_json=json.dumps(value),
            source=self.SOURCE,
            observed_at=self._now,
            confidence_kind=kind,
            confidence_score=1.0 if kind is ConfidenceKind.VERIFIED else 0.5,
        )

    def _degraded(
        self, data: list[PoiPracticalInfo], message: str,
    ) -> ProviderResult[list[PoiPracticalInfo]]:
        return ProviderResult[list[PoiPracticalInfo]](
            data=data,
            source=self.SOURCE,
            observed_at=self._now,
            expires_at=self._now + timedelta(minutes=15),
            confidence_kind=ConfidenceKind.ESTIMATED,
            errors=[ProviderError(
                code="places_unavailable",
                message=message,
                retryable=True,
            )],
        )
