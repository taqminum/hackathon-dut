import concurrent.futures
import math
import os

import requests

from app.services.coord import gcj02_str_to_wgs84_str, wgs84_str_to_gcj02_str
from app.services.dalian import scenario_key
from app.services.geocoder import resolve_location
from app.services.route_engine import throttle_amap

POI_URL = "https://restapi.amap.com/v3/place/around"

# 沿线搜索必须形成近似连续的走廊。采样点数量随路线长度和搜索半径变化，
# 同时设上限保护高德配额；起终点本身不搜，避免把出发地/目的地周围的普通地点
# 当成「途中偶遇」。
MIN_SAMPLE_POINTS = 3
MAX_SAMPLE_POINTS = 10
LEGACY_SAMPLE_FRACTIONS = (0.25, 0.50, 0.75)
# 高德对同一个 Key 有并发上限，采样点之间共用 route_engine 的限流器，
# 线程数保持小值：并发开大只会互相排队并触发限流重试。
SAMPLE_MAX_WORKERS = 2

# 有评分时低于这个门槛就不推荐；没有评分不能一刀切掉，因为公园、展馆、历史建筑
# 等非商业地点经常没有评分。无评分候选仍会在后续按类别、距离和用户偏好参与排序，
# 页面也会如实显示「高德暂无评分」，不会编造分数。
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
    *,
    allow_fallback: bool = True,
    strict: bool = False,
) -> list[dict]:
    """沿路线找值得停一下的地方。

    正式调用传入 `polyline`（基准路线的 WGS-84 折线）时按路线长度自适应采样，
    形成有重叠的搜索走廊并按高德 POI id 去重；没有折线时退回中点单点查询。
    """
    sample_points = _sample_points(origin, destination, polyline, radius, adaptive=strict)

    if os.getenv("AMAP_KEY"):
        found = _query_samples(sample_points, types, radius, strict=strict)
        if found:
            return found

    if not allow_fallback:
        return []

    fallback = _dalian_fallback_pois(origin, destination) or []
    return [poi for poi in fallback if any(t in poi.get("type", "") for t in types)]


def _sample_points(
    origin: str,
    destination: str,
    polyline: str | None,
    radius: int = 300,
    *,
    adaptive: bool = False,
) -> list[str]:
    """取样点（WGS-84 "lng,lat" 字符串），按里程比例分布在折线上。"""
    points = _polyline_points(polyline)

    if len(points) >= 2:
        if adaptive:
            total_meters = _polyline_length_meters(points)
            # 相邻圆心最多约 1.5 个半径，保证圆之间有重叠，弯路上也不留下明显空洞。
            spacing = max(200.0, float(radius) * 1.5)
            count = max(MIN_SAMPLE_POINTS, min(MAX_SAMPLE_POINTS, math.ceil(total_meters / spacing)))
            fractions = [(index + 1) / (count + 1) for index in range(count)]
        else:
            # 兼容离线/单元回归；正式推荐 strict=True，一定走上面的自适应走廊。
            fractions = LEGACY_SAMPLE_FRACTIONS
        sampled = [_point_at_fraction(points, fraction) for fraction in fractions]
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


def _polyline_length_meters(points: list[tuple[float, float]]) -> float:
    return sum(_haversine_meters(points[index], points[index + 1]) for index in range(len(points) - 1))


def _haversine_meters(start: tuple[float, float], end: tuple[float, float]) -> float:
    lng1, lat1 = map(math.radians, start)
    lng2, lat2 = map(math.radians, end)
    delta_lng = lng2 - lng1
    delta_lat = lat2 - lat1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return 6_371_000 * 2 * math.asin(math.sqrt(value))


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


def _query_samples(
    sample_points: list[str],
    types: list[str],
    radius: int,
    *,
    strict: bool = False,
) -> list[dict]:
    """并发查询各取样点，按 name 去重合并（同名保留评分高的那个）。"""
    if len(sample_points) == 1:
        results = [_query_around(sample_points[0], types, radius, strict=strict)]
    else:
        workers = min(SAMPLE_MAX_WORKERS, len(sample_points))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(
                executor.map(
                    lambda point: _query_around(point, types, radius, strict=strict),
                    sample_points,
                )
            )

    merged: dict[str, dict] = {}
    for batch in results:
        for poi in batch:
            key = poi.get("id") or f"{poi.get('name') or ''}|{poi.get('location') or ''}"
            existing = merged.get(key)
            if existing is None or poi["rating"] > existing["rating"]:
                merged[key] = poi
    return list(merged.values())


