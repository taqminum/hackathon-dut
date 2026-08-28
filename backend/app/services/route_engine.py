import os
import random
import threading
import time
from math import asin, cos, radians, sin, sqrt

import requests

from app.services.coord import gcj02_polyline_to_wgs84, wgs84_str_to_gcj02_str
from app.services.dalian import scenario_key

WALKING_URL = "https://restapi.amap.com/v3/direction/walking"

# 高德对同一个 Key 有并发上限，超了返回 status=0 / infocode=10021
# CUQPS_HAS_EXCEEDED_THE_LIMIT（HTTP 仍是 200，很容易被当成成功）。
# 实测 3 线程并发 9 次调用有 6 次被拒，所以必须限流 + 重试。
AMAP_RATE_LIMIT_CODES = {"10021", "10022", "10019", "10020", "10001"}
AMAP_MIN_INTERVAL_SECONDS = 0.2   # 两次高德调用之间的最小间隔
AMAP_MAX_ATTEMPTS = 3

# 路线来源。绝不能把 amap 的真实路线和 fallback 的直线几何放在一起比较绕行，
# 否则会拿真实基准去减合成候选，算出来的「多花 N 分钟」是假的。
SOURCE_AMAP = "amap"
SOURCE_FALLBACK = "fallback"

_throttle_lock = threading.Lock()
_last_request_at = 0.0


def throttle_amap() -> None:
    """进程级限流：保证任意两次高德调用间隔不小于 AMAP_MIN_INTERVAL_SECONDS。"""
    global _last_request_at
    with _throttle_lock:
        wait = AMAP_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()

# 断网兜底的三个演示场景。key 由 dalian.scenario_key 生成 —— 三张兜底表共用
# 同一套地标坐标，改一处漏两处的静默退化在结构上不可能发生。
# base_* 和 polyline 都来自高德实测（见 docs 交接文档），不是估算：
# 折线按里程从实测的 163/246/222 个点等距抽稀到 7 个点，形状仍贴合真实道路。
# extra_* 是经由 POI 的额外代价，按模式给出，保证兜底时绕行也落在预算内。
DALIAN_SCENARIOS = {
    scenario_key("dut", "xinghai"): {
        "base_distance": 6920,
        "base_duration": 5536,
        "extra_distance": {None: 0, "+5": 240, "+15": 520, "roam": 780},
        "extra_duration": {None: 0, "+5": 140, "+15": 300, "roam": 460},
        "polyline": [
            "121.5197,38.8856",
            "121.5329,38.8871",
            "121.5460,38.8881",
            "121.5548,38.8883",
            "121.5635,38.8836",
            "121.5735,38.8823",
            "121.5839,38.8816",
        ],
    },
    scenario_key("donggang", "laohutan"): {
        "base_distance": 7322,
        "base_duration": 5858,
        "extra_distance": {None: 0, "+5": 260, "+15": 620, "roam": 980},
        "extra_duration": {None: 0, "+5": 160, "+15": 360, "roam": 580},
        "polyline": [
            "121.6785,38.9287",
            "121.6725,38.9219",
            "121.6722,38.9130",
            "121.6726,38.9041",
            "121.6719,38.8943",
            "121.6721,38.8839",
            "121.6701,38.8783",
        ],
    },
    scenario_key("xianlu", "fujiazhuang"): {
        "base_distance": 7361,
        "base_duration": 5889,
        "extra_distance": {None: 0, "+5": 220, "+15": 460, "roam": 720},
        "extra_duration": {None: 0, "+5": 130, "+15": 280, "roam": 420},
        "polyline": [
            "121.5825,38.9136",
            "121.5850,38.9031",
            "121.5902,38.8929",
            "121.5903,38.8826",
            "121.5937,38.8747",
            "121.6051,38.8722",
            "121.6161,38.8658",
        ],
    },
}


