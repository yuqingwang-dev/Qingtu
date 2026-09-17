import asyncio

import httpx
import pytest

from app.api.schemas import CityResponse, TripPreferences
from app.core.route_cities import ROUTE_CITIES
from app.providers import amap_routes as routes


@pytest.mark.parametrize("name,domestic,supported", [
    ("Beijing",True,True), ("Shanghai",True,True), ("Hangzhou",True,True), ("Chengdu",True,True),
    ("Paris",False,False), ("Tokyo",False,False), ("Beijing",False,False), ("Unlisted",True,False),
])
def test_api_capability_flag_matches_backend(name, domestic, supported):
    city = CityResponse(id=1,name=name,country="China" if domestic else "France",
                        time_zone="UTC",default_currency="CNY",is_domestic=domestic)
    assert city.model_dump()["supports_real_routes"] is supported


def test_city_is_part_of_route_cache_key(monkeypatch):
    from unittest.mock import AsyncMock
    from app.config import settings
    monkeypatch.setattr(settings,"AMAP_WEB_SERVICE_KEY","test")
    monkeypatch.setattr(routes.cache,"get",AsyncMock(return_value=None))
    monkeypatch.setattr(routes.cache,"set",AsyncMock())
    routes._memory.clear()
    calls = []
    def handler(request):
        calls.append(request.url.params["city"])
        return httpx.Response(200,json={"status":"1","route":{"transits":[{"duration":"600","segments":[]}]}})
    origin = dict(id=1,name="test",latitude=30.6,longitude=104,verified=True)
    destination = dict(id=2,name="test2",latitude=30.7,longitude=104.1,verified=True)
    async def check():
        for city in ["北京市","上海市","北京市"]:
            provider = routes.AmapRouteProvider(httpx.MockTransport(handler),interval=0,city_name=city)
            await provider.route(origin,destination,"public_transport")
    asyncio.run(check())
    assert calls == ["北京市","上海市"]
    routes._memory.clear()


def test_lodging_from_another_city_is_rejected():
    with pytest.raises(ValueError):
        TripPreferences(destination_city_id=1,start_date="2026-10-01",end_date="2026-10-03",
            trip_type="weekend",budget_level="medium",energy_level="moderate",travel_mode="public_transport",
            use_real_routes=True,lodging={"name":"wrong city", "city_id":2,"latitude":31.2,"longitude":121.5})