def _query_around(
    location_wgs: str,
    types: list[str],
    radius: int,
    *,
    strict: bool = False,
) -> list[dict]:
    """单个取样点的周边查询。任一点失败不影响其他点。"""
    # 入参是 WGS-84，发给高德要 GCJ-02。
    params = {
        "location": wgs84_str_to_gcj02_str(location_wgs) or location_wgs,
        "types": "|".join(types),
        "radius": radius,
        "sortrule": "weight",
        "offset": 20,
        "page": 1,
        # R6：不传这个的话响应里只有 name/type/distance/location 和 biz_ext.rating，
        # 地址、电话、营业时间、照片一个都不回来 —— 卡片展开就没有东西可展。
        # 同一次请求，不额外计费，代价只是响应变大。
        "extensions": "all",
        "key": os.getenv("AMAP_KEY"),
    }

    try:
        throttle_amap()
        response = requests.get(POI_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, TypeError, ValueError, AttributeError) as exc:
        if strict:
            raise RuntimeError(f"高德地点搜索失败：{exc}") from exc
        return []

    invalid_status = not isinstance(data, dict) or (
        (strict or "status" in data) and str(data.get("status")) != "1"
    )
    if invalid_status:
        if strict:
            info = data.get("info") if isinstance(data, dict) else "响应格式错误"
            infocode = data.get("infocode") if isinstance(data, dict) else ""
            raise RuntimeError(f"高德地点搜索失败：{info or '未知错误'} ({infocode})")
        return []

    pois = data.get("pois", []) if isinstance(data, dict) else []
    filtered = []
    for poi in pois:
        if not isinstance(poi, dict):
            continue
        poi_type = poi.get("type", "")
        if not isinstance(poi.get("name"), str) or not poi["name"].strip():
            continue
        if not isinstance(poi_type, str) or not poi_type.strip():
            continue
        if not isinstance(poi.get("location"), str) or "," not in poi["location"]:
            continue
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
    """高德 POI -> 对外结构。location 从 GCJ-02 转成 WGS-84，评分从 biz_ext 里取。

    R6：后四个字段（address / tel / opentime / photo）是给前端卡片展开用的。
    取不到就是空串 —— **不编造**，前端见空串整行不渲染，不摆「暂无」占位。
    """
    location = poi.get("location")
    biz_ext = poi.get("biz_ext")
    return {
        "id": _extract_text(poi.get("id")),
        "name": poi.get("name"),
        "type": poi_type,
        "typecode": _extract_text(poi.get("typecode")),
        "distance": poi.get("distance"),
        "rating": _extract_rating(poi),
        "location": gcj02_str_to_wgs84_str(location) or location,
        "navigation_location": gcj02_str_to_wgs84_str(
            _extract_text(poi.get("entr_location")) or location
        ) or location,
        "source": "amap",
        "address": _extract_text(poi.get("address")),
        "tel": _extract_text(poi.get("tel")),
        # 营业时间在 biz_ext 里，和 rating 同一个坑（见 _extract_rating）
        "opentime": _extract_text(
            biz_ext.get("opentime") if isinstance(biz_ext, dict) else None
        ),
        "cost": _extract_text(biz_ext.get("cost") if isinstance(biz_ext, dict) else None),
        "photo": _extract_photo(poi.get("photos")),
    }


def _extract_text(value) -> str:
    """高德的文本字段 -> 干净的字符串，取不到就是空串。

    R6：无数据时高德给的是**空数组** `[]` 而不是 `null`（`_extract_rating` 的
    注释里已经记过这个坑），`str([])` 会得到字面量 `'[]'` 印到屏幕上。
    另有两种形态要收：`address` 偶尔是 `["中山路1号", ...]` 这样的列表（多个
    门址），取第一个非空项；纯空白串按空处理。
    """
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _extract_text(item)
            if text:
                return text
        return ""
    if value is None or isinstance(value, dict):
        return ""
    return str(value).strip()


def _extract_photo(photos) -> str:
    """首张照片的 URL。`photos` 是 `[{"title": ..., "url": ...}, ...]`，
    无数据时同样是 `[]`。取第一个有 url 的，取不到就空串 —— 前端不渲染图位。
    """
    if not isinstance(photos, (list, tuple)):
        return ""
    for photo in photos:
        if isinstance(photo, dict):
            url = _extract_text(photo.get("url"))
            if url:
                return url
    return ""


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
    if 0 < rating < MIN_RATING:
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
