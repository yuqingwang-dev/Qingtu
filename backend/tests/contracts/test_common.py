"""Tests for common trust/provenance contracts (ConfidenceKind, Evidence, ProviderResult)."""
from datetime import datetime, timezone

from app.contracts.common import ConfidenceKind, Evidence, ProviderError, ProviderResult


def test_confidence_kind_has_three_states():
    """The product doc (section 4) and ADR-007 require exactly these three states."""
    assert ConfidenceKind.VERIFIED == "VERIFIED"
    assert ConfidenceKind.ESTIMATED == "ESTIMATED"
    assert ConfidenceKind.AI_SUGGESTION == "AI_SUGGESTION"
    assert {k.value for k in ConfidenceKind} == {
        "VERIFIED", "ESTIMATED", "AI_SUGGESTION",
    }


def test_evidence_required_fields():
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    ev = Evidence(
        entity_type="poi",
        entity_id="abc",
        field_name="opening_hours",
        value_json='{"mon":"09:00-17:00"}',
        source="official_website",
        observed_at=now,
        confidence_kind=ConfidenceKind.VERIFIED,
    )
    assert ev.field_name == "opening_hours"
    assert ev.confidence_kind is ConfidenceKind.VERIFIED
    assert ev.errors == []
    assert ev.expires_at is None
    assert ev.source_url is None


def test_provider_result_generic_round_trip():
    """A parameterized ProviderResult must dump and re-parse preserving the data type."""
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    result = ProviderResult[list[int]](
        data=[1, 2, 3],
        source="mock",
        observed_at=now,
        confidence_kind=ConfidenceKind.VERIFIED,
    )
    dumped = result.model_dump()
    parsed = ProviderResult[list[int]].model_validate(dumped)
    assert parsed.data == [1, 2, 3]
    assert parsed.source == "mock"
    assert parsed.errors == []


def test_provider_result_carries_degraded_errors():
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    result = ProviderResult[list[int]](
        data=[],
        source="google_places",
        observed_at=now,
        confidence_kind=ConfidenceKind.ESTIMATED,
        errors=[ProviderError(code="places_unavailable", message="no key", retryable=True)],
    )
    assert result.data == []
    assert result.errors[0].code == "places_unavailable"
    assert result.errors[0].retryable is True
