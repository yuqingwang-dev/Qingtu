"""TripPilot provider layer.

Provider ports and adapters return `ProviderResult` envelopes (see
docs/trippilot_architecture.md section 3.1). Phase 1.1 ships only the
`SearchProvider` port plus a `MockSearchProvider` and a non-breaking
`GoogleSearchAdapter` that wraps the existing `places_service`.

Other ports (MapProvider, TransportProvider, WeatherProvider, CrowdProvider,
BookingProvider, LLMProvider) are defined in Phase 1.2 (M2) and are intentionally
not implemented here.
"""
from app.providers.base import SearchProvider
from app.providers.google_search_adapter import GoogleSearchAdapter
from app.providers.mock_search import MockSearchProvider

__all__ = ["SearchProvider", "MockSearchProvider", "GoogleSearchAdapter"]