def get_candidate_routes(origin: str, destination: str, mode: str, waypoint: str | None = None) -> list[dict]:
    """origin / destination / waypoint 均为 WGS-84 的 `"lng,lat"`，返回的 polyline 也是 WGS-84。

    坐标系转换只在这里和 poi_explorer 里发生：发给高德前转 GCJ-02，收回来转回 WGS-84。
    """
    if os.getenv("AMAP_KEY"):
        if waypoint:
            routes = _request_amap_two_legs(origin, waypoint, destination)
        else:
            routes = _request_amap_walking(origin, destination)
        if routes:
            # 两条路径必须同形。高德分支过去只有 distance/duration/steps/polyline，
            # 而前端靠 `route.demo_mode` 决定是否显示「内置演示数据」提示、
            # 靠 `route.origin` 做起终点回退 —— 缺字段时 undefined 恰好为假，
            # 不报错但是隐性依赖：任何一处改成 `'demo_mode' in route` 就会翻车。
            return [
                {**route, "origin": origin, "destination": destination, "demo_mode": False}
                for route in routes
            ]

    return [_build_fallback_route(origin, destination, mode, waypoint)]


def _to_amap_coord(coord: str | None) -> str | None:
    """WGS-84 -> GCJ-02。转不动就原样返回，让高德自己报错，不要静默丢坐标。"""
    if not coord:
        return None
    return wgs84_str_to_gcj02_str(coord) or coord


def _request_amap_walking(origin: str, destination: str) -> list[dict]:
    """单段步行调用。

    注意：步行接口**不支持** waypoint，传了会被静默忽略（实测带与不带距离完全一致
    6920 m）。途经点必须靠 _request_amap_two_legs 两段拼接实现。
    """
    params = {
        "origin": _to_amap_coord(origin),
        "destination": _to_amap_coord(destination),
        "strategy": 0,
        "key": os.getenv("AMAP_KEY"),
    }

    data = _get_with_retry(params)
    if data is None:
        return []

    route_data = data.get("route") if isinstance(data, dict) else None
    paths = route_data.get("paths", []) if isinstance(route_data, dict) else []
    if not isinstance(paths, list):
        return []

    routes = []
    for path in paths:
        if not isinstance(path, dict):
            continue
        try:
            distance = int(path.get("distance", 0))
            duration = int(path.get("duration", 0))
        except (TypeError, ValueError):
            continue
        if distance <= 0 or duration <= 0:
            continue
        steps = path.get("steps", [])
        routes.append(
            {
                "source": SOURCE_AMAP,
                "distance": distance,
                "duration": duration,
                "steps": _steps_to_wgs84(steps),
                # 步行接口的 path 上没有 polyline 字段，几何全在每个 step 里，
                # 必须拼起来，否则前端拿到空串画不出折线。
                "polyline": gcj02_polyline_to_wgs84(
                    path.get("polyline") or _join_step_polylines(steps)
                ),
            }
        )
    return routes


def _get_with_retry(params: dict) -> dict | None:
    """带限流与重试的高德 GET。被限流时退避重试，最终失败返回 None。

    注意高德限流时 HTTP 状态码仍是 200，必须看 infocode。
    """
    for attempt in range(AMAP_MAX_ATTEMPTS):
        throttle_amap()
        try:
            response = requests.get(WALKING_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, TypeError, ValueError, AttributeError):
            return None

        if not isinstance(data, dict):
            return None

        if str(data.get("infocode", "")) not in AMAP_RATE_LIMIT_CODES:
            return data

        # 被限流：退避后重试，加抖动避免多个线程同时重试又一起撞上
        if attempt < AMAP_MAX_ATTEMPTS - 1:
            time.sleep(0.25 * (2 ** attempt) + random.uniform(0, 0.1))

    return None


def _join_step_polylines(steps) -> str:
    """把各 step 的 polyline 首尾相接，去掉衔接处重复的那个点。"""
    if not isinstance(steps, list):
        return ""
    points: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        for chunk in str(step.get("polyline") or "").split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            if points and points[-1] == chunk:
                continue
            points.append(chunk)
    return ";".join(points)


def _steps_to_wgs84(steps) -> list:
    """分段指引里也带 polyline，一并转换，保证对外只有一种坐标系。"""
    if not isinstance(steps, list):
        return []
    converted = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("polyline"):
            step = {**step, "polyline": gcj02_polyline_to_wgs84(step.get("polyline"))}
        converted.append(step)
    return converted


