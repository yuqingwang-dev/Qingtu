"""Tests for MockSearchProvider."""
import asyncio
from datetime import datetime, timezone

from app.contracts.common import ConfidenceKind
from app.contracts.poi import PoiSearchQuery
from app.providers.mock_search import MockSearchProvider


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_mock_search_returns_valid_result():
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    provider = MockSearchProvider(now=now)
    result = _run(provider.search_pois(PoiSearchQuery(text_query="museum", max_results=5)))

    assert result.source == "mock"
    assert result.observed_at == now
    assert result.expires_at is not None
    assert len(result.data) == 2
    # Each POI carries evidence.
    all_evidence = [ev for poi in result.data for ev in poi.evidence]
    assert all_evidence, "mock POIs must carry field-level evidence"
    kinds = {ev.confidence_kind for ev in all_evidence}
    assert ConfidenceKind.VERIFIED in kinds
    assert ConfidenceKind.ESTIMATED in kinds


def test_mock_search_is_deterministic():
    provider = MockSearchProvider(now=datetime(2026, 9, 8, tzinfo=timezone.utc))
    r1 = _run(provider.search_pois(PoiSearchQuery(max_results=5)))
    r2 = _run(provider.search_pois(PoiSearchQuery(max_results=5)))
    assert [p.identifier.provider_poi_id for p in r1.data] == [
        p.identifier.provider_poi_id for p in r2.data
    ]


def test_mock_search_respects_max_results():
    provider = MockSearchProvider()
    result = _run(provider.search_pois(PoiSearchQuery(max_results=1)))
    assert len(result.data) == 1


def test_mock_search_get_poi_details():
    provider = MockSearchProvider()
    result = _run(provider.get_poi_details("mock-museum-001"))
    assert result.data.identifier.provider_poi_id == "mock-museum-001"


def test_mock_does_not_fabricate_unknown_fields():
    """The café mock does not provide opening_hours or last_entry_time."""
    provider = MockSearchProvider()
    result = _run(provider.search_pois(PoiSearchQuery(max_results=5)))
    cafe = next(p for p in result.data if p.identifier.provider_poi_id == "mock-cafe-002")
    assert cafe.opening_hours is None
    assert cafe.last_entry_time is None
    assert cafe.reservation_required is None
