import asyncio
import logging

import httpx
import pytest

from app.contracts.poi import PoiSearchQuery
from app.providers.amap_search import AmapSearchProvider


def row(identity="B001", **kwargs):
    return {"id": identity, "name": "测试博物馆", "location": "104.08,30.66", "cityname": "成都市",
            "typecode": "140100", "type": "科教文化服务;博物馆", **kwargs}


def run(handler, limit=5):
    return asyncio.run(AmapSearchProvider(api_key="test-secret", transport=httpx.MockTransport(handler)).search_pois(
        PoiSearchQuery(city_name="成都", text_query="博物馆", max_results=limit)))


def test_valid_poi_strict_city_provenance_unknown_fields(caplog):
    caplog.set_level(logging.INFO, logger="httpx")
    def handler(request):
        assert request.url.params["city_limit"] == "true"
        assert request.url.params["region"] == "成都"
        return httpx.Response(200, json={"status": "1", "pois": [row(), row("foreign", cityname="北京市"), row()]})
    result = run(handler)
    assert len(result.data) == 1
    poi = result.data[0]
    assert poi.coordinate_system == "GCJ02"
    assert poi.latitude == 30.66 and poi.longitude == 104.08
    assert poi.ticket_price is None and poi.rating is None and poi.opening_hours is None
    assert poi.recommended_duration_minutes is None
    assert poi.evidence and "test-secret" not in caplog.text


@pytest.mark.parametrize("payload", [
    row(location="bad"), row(location="0,0"), row(location="nan,30"),
    row(id=""), row(name=""), row(name="博物馆停车场"), row(cityname=[]),
])
def test_bad_or_outside_pois_are_ignored(payload):
    result = run(lambda request: httpx.Response(200, json={"status": "1", "pois": [payload]}))
    assert result.data == []


@pytest.mark.parametrize("code", ["10001", "10003", "10009"])
def test_auth_quota_permission_failures_do_not_raise(code):
    result = run(lambda request: httpx.Response(200, json={"status": "0", "infocode": code, "info": "test-secret"}))
    assert not result.data and result.errors[0].code == "amap_" + code
    assert "test-secret" not in result.model_dump_json()


def test_timeout_degrades():
    def handler(request):
        raise httpx.ReadTimeout("test-secret", request=request)
    result = run(handler)
    assert result.errors[0].code == "timeout"


def test_missing_key_never_sends_request():
    def handler(request):
        pytest.fail("should not send a request")
    result = asyncio.run(AmapSearchProvider(api_key="", transport=httpx.MockTransport(handler)).search_pois(
        PoiSearchQuery(city_name="成都", text_query="博物馆")))
    assert result.errors[0].code == "missing_key"


def test_page_limit_and_stable_deduplication():
    pages = []
    def handler(request):
        page = int(request.url.params["page_num"])
        pages.append(page)
        return httpx.Response(200, json={"status": "1", "pois": [row(str(i)) for i in range((page-1)*25, page*25)]})
    result = run(handler, 30)
    assert pages == [1, 2] and len(result.data) == 30


def test_average_spend_is_not_ticket_price():
    result = run(lambda request: httpx.Response(200, json={"status": "1", "pois": [row(
        business={"cost": "88", "rating": "4.6", "opentime_today": "09:00-17:00"})]}))
    poi = result.data[0]
    assert poi.average_spend == 88 and poi.ticket_price is None
    assert poi.opening_hours == {"opentime_today": "09:00-17:00"}
    assert poi.closing_time is None


def test_invalid_payload_degrades():
    result = run(lambda request: httpx.Response(200, text="not-json"))
    assert result.errors[0].code == "connection_or_payload_error"