def _walk_leg(origin: str, destination: str) -> dict | None:
    """一段步行，取高德给的第一条方案；失败返回 None。"""
    routes = _request_amap_walking(origin, destination)
    return routes[0] if routes else None


def _request_amap_two_legs(origin: str, waypoint: str, destination: str) -> list[dict]:
    """经由 waypoint 的路线 = `起点->途经点` + `途经点->终点` 两段拼接。

    代价是每个候选 2 次调用，所以调用方必须截断候选数量（见 api.py）。
    """
    first = _walk_leg(origin, waypoint)
    if not first:
        return []
    second = _walk_leg(waypoint, destination)
    if not second:
        return []

    return [
        {
            "source": SOURCE_AMAP,
            "distance": first["distance"] + second["distance"],
            "duration": first["duration"] + second["duration"],
            "steps": list(first["steps"]) + list(second["steps"]),
            "polyline": _concat_polylines(first["polyline"], second["polyline"]),
        }
    ]


def _concat_polylines(first: str, second: str) -> str:
    """首尾相接两条明文折线，去掉衔接处重复的点。"""
    head = [c for c in str(first or "").split(";") if c]
    tail = [c for c in str(second or "").split(";") if c]
    if head and tail and head[-1] == tail[0]:
        tail = tail[1:]
    return ";".join(head + tail)


def _build_fallback_route(origin: str, destination: str, mode: str, waypoint: str | None) -> dict:
    scenario = _select_dalian_scenario(origin, destination)
    start = _parse_lng_lat(origin)
    end = _parse_lng_lat(destination)
    mid = _parse_lng_lat(waypoint) if waypoint else None

    if scenario:
        base_distance = scenario["base_distance"]
        base_duration = scenario["base_duration"]
    else:
        direct_distance = _haversine_meters(start, end)
        if direct_distance > 50_000:
            raise ValueError("fallback route is too long")

        route_distance = direct_distance
        if mid:
            route_distance = _haversine_meters(start, mid) + _haversine_meters(mid, end)
        base_distance = max(1, round(route_distance * 1.3))
        base_duration = max(1, round(base_distance / 1.35))

    if waypoint and scenario:
        effective_mode = mode or "+15"
        extra_distance = (scenario or {}).get("extra_distance") or {}
        extra_duration = (scenario or {}).get("extra_duration") or {}
        base_distance += extra_distance.get(effective_mode, 220)
        base_duration += extra_duration.get(effective_mode, 120)

    points = [start]
    if mid:
        points.append(mid)
    points.append(end)

    if scenario:
        scenario_points = list(scenario["polyline"])
        if mid:
            scenario_points.insert(_waypoint_insert_index(scenario_points, mid), [mid[0], mid[1]])

        polyline = _format_polyline(scenario_points)
    else:
        polyline = _format_polyline(points)

    return {
        "source": SOURCE_FALLBACK,
        "origin": origin,
        "destination": destination,
        "demo_mode": scenario is not None,
        "distance": base_distance,
        "duration": base_duration,
        "steps": [
            {
                "instruction": "按推荐路线行走",
                "road": origin,
                "distance": str(base_distance),
                "duration": str(base_duration),
            }
        ],
        "polyline": polyline,
    }


def _format_polyline(points) -> str:
    """折线序列化成 "lng,lat;..."，顺带丢掉相邻重复点。

    途经点可能正好落在折线原有的顶点上（4 位小数下更容易撞上），
    重复点会让前端画出零长度线段。
    """
    formatted: list[str] = []
    for lng, lat in points:
        point = f"{float(lng):.4f},{float(lat):.4f}"
        if not formatted or formatted[-1] != point:
            formatted.append(point)
    return ";".join(formatted)


