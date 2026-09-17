"""Provider port definitions.

Phase 1.1 implements only `SearchProvider`. The remaining ports are listed as
comments to document the intended surface (to be added in Phase 1.2 / M2). They
are deliberately not turned into Protocol stubs yet so that imports stay clean
and the scope stays minimal.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.contracts.common import ProviderResult
from app.contracts.poi import PoiPracticalInfo, PoiSearchQuery


@runtime_checkable
class SearchProvider(Protocol):
    """Provider-agnostic POI search/details port.

    Implementations MUST NOT raise on timeout, rate-limit, empty results or HTTP
    non-200; they return a degraded `ProviderResult` (empty `data` + `errors`)
    instead. Per ADR-007, fields that cannot be verified stay `None` on each
    returned `PoiPracticalInfo` — never fabricated.
    """

    async def search_pois(self, query: PoiSearchQuery) -> ProviderResult[list[PoiPracticalInfo]]:
        """Search POIs matching `query`. Returns at most `query.max_results`."""
        ...

    async def get_poi_details(self, poi_id: str) -> ProviderResult[PoiPracticalInfo]:
        """Fetch practical details for a single POI by its provider id."""
        ...


# Ports planned for Phase 1.2 (M2) — intentionally not implemented:
#
#   MapProvider.geocode() / route_matrix() / route_geometry()
#   TransportProvider.options() / last_service()
#   WeatherProvider.forecast()
#   CrowdProvider.crowd_level() / queue_estimate()
#   BookingProvider.search() / check_price() / check_availability()
#       / create_order() / cancel_order()   (human-in-the-loop, ADR-010)
#   LLMProvider.extract_preferences() / classify_replan_intent() / explain_plan()
