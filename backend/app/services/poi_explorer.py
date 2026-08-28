import concurrent.futures
import math
import os

import requests

from app.services.coord import gcj02_str_to_wgs84_str, wgs84_str_to_gcj02_str
from app.services.dalian import scenario_key
from app.services.geocoder import resolve_location
from app.services.route_engine import throttle_amap

POI_URL = "https://restapi.amap.com/v3/place/around"

# 沿基准路线按里程取样的位置。只取中点会漏掉起终点附近的一大段，
# 而"偶遇"恰恰不该只发生在正中间。
SAMPLE_FRACTIONS = (0.25, 0.50, 0.75)
# 高德对同一个 Key 有并发上限，采样点之间共用 route_engine 的限流器，
# 线程数保持小值：并发开大只会互相排队并触发限流重试。
SAMPLE_MAX_WORKERS = 2

# 低于这个评分的地方不值得让用户绕路（"偶遇"必须是好的偶遇）。
# 高德无评分数据的 POI 一并排除：说不清好不好，就不该拿它当推荐理由。
MIN_RATING = 3.5

# 评分门槛挡不住的类别噪声：实测便利店 4.0、烟酒专卖店 4.2 都能过 3.5，
# 但推荐用户"偶遇一家烟酒店"这个叙事就垮了。按 type 串关键词排除。
EXCLUDED_TYPE_KEYWORDS = (
    "便利店",
    "便民商店",
    "超市",
    "超级市场",
    "购物相关场所",
    "烟酒",
    "农副产品",
    "果品市场",
    "综合市场",
    "建材",
    "五金",
    "汽车",
    "加油",
    "药店",
    "医药",
)


def explore_pois_along_route(
    origin: str,
    destination: str,
    types: list[str],
    radius: int = 300,
    polyline: str | None = None,
) -> list[dict]:
    """沿路线找值得停一下的地方。

    传入 `polyline`（基准路线的 WGS-84 折线）时按里程 25%/50%/75% 三点各查一次，
    按 name 去重合并；没有折线时退回起终点中点单点查询。
    """
    sample_points = _sample_points(origin, destination, polyline)

    if os.getenv("AMAP_KEY"):
        found = _query_samples(sample_points, types, radius)
        if found:
            return found

    fallback = _dalian_fallback_pois(origin, destination) or []
    return [poi for poi in fallback if any(t in poi.get("type", "") for t in types)]


def _sample_points(origin: str, destination: str, polyline: str | None) -> list[str]:
    """取样点（WGS-84 "lng,lat" 字符串），按里程比例分布在折线上。"""
    points = _polyline_points(polyline)

    if len(points) >= 2:
        sampled = [_point_at_fraction(points, fraction) for fraction in SAMPLE_FRACTIONS]
        unique: list[str] = []
        for point in sampled:
            if point and point not in unique:
                unique.append(point)
        if unique:
            return unique

    # 没有可用折线：退回起终点中点。
    lng1, lat1 = map(float, resolve_location(origin).split(",", 1))
    lng2, lat2 = map(float, resolve_location(destination).split(",", 1))
    return [f"{(lng1 + lng2) / 2},{(lat1 + lat2) / 2}"]