def _waypoint_insert_index(points: list, waypoint: tuple[float, float]) -> int:
    """途经点该插在折线的哪个位置。

    过去固定插到索引 2，途经点在路线后半段时就会画出折返线（实测反向远离终点
    416-501 米）。改成找与途经点距离最近的线段，插到该线段之后 —— 折线保持单向。
    """
    best_index = 1
    best_distance = float("inf")

    for index in range(len(points) - 1):
        start = (float(points[index][0]), float(points[index][1]))
        end = (float(points[index + 1][0]), float(points[index + 1][1]))
        distance = _point_to_segment_meters(waypoint, start, end)
        if distance < best_distance:
            best_distance = distance
            best_index = index + 1

    return best_index


def point_to_route_meters(point: str | None, polyline: str | None) -> float | None:
    """一个坐标点到整条折线的最近距离（米）。算不出返回 None。

    给 api.py 判断「这个 POI 是否真的在最终路线沿途」用：多返回几个亮点是好事，
    但只有确实贴着选中路线的点才能说「顺路会经过」。折线只有 1 个点或点解析
    不出来时返回 None —— 让调用方决定怎么处理，不要伪造一个 0 或 inf。
    """
    try:
        target = _parse_lng_lat(point)
    except (ValueError, AttributeError):
        return None

    points: list[tuple[float, float]] = []
    for chunk in str(polyline or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            points.append(_parse_lng_lat(chunk))
        except (ValueError, AttributeError):
            continue

    if len(points) < 2:
        return None

    return min(
        _point_to_segment_meters(target, points[index], points[index + 1])
        for index in range(len(points) - 1)
    )


def _point_to_segment_meters(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """点到线段的距离。先在局部平面上求最近点，再用 _haversine_meters 报真实米数。

    只投影不换算会让经度差被高估（大连一带 1 度经度约是 1 度纬度的 0.78 倍），
    选错线段就又画出折返线。
    """
    scale = cos(radians((start[1] + end[1]) / 2))
    ax, ay = start[0] * scale, start[1]
    bx, by = end[0] * scale, end[1]
    px, py = point[0] * scale, point[1]

    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    if denominator == 0:
        return _haversine_meters(point, start)

    ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denominator))
    nearest = (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)
    return _haversine_meters(point, nearest)


def _parse_lng_lat(coord: str | None) -> tuple[float, float]:
    """`"lng,lat"` -> `(lng, lat)`。解析不了就抛 ValueError。

    过去空值会返回天安门坐标 `116.407526,39.90403`。那是个静默的错误默认值：
    坐标丢在上游（地理编码失败、字段拼错）时，用户拿到的是一条**北京的**路线，
    而不是一个能定位问题的错误 —— 排查起来极难，界面上也看不出哪里不对。
    现在抛异常，由 api.py 转成 404「未找到可行路线」。
    """
    if not coord or not str(coord).strip():
        raise ValueError("coordinate is empty")
    lng, lat = str(coord).split(",", 1)
    return float(lng), float(lat)


def _haversine_meters(start: tuple[float, float], end: tuple[float, float]) -> float:
    start_lng, start_lat = map(radians, start)
    end_lng, end_lat = map(radians, end)
    delta_lng = end_lng - start_lng
    delta_lat = end_lat - start_lat
    value = sin(delta_lat / 2) ** 2 + cos(start_lat) * cos(end_lat) * sin(delta_lng / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(value))


def _select_dalian_scenario(origin: str, destination: str) -> dict | None:
    direct_key = f"{_normalize(origin)}->{_normalize(destination)}"
    reverse_key = f"{_normalize(destination)}->{_normalize(origin)}"

    selected = DALIAN_SCENARIOS.get(direct_key)
    reversed_route = False
    if not selected:
        selected = DALIAN_SCENARIOS.get(reverse_key)
        reversed_route = selected is not None

    if not selected:
        return None

    normalized = selected.copy()
    normalized["polyline"] = [
        list(map(float, point.split(","))) for point in selected["polyline"]
    ]
    if reversed_route:
        normalized["polyline"].reverse()
    return normalized


def _normalize(coord: str | None) -> str:
    if not coord:
        return ""
    lng, lat = str(coord).split(",", 1)
    return f"{float(lng):.4f},{float(lat):.4f}"
