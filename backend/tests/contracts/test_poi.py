"""Tests for POI practical-info contracts."""
from app.contracts.poi import PoiIdentifier, PoiPracticalInfo


def test_poi_practical_info_defaults_unknown_to_none():
    """ADR-007: unknown fields stay None, they are not coerced to a suggestion."""
    poi = PoiPracticalInfo(
        identifier=PoiIdentifier(provider="mock", provider_poi_id="x"),
        name="Test POI",
    )
    # Every practical field that the provider did not fill must be None.
    assert poi.opening_hours is None
    assert poi.last_entry_time is None
    assert poi.ticket_price is None
    assert poi.reservation_required is None
    assert poi.estimated_queue_minutes is None
    assert poi.restroom_available is None
    assert poi.luggage_storage is None
    assert poi.accessibility is None
    assert poi.nearest_public_transport is None
    assert poi.rating is None
    # Evidence list defaults to empty (no fabricated provenance).
    assert poi.evidence == []


def test_poi_identifier_required_fields():
    ident = PoiIdentifier(provider="google_places", provider_poi_id="ChIJ123")
    assert ident.provider == "google_places"
    assert ident.canonical_place_id is None
