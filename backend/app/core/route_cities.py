"""Single capability registry for currently supported domestic route cities."""
ROUTE_CITIES = {
    "Beijing": "北京市",
    "Shanghai": "上海市",
    "Hangzhou": "杭州市",
    "Chengdu": "成都市",
}


def supports_real_routes(name: str, is_domestic: bool) -> bool:
    return is_domestic and name in ROUTE_CITIES
