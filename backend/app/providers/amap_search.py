"""AMap v5 POI search; transport errors degrade without leaking the Key."""
import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.contracts.common import ConfidenceKind, Evidence, ProviderError, ProviderResult
from app.contracts.poi import PoiIdentifier, PoiPracticalInfo, PoiSearchQuery


class _RedactKey(logging.Filter):
    def filter(self, record):
        if "restapi.amap.com" in record.getMessage():
            record.msg = re.sub(r"([?&]key=)[^&\s\"']+", r"\1[REDACTED]", record.getMessage())
            record.args = ()
        return True


for _name in ("httpx", "httpx2", "httpcore"):
    logging.getLogger(_name).addFilter(_RedactKey())


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


class AmapSearchProvider:
    SOURCE = "amap"

    def __init__(self, api_key=None, transport=None):
        self.api_key = settings.AMAP_WEB_SERVICE_KEY if api_key is None else api_key
        self.transport = transport

    def _result(self, data, errors=None):
        now = datetime.now(timezone.utc)
        return ProviderResult(data=data, source=self.SOURCE, observed_at=now,
            expires_at=now + timedelta(seconds=settings.POI_CACHE_TTL_SECONDS),
            confidence_kind=ConfidenceKind.VERIFIED if data else ConfidenceKind.ESTIMATED,
            errors=errors or [])

    async def _request(self, path, params):
        if not self.api_key:
            return None, ProviderError(code="missing_key", message="未配置高德 Web 服务 Key")
        try:
            async with httpx.AsyncClient(timeout=settings.POI_TIMEOUT_SECONDS, transport=self.transport) as client:
                response = await client.get("https://restapi.amap.com/v5/place/" + path,
                                            params={**params, "key": self.api_key, "show_fields": "business"})
            if response.status_code != 200:
                return None, ProviderError(code="http_error", message="地点服务暂不可用", retryable=True)
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("invalid payload")
            if str(data.get("status")) != "1":
                code = str(data.get("infocode", "unknown"))
                return None, ProviderError(code="amap_" + code if code.isdigit() else "amap_error",
                    message="高德搜索失败，请检查 Key 类型、接口权限或额度", retryable=False)
            return data, None
        except httpx.TimeoutException:
            return None, ProviderError(code="timeout", message="地点搜索超时", retryable=True)
        except Exception:
            return None, ProviderError(code="connection_or_payload_error", message="地点服务连接或数据异常", retryable=True)

    async def search_pois(self, query: PoiSearchQuery):
        if not query.city_name:
            return self._result([], [ProviderError(code="missing_city", message="必须限定搜索城市")])
        limit = min(50, max(1, query.max_results))
        found, seen, errors = [], set(), []
        for page in range(1, 3):
            data, error = await self._request("text", {"region": query.city_name, "city_limit": "true",
                "keywords": (query.explicit_query or query.text_query or "景点")[:80],
                "page_size": min(25, limit), "page_num": page})
            if error:
                errors.append(error)
                break
            rows = data.get("pois", [])
            if not isinstance(rows, list):
                errors.append(ProviderError(code="invalid_payload", message="地点列表格式错误"))
                break
            for row in rows:
                poi = self._map(row)
                if not poi or poi.identifier.provider_poi_id in seen:
                    continue
                # Strict city_limit plus a defensive returned-city check.
                if not poi.city_name or poi.city_name.removesuffix("市") != query.city_name.removesuffix("市"):
                    continue
                seen.add(poi.identifier.provider_poi_id)
                found.append(poi)
            if len(found) >= limit or len(rows) < min(25, limit):
                break
        return self._result(found[:limit], errors)

    async def get_poi_details(self, poi_id: str):
        data, error = await self._request("detail", {"id": poi_id})
        poi = self._map(data["pois"][0]) if data and isinstance(data.get("pois"), list) and data["pois"] else None
        return self._result(poi or PoiPracticalInfo(identifier=PoiIdentifier(provider="amap", provider_poi_id=poi_id), name=""),
                            [error] if error else [] if poi else [ProviderError(code="not_found", message="未找到地点")])

    def _map(self, row):
        if not isinstance(row, dict):
            return None
        name, identity = _text(row.get("name")), _text(row.get("id"))
        if not name or not identity or any(word in name for word in ("停车场", "售票处", "检票口", "出入口", "卫生间")):
            return None
        try:
            longitude, latitude = map(float, _text(row.get("location")).split(","))
            if not (73 <= longitude <= 135 and 18 <= latitude <= 54):
                return None
        except (ValueError, TypeError):
            return None
        business = row.get("business") if isinstance(row.get("business"), dict) else {}
        rating = _number(business.get("rating"))
        rating = rating if rating is not None and rating <= 5 else None
        category = None
        code, type_name = _text(row.get("typecode")), _text(row.get("type"))
        if code.startswith("05"):
            category = "food"
        elif code.startswith("06"):
            category = "shopping"
        elif "公园" in type_name or "公园" in name or "自然" in type_name:
            category = "nature"
        elif code.startswith(("11", "14")):
            category = "culture"
        elif "酒吧" in type_name:
            category = "nightlife"
        elif code.startswith("08"):
            category = "adventure"
        now = datetime.now(timezone.utc)
        values = dict(name=name, latitude=latitude, longitude=longitude, coordinate_system="GCJ02",
            city_name=_text(row.get("cityname")), address=_text(row.get("address")) or None,
            provider_type=type_name or None, category=category, rating=rating,
            average_spend=_number(business.get("cost")))
        # Today's raw hours are not reused as future-trip operating hours.
        hours = {k: business[k] for k in ("opentime_today", "opentime_week") if _text(business.get(k))}
        if hours:
            values["opening_hours"] = hours
        evidence = [Evidence(entity_type="poi", entity_id=identity, field_name=key,
            value_json=json.dumps(value, ensure_ascii=False), source="amap", observed_at=now,
            expires_at=now + timedelta(seconds=settings.POI_CACHE_TTL_SECONDS), confidence_kind=ConfidenceKind.VERIFIED)
            for key, value in values.items() if value is not None and key != "category"]
        return PoiPracticalInfo(identifier=PoiIdentifier(provider="amap", provider_poi_id=identity),
                                evidence=evidence, **values)
