import asyncio
import httpx
import pytest

from app.config import settings
from app.providers import amap_routes as routes


def point(identity, lon):
    return dict(id=identity, name=f"p{identity}", longitude=lon, latitude=30.66, verified=True)


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(settings, "AMAP_WEB_SERVICE_KEY", "route-test-secret")
    monkeypatch.setattr(settings, "ROUTE_MAX_REQUESTS", 100)
    monkeypatch.setattr(routes.cache, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(routes.cache, "set", AsyncMock())
    routes._memory.clear()


@pytest.mark.parametrize("mode,path", [("walking", "walking"), ("taxi", "driving"), ("self_drive", "driving")])
def test_modes_seconds_geometry_and_directed_cache(mode, path):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.url.path.endswith(path)
        return httpx.Response(200, json={"status": "1", "route": {"paths": [{"duration": "121", "distance": "800", "steps": [{"polyline": "104.08,30.66;104.09,30.66", "instruction": "向东步行"}]}]}})
    provider = routes.AmapRouteProvider(httpx.MockTransport(handler), interval=0, city_name="成都市")
    async def check():
        a, b = point(1,104.08), point(2,104.09)
        first = await provider.route(a,b,mode)
        assert first["source"] == "amap" and first["duration_minutes"] == 3
        assert first["geometry"] and first["distance_meters"] == 800
        assert (await provider.route(a,b,mode))["cache_hit"] is True
        await provider.route(b,a,mode)
        assert len(requests) == 2
    asyncio.run(check())


@pytest.mark.parametrize("city_name", ["北京市", "上海市", "杭州市", "成都市"])
def test_transit_contains_walk_and_bus_geometry(city_name):
    def handler(request):
        assert request.url.params["city"] == city_name
        assert request.url.params["cityd"] == city_name
        return httpx.Response(200, json={"status":"1", "route":{"transits":[{"duration":"900", "segments":[{
            "walking":{"distance":"100", "steps":[{"polyline":"104.08,30.66;104.081,30.66"}]},
            "railway":{"via_stops":[],"alters":[],"spaces":[]}, "taxi":[],
            "bus":{"buslines":[{"name":"地铁2号线", "distance":"2000", "polyline":"104.081,30.66;104.1,30.66"}]}
        }]}]}})
    provider = routes.AmapRouteProvider(httpx.MockTransport(handler), interval=0, city_name=city_name)
    leg = asyncio.run(provider.route(point(1,104.08), point(2,104.1), "public_transport"))
    assert leg["duration_minutes"] == 15 and leg["distance_meters"] == 2100
    assert len(leg["geometry"]) == 2 and "乘坐 地铁2号线" in leg["instructions"]


@pytest.mark.parametrize("status,payload", [(500, {}), (200,{"status":"1","route":{"paths":[]}}),
                                           (200,{"status":"0","infocode":"10003"})])
def test_error_does_not_invent_road_geometry(status, payload):
    provider = routes.AmapRouteProvider(httpx.MockTransport(lambda r: httpx.Response(status,json=payload)), interval=0, city_name="成都市")
    leg = asyncio.run(provider.route(point(1,104.08), point(2,104.1), "walking"))
    assert leg["source"] == "estimated" and leg["geometry"] == [] and leg["error_code"]


def test_quota_failure_stops_further_requests():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"status":"0","infocode":"10003"})
    provider = routes.AmapRouteProvider(httpx.MockTransport(handler), interval=0, city_name="成都市")
    async def check():
        await provider.route(point(1,104.08), point(2,104.1), "walking")
        await provider.route(point(2,104.1), point(1,104.08), "walking")
    asyncio.run(check())
    assert len(calls) == 1


def test_budget_and_unknown_coordinates_do_not_call_network(monkeypatch):
    monkeypatch.setattr(settings, "ROUTE_MAX_REQUESTS", 0)
    def handler(request):
        pytest.fail("must not query")
    provider = routes.AmapRouteProvider(httpx.MockTransport(handler), interval=0, city_name="成都市")
    leg = asyncio.run(provider.route(point(1,104.08),point(2,104.1),"walking"))
    assert leg["error_code"] == "request_budget"
    a = point(1,104.08)
    a["verified"] = False
    leg = asyncio.run(provider.route(a,point(2,104.1),"walking"))
    assert leg["error_code"] == "unverified_coordinates"


def test_short_transit_gap_queries_real_walking_instead_of_guessing():
    paths = []
    def handler(request):
        paths.append(request.url.path)
        data = {"transits":[]} if request.url.path.endswith("integrated") else {"paths":[{"duration":"300","distance":"400","steps":[]}]}
        return httpx.Response(200,json={"status":"1","route":data})
    provider = routes.AmapRouteProvider(httpx.MockTransport(handler),interval=0, city_name="成都市")
    leg = asyncio.run(provider.route(point(1,104.08),point(2,104.081),"public_transport"))
    assert len(paths) == 2 and leg["mode"] == "walking" and leg["source"] == "amap"