def _polyline_points(polyline: str | None) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for chunk in str(polyline or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            lng, lat = (float(part) for part in chunk.split(",", 1))
        except (TypeError, ValueError):
            continue
        if math.isfinite(lng) and math.isfinite(lat):
            points.append((lng, lat))
    return points


def _point_at_fraction(points: list[tuple[float, float]], fraction: float) -> str | None:
    """折线上按累计里程取 fraction 处的点，落在线段内则线性插值。"""
    spans = [_flat_distance(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total = sum(spans)
    if total <= 0:
        lng, lat = points[0]
        return f"{lng},{lat}"

    target = total * fraction
    walked = 0.0
    for index, span in enumerate(spans):
        if walked + span >= target:
            ratio = (target - walked) / span if span > 0 else 0.0
            (lng1, lat1), (lng2, lat2) = points[index], points[index + 1]
            return f"{lng1 + (lng2 - lng1) * ratio:.6f},{lat1 + (lat2 - lat1) * ratio:.6f}"
        walked += span

    lng, lat = points[-1]
    return f"{lng},{lat}"


def _flat_distance(start: tuple[float, float], end: tuple[float, float]) -> float:
    """够用的平面近似距离：只用来在折线上分配比例，不对外报里程。"""
    lng_scale = math.cos(math.radians((start[1] + end[1]) / 2))
    return math.hypot((end[0] - start[0]) * lng_scale, end[1] - start[1])


def _query_samples(sample_points: list[str], types: list[str], radius: int) -> list[dict]:
    """并发查询各取样点，按 name 去重合并（同名保留评分高的那个）。"""
    if len(sample_points) == 1:
        results = [_query_around(sample_points[0], types, radius)]
    else:
        workers = min(SAMPLE_MAX_WORKERS, len(sample_points))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(lambda point: _query_around(point, types, radius), sample_points))

    merged: dict[str, dict] = {}
    for batch in results:
        for poi in batch:
            key = poi.get("name") or ""
            existing = merged.get(key)
            if existing is None or poi["rating"] > existing["rating"]:
                merged[key] = poi
    return list(merged.values())


def _query_around(location_wgs: str, types: list[str], radius: int) -> list[dict]:
    """单个取样点的周边查询。任一点失败不影响其他点。"""
    # 入参是 WGS-84，发给高德要 GCJ-02。
    params = {
        "location": wgs84_str_to_gcj02_str(location_wgs) or location_wgs,
        "types": "|".join(types),
        "radius": radius,
        "offset": 20,
        "page": 1,
        "key": os.getenv("AMAP_KEY"),
    }

    try:
        throttle_amap()
        response = requests.get(POI_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, TypeError, ValueError, AttributeError):
        return []

    pois = data.get("pois", []) if isinstance(data, dict) else []
    filtered = []
    for poi in pois:
        if not isinstance(poi, dict):
            continue
        poi_type = poi.get("type", "")
        # 这里**不再**按 types 复筛一遍。高德服务端已经按 types 筛过，而本地
        # 用 `"景点" in poi_type` 复筛会把整个景点类别砍光：高德实际返回的是
        # 「风景名胜;公园广场;公园」「风景名胜;风景名胜;世界遗产」，串里根本
        # 没有「景点」二字。请求侧接受模糊词，返回侧的分类名是另一套词表。
        # 类别噪声由 EXCLUDED_TYPE_KEYWORDS + MIN_RATING 负责，那两道够了。
        normalized = _normalize_amap_poi(poi, poi_type)
        if _is_worth_recommending(poi_type, normalized["rating"]):
            filtered.append(normalized)
    return filtered


def _normalize_amap_poi(poi: dict, poi_type: str) -> dict:
    """高德 POI -> 对外结构。location 从 GCJ-02 转成 WGS-84，评分从 biz_ext 里取。"""
    location = poi.get("location")
    return {
        "name": poi.get("name"),
        "type": poi_type,
        "distance": poi.get("distance"),
        "rating": _extract_rating(poi),
        "location": gcj02_str_to_wgs84_str(location) or location,
    }


def _extract_rating(poi: dict) -> float:
    """取 POI 评分。

    高德把评分放在 `biz_ext.rating`，**顶层没有 rating 字段**，
    之前读顶层导致所有 POI 评分恒为 0、打分退化。两个解析陷阱：
      * 值是字符串 `'4.8'`，要转 float
      * 无数据时 `biz_ext` 的字段会是空数组 `[]`（不是 null），`float([])` 会抛异常
    """
    biz_ext = poi.get("biz_ext")
    candidates = []
    if isinstance(biz_ext, dict):
        candidates.append(biz_ext.get("rating"))
    candidates.append(poi.get("rating"))  # 兼容回退

    for value in candidates:
        if value is None or isinstance(value, (list, tuple, dict)):
            continue
        try:
            rating = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(rating) or rating <= 0:
            continue
        return min(5.0, rating)

    return 0.0


def _is_worth_recommending(poi_type: str, rating: float) -> bool:
    """够好、且属于会让人愿意停一下的类别。"""
    if rating < MIN_RATING:
        return False
    return not any(keyword in poi_type for keyword in EXCLUDED_TYPE_KEYWORDS)


# 断网兜底的沿线亮点。key 与 route_engine.DALIAN_SCENARIOS 共用 dalian.scenario_key，
# 所以不会出现「路线表改了、POI 表没改」的静默退化。
# 店名、type、rating、location 全部来自高德实测（location 已转成 WGS-84），
# distance 是该点到兜底折线的最近距离，不是编的。
DALIAN_POI_SCENARIOS = {
    scenario_key("dut", "xinghai"): [
        {
            "name": "香海金波海鲜烧烤(西南路店)",
            "type": "餐饮服务;中餐厅;海鲜酒楼",
            "distance": "70",
            "rating": 4.6,
            "location": "121.554782,38.887539",
        },
        {
            "name": "瑞幸咖啡(大连软件园22号楼店)",
            "type": "餐饮服务;咖啡厅;咖啡厅",
            "distance": "7",
            "rating": 4.3,
            "location": "121.539956,38.887705",
        },
    ],
    scenario_key("donggang", "laohutan"): [
        {
            "name": "蒙亘花·呼盟全羊(中南路店)",
            "type": "餐饮服务;中餐厅;特色/地方风味餐厅",
            "distance": "32",
            "rating": 4.6,
            "location": "121.671643,38.888473",
        },
        {
            "name": "老虎滩船说",
            "type": "餐饮服务;中餐厅;海鲜酒楼",
            "distance": "7",
            "rating": 4.5,
            "location": "121.672093,38.888650",
        },
    ],
    scenario_key("xianlu", "fujiazhuang"): [
        {
            "name": "钱库里海鲜自助(星海广场店)",
            "type": "餐饮服务;中餐厅;中餐厅",
            "distance": "179",
            "rating": 4.7,
            "location": "121.588223,38.883247",
        },
        {
            "name": "森垚韩小馆",
            "type": "餐饮服务;中餐厅;中餐厅",
            "distance": "128",
            "rating": 4.6,
            "location": "121.588400,38.899552",
        },
    ],
}


def _dalian_fallback_pois(origin: str, destination: str) -> list[dict] | None:
    route_key = f"{_normalize(coord=origin)}->{_normalize(coord=destination)}"
    reverse_key = f"{_normalize(coord=destination)}->{_normalize(coord=origin)}"

    selected = DALIAN_POI_SCENARIOS.get(route_key) or DALIAN_POI_SCENARIOS.get(reverse_key)
    return selected


def _normalize(coord: str | None) -> str:
    if not coord:
        return ""
    lng, lat = str(coord).split(",", 1)
    return f"{float(lng):.4f},{float(lat):.4f}"
