"""Tests for GoogleSearchAdapter (non-breaking wrapper around places_service)."""
import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from app.contracts.common import ConfidenceKind
from app.contracts.poi import PoiSearchQuery
from app.providers.google_search_adapter import GoogleSearchAdapter


def _run(coro):
    return asyncio.run(coro)


def _fake_fetch_factory(venues: list[dict[str, Any]]):
    async def _fake(**kwargs: Any) -> list[dict[str, Any]]:
        # Record that the adapter forwards the query shape to places_service.
        _fake.last_kwargs = kwargs
        return venues
    _fake.last_kwargs = None
    return _fake


def _sample_venue() -> dict[str, Any]:
    return {
        "name": "Test Museum",
        "rating": 4.5,
        "address": "1 Main St",
        "latitude": 37.7857,
        "longitude": -122.4011,
        "place_id": "ChIJTest",
        "types": ["museum"],
        "price_level": 2,
        "price_label": "Moderate",
        "user_ratings_total": 1234,
    }


def test_adapter_maps_google_venue_to_verified_fields():
    fetch = _fake_fetch_factory([_sample_venue()])
    adapter = GoogleSearchAdapter(fetch_venues_fn=fetch, now=datetime(2026, 9, 8, tzinfo=timezone.utc))
    result = _run(adapter.search_pois(PoiSearchQuery(
        text_query="museum", categories=["culture"],
        city_lat=37.7749, city_lon=-122.4194, max_results=5,
    )))

    assert result.source == "google_places"
    assert len(result.data) == 1
    poi = result.data[0]
    # Google-provided fields are filled and VERIFIED.
    assert poi.name == "Test Museum"
    assert poi.latitude == 37.7857
    assert poi.longitude == -122.4011
    assert poi.rating == 4.5
    assert poi.user_ratings_total == 1234
    # price_level 2 maps to an ESTIMATED cost bucket, not a real price.
    assert poi.ticket_price == 35.0
    assert poi.currency == "USD"
    # Fields Google does not return stay None — never fabricated (ADR-007).
    assert poi.opening_hours is None
    assert poi.last_entry_time is None
    assert poi.reservation_required is None
    assert poi.restroom_available is None
    assert poi.nearest_public_transport is None
    # Evidence present and tagged correctly.
    field_kinds = {ev.field_name: ev.confidence_kind for ev in poi.evidence}
    assert field_kinds["name"] is ConfidenceKind.VERIFIED
    assert field_kinds["rating"] is ConfidenceKind.VERIFIED
    assert field_kinds["ticket_price"] is ConfidenceKind.ESTIMATED


def test_adapter_degrades_on_empty_results():
    fetch = _fake_fetch_factory([])
    adapter = GoogleSearchAdapter(fetch_venues_fn=fetch)
    result = _run(adapter.search_pois(PoiSearchQuery(
        city_lat=37.7749, city_lon=-122.4194, max_results=5,
    )))
    assert result.data == []
    assert result.confidence_kind is ConfidenceKind.ESTIMATED
    assert len(result.errors) == 1
    assert result.errors[0].code == "places_unavailable"
    assert result.errors[0].retryable is True


def test_adapter_degrades_on_exception_without_raising():
    async def _raising(**kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("timeout")
    adapter = GoogleSearchAdapter(fetch_venues_fn=_raising)
    result = _run(adapter.search_pois(PoiSearchQuery(
        city_lat=37.7749, city_lon=-122.4194, max_results=5,
    )))
    assert result.data == []
    assert len(result.errors) == 1
    assert "google_places_error" in result.errors[0].message


def test_adapter_degrades_without_search_center():
    """Without city_lat/lon the adapter must not call fetch and must degrade."""
    fetch = _fake_fetch_factory([_sample_venue()])
    adapter = GoogleSearchAdapter(fetch_venues_fn=fetch)
    result = _run(adapter.search_pois(PoiSearchQuery(text_query="museum", max_results=5)))
    assert result.data == []
    assert result.errors[0].code == "places_unavailable"
    assert fetch.last_kwargs is None  # fetch was never invoked


def test_adapter_get_poi_details_degrades_honestly():
    adapter = GoogleSearchAdapter()
    result = _run(adapter.get_poi_details("ChIJ123"))
    # Google Text Search cannot fetch by id; adapter must not fabricate details.
    assert result.data.name == ""
    assert result.errors[0].code == "not_implemented"


def test_adapter_is_a_search_provider():
    """The adapter satisfies the runtime-checkable SearchProvider protocol."""
    from app.providers.base import SearchProvider
    adapter = GoogleSearchAdapter()
    assert isinstance(adapter, SearchProvider)
