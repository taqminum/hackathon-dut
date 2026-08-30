import os
import random
import threading
import time
from math import asin, atan2, cos, degrees, radians, sin, sqrt

import requests

from app.services.coord import gcj02_polyline_to_wgs84, wgs84_str_to_gcj02_str
from app.services.dalian import scenario_key

WALKING_URL = "https://restapi.amap.com/v3/direction/walking"

# 高德对同一个 Key 有并发上限，超了返回 status=0 / infocode=10021
# CUQPS_HAS_EXCEEDED_THE_LIMIT（HTTP 仍是 200，很容易被当成成功）。
# 实测 3 线程并发 9 次调用有 6 次被拒，所以必须限流 + 重试。
AMAP_RATE_LIMIT_CODES = {"10021", "10022", "10019", "10020", "10001"}
AMAP_MIN_INTERVAL_SECONDS = float(os.getenv("AMAP_MIN_INTERVAL_SECONDS", "0.35"))
AMAP_MAX_ATTEMPTS = int(os.getenv("AMAP_MAX_ATTEMPTS", "3"))

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
#
# R4：这里原本还有一对 `extra_distance` / `extra_duration`
# （`{None: 0, "+5": 240, "+15": 520, "roam": 780}` 之类），经由 POI 时按模式
# **加到 distance 上**。那是个假数字：折线只多插了一个点，三个模式的几何一模一样
# （polyline sha1 全等），而报出的距离却差了 240/520/780 米。现在 base_* 只作为
# **标定系数的来源**（几何长度 -> 实测里程的比例、以及实测步速），距离和时长一律从
# 最终折线量出来 —— 见 _build_fallback_route。数字想变，几何就必须真的变。
DALIAN_SCENARIOS = {
    scenario_key("dut", "xinghai"): {
        "base_distance": 6920,
        "base_duration": 5536,
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


def get_route_via_waypoints(
    origin: str,
    destination: str,
    waypoints: list[str] | tuple[str, ...],
) -> dict | None:
    """用真实高德步行路网依次经过多个途经点。

    v3 步行接口没有途经点参数，因此把 ``A -> P1 -> ... -> B`` 拆成多段请求，
    再把距离、时长、指引和折线无损拼接。这个函数绝不降级到几何估算：调用方用它
    生成正式推荐，任一段拿不到真实高德结果时整条候选作废。
    """
    if not os.getenv("AMAP_KEY"):
        return None

    stops = [origin, *[point for point in waypoints if point], destination]
    if len(stops) < 2:
        return None

    legs: list[dict] = []
    for start, end in zip(stops, stops[1:]):
        leg = _walk_leg(start, end)
        if not leg or leg.get("source") != SOURCE_AMAP:
            return None
        legs.append(leg)

    if not legs:
        return None

    polyline = ""
    for leg in legs:
        polyline = _concat_polylines(polyline, leg.get("polyline", ""))

    return {
        "source": SOURCE_AMAP,
        "origin": origin,
        "destination": destination,
        "demo_mode": False,
        "distance": sum(int(leg["distance"]) for leg in legs),
        "duration": sum(int(leg["duration"]) for leg in legs),
        "steps": [step for leg in legs for step in leg.get("steps", [])],
        "polyline": polyline,
        "waypoint_count": len(stops) - 2,
    }


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
    """兜底路线。**distance / duration 一律从最终折线量出来**，不查表加常数。

    R4：原来经由 POI 时按模式给 distance 加一个表里的常数（240/520/780 米），
    而折线只是把 POI 那一个点插进 7 点折线里 —— 三个模式的 polyline sha1 完全相同，
    却报出三个不同的距离。用户的观感（「三个模式看起来一样」）是准确的，而数字是假的。
    现在几何是唯一的事实来源：绕行想让距离变长，折线就必须真的变长。
    """
    scenario = _select_dalian_scenario(origin, destination)
    start = _parse_lng_lat(origin)
    end = _parse_lng_lat(destination)
    mid = _parse_lng_lat(waypoint) if waypoint else None

    if scenario:
        points = _detour_points(scenario["polyline"], mid, _detour_width(mode))
        # 折线是按里程抽稀过的 7 点直线段，几何长度短于实测里程（实测/几何 =
        # 1.20 ~ 1.26，比无 scenario 分支的 1.3 更贴近真实道路）。系数和步速都由
        # base_* 反算，所以「大工→星海 6.9 公里 / 92 分钟」这两个实测数字仍然成立，
        # 只是不再作为常数直接输出，而是作为标定值参与换算。
        base_geometry = _polyline_length(scenario["polyline"])
        factor = scenario["base_distance"] / base_geometry if base_geometry > 0 else 1.3
        speed = scenario["base_distance"] / max(1, scenario["base_duration"])
    else:
        direct_distance = _haversine_meters(start, end)
        if direct_distance > 50_000:
            raise ValueError("fallback route is too long")

        points = [start]
        if mid:
            points.append(mid)
        points.append(end)
        factor, speed = 1.3, 1.35

    polyline = _format_polyline(points)
    # 量的是格式化之后的折线：_format_polyline 会四舍五入到 4 位小数并丢掉重复点，
    # 量格式化之前的点会和前端画出来的线差上几米，验收标准的 5% 容差留不住这种偏移。
    geometry = _polyline_length(_parse_polyline(polyline))
    base_distance = max(1, round(geometry * factor))
    base_duration = max(1, round(base_distance / speed))

    return {
        "source": SOURCE_FALLBACK,
        "origin": origin,
        "destination": destination,
        "demo_mode": scenario is not None,
        "distance": base_distance,
        "duration": base_duration,
        "steps": _fallback_steps(polyline, base_distance, base_duration),
        "polyline": polyline,
    }


# R4：兜底折线为了接 POI，最多让开几个原顶点。「让开」= 推荐路线不再经过那个点，
# 于是两条线分岔再合拢 —— 分岔幅度随模式放大，这是「绕多远去接 POI」在几何上的体现。
# 只有 7 个点可用，所以 1/2/3 已经是这份演示数据能撑开的全部量级。
_DETOUR_WIDTH = {"+5": 1, "+15": 2, "roam": 3}


def _detour_width(mode: str | None) -> int:
    return _DETOUR_WIDTH.get(mode or "+15", 2)


def _detour_points(
    scenario_polyline,
    mid: tuple[float, float] | None,
    width: int = 2,
) -> list[tuple[float, float]]:
    """把途经点插进场景折线，并让两条线真的分岔一次。

    只插入一个点的话，推荐折线是基准折线的**严格子序列**（`base_only == 0`）：
    两条线完全重合，只在 POI 处鼓出几十米，7 公里的图上肉眼分不出来 ——
    这正是用户说「原路线和推荐路线没区别」的原因。

    所以插入之后再让开离 POI 最近的几个原顶点：推荐路线绕去 POI，基准路线仍走原顶点，
    两条线**分岔再合拢**，`base_only > 0`，地图上看得见。`width` 决定让开几个，
    由模式给出。只在「让开之后几何更长」时才让（否则等于抄近道，绕行会变成负数），
    让不动就保留原样 —— 正确性优先于观感。
    """
    points = _coerce_points(scenario_polyline)
    if mid is None:
        return points

    index = _waypoint_insert_index(points, mid)
    result = points[:index] + [mid] + points[index:]
    mid_index = index
    baseline_length = _polyline_length(points)

    for _ in range(max(0, width)):
        # 每轮重算候选：让开一个点之后，剩下哪个离 POI 最近会变。
        candidates = sorted(
            (i for i in range(1, len(result) - 1) if i != mid_index),
            key=lambda i: _haversine_meters(result[i], mid),
        )
        for i in candidates:
            trimmed = result[:i] + result[i + 1 :]
            if _polyline_length(trimmed) > baseline_length:
                result = trimmed
                if i < mid_index:
                    mid_index -= 1
                break
        else:
            break

    return result


def _coerce_points(polyline) -> list[tuple[float, float]]:
    """`["lng,lat", ...]` / `[[lng, lat], ...]` 都收，统一成 float 二元组。

    `DALIAN_SCENARIOS` 里存的是字符串，`_select_dalian_scenario` 出来的是 list ——
    `_waypoint_insert_index` 对字符串点会算出错误的索引（float() 收不了 "lng,lat"，
    但下标取字符会静默给出别的数），所以入口统一。
    """
    points: list[tuple[float, float]] = []
    for point in polyline or []:
        if isinstance(point, str):
            points.append(_parse_lng_lat(point))
        else:
            points.append((float(point[0]), float(point[1])))
    return points


def _parse_polyline(polyline: str | None) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for chunk in str(polyline or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            points.append(_parse_lng_lat(chunk))
        except (ValueError, AttributeError):
            continue
    return points


def _polyline_length(points) -> float:
    """折线的球面长度（米）。少于两个点时是 0，由调用方决定怎么兜。"""
    prepared = _coerce_points(points)
    return sum(
        _haversine_meters(prepared[i], prepared[i + 1]) for i in range(len(prepared) - 1)
    )


# 方位角 -> 方向词。八向，边界按 22.5° 均分（0° 是正北，顺时针增大）。
_BEARING_WORDS = ("北", "东北", "东", "东南", "南", "西南", "西", "西北")


def _bearing_degrees(start: tuple[float, float], end: tuple[float, float]) -> float:
    """从 start 走向 end 的方位角，0~360，0 为正北。"""
    start_lng, start_lat = map(radians, start)
    end_lng, end_lat = map(radians, end)
    delta_lng = end_lng - start_lng
    y = sin(delta_lng) * cos(end_lat)
    x = cos(start_lat) * sin(end_lat) - sin(start_lat) * cos(end_lat) * cos(delta_lng)
    return (degrees(atan2(y, x)) + 360) % 360


def _direction_word(start: tuple[float, float], end: tuple[float, float]) -> str:
    index = int((_bearing_degrees(start, end) + 22.5) % 360 // 45)
    return _BEARING_WORDS[index]


def _fallback_steps(polyline: str, total_distance: int, total_duration: int) -> list[dict]:
    """兜底路线的分段指引。

    以前这里是硬编码的**单元素**列表，而且 `road` 字段塞的是起点坐标 ——
    界面上就变成「01 按推荐路线行走 / 121.5197,38.8856 / 7.4 公里 / 1 小时 37 分钟」：
    一整条路只有一步（`RouteSteps` 的折叠交互因此永远不出现），
    路名的位置印着一串经纬度。

    现在按折线的相邻点分段，方向词由方位角推出。两条硬约束：

    * `road` **不放坐标**。兜底数据没有真实路名，宁可留空 ——
      `RouteSteps.vue` 的 `v-if="step.road"` 会自动隐掉这一行。
    * 各段的 distance / duration **之和必须等于**整条路线的总值。
      逐段按比例取整会累积误差，所以用「前缀和的差」来分配：
      第 i 段拿到 `round(总量 * 累计里程/总里程)` 减去已分配的部分，
      最后一段自然吃掉全部余数，加起来恒等于总量。
    """
    points = []
    for chunk in str(polyline or "").split(";"):
        if not chunk:
            continue
        try:
            lng, lat = chunk.split(",", 1)
            points.append((float(lng), float(lat)))
        except ValueError:
            continue

    legs = [
        (points[i], points[i + 1], _haversine_meters(points[i], points[i + 1]))
        for i in range(len(points) - 1)
    ]
    legs = [leg for leg in legs if leg[2] > 0]

    if not legs:
        # 折线退化（单点、或解析不出）时给一条不带坐标的兜底，总量照旧对得上
        return [
            {
                "instruction": "按推荐路线行走",
                "road": "",
                "distance": str(total_distance),
                "duration": str(total_duration),
            }
        ]

    geometric_total = sum(leg[2] for leg in legs)
    steps: list[dict] = []
    walked = 0.0
    given_distance = 0
    given_duration = 0

    for index, (start, end, meters) in enumerate(legs):
        walked += meters
        ratio = walked / geometric_total
        # 前缀和分配：最后一段的 ratio 恰好是 1.0，于是余数全部落在它身上
        distance = round(total_distance * ratio) - given_distance
        duration = round(total_duration * ratio) - given_duration
        given_distance += distance
        given_duration += duration

        word = _direction_word(start, end)
        if len(legs) == 1:
            # 折线只有起终两点（非演示场景的直连兜底）时整条就是一段，
            # 说「继续」或「到达终点」都像漏了前面几步
            instruction = f"从起点向{word}走约 {distance} 米到达终点"
        elif index == len(legs) - 1:
            instruction = f"向{word}走约 {distance} 米后到达终点"
        elif index == 0:
            instruction = f"从起点向{word}走约 {distance} 米"
        else:
            instruction = f"继续向{word}走约 {distance} 米"

        steps.append(
            {
                "instruction": instruction,
                # 兜底数据没有真实路名。留空而不是填坐标，见本函数 docstring。
                "road": "",
                "distance": str(distance),
                "duration": str(duration),
            }
        )

    return steps


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

    points = _parse_polyline(polyline)
    if len(points) < 2:
        return None

    return min(
        _point_to_segment_meters(target, points[index], points[index + 1])
        for index in range(len(points) - 1)
    )


def point_to_route_progress(point: str | None, polyline: str | None) -> float | None:
    """返回点在路线上的最近投影进度，范围 ``[0, 1]``。

    多途经点必须按基准路线的前后顺序访问，否则同一批好地点会被拼成来回折返的路线。
    这里同时考虑每段真实长度和点在线段上的投影比例，不能只找最近顶点。
    """
    try:
        target = _parse_lng_lat(point)
    except (ValueError, AttributeError):
        return None

    points = _parse_polyline(polyline)
    if len(points) < 2:
        return None

    spans = [_haversine_meters(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total = sum(spans)
    if total <= 0:
        return None

    best_distance = float("inf")
    best_progress = 0.0
    walked = 0.0
    for index, span in enumerate(spans):
        start, end = points[index], points[index + 1]
        ratio = _point_projection_ratio(target, start, end)
        nearest = (
            start[0] + (end[0] - start[0]) * ratio,
            start[1] + (end[1] - start[1]) * ratio,
        )
        distance = _haversine_meters(target, nearest)
        if distance < best_distance:
            best_distance = distance
            best_progress = (walked + span * ratio) / total
        walked += span
    return max(0.0, min(1.0, best_progress))


def _point_to_segment_meters(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """点到线段的距离。先在局部平面上求最近点，再用 _haversine_meters 报真实米数。

    只投影不换算会让经度差被高估（大连一带 1 度经度约是 1 度纬度的 0.78 倍），
    选错线段就又画出折返线。
    """
    ratio = _point_projection_ratio(point, start, end)
    nearest = (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)
    return _haversine_meters(point, nearest)


def _point_projection_ratio(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """局部平面中点在线段上的投影比例，端点外的结果钳到 ``[0, 1]``。"""
    scale = cos(radians((start[1] + end[1]) / 2))
    ax, ay = start[0] * scale, start[1]
    bx, by = end[0] * scale, end[1]
    px, py = point[0] * scale, point[1]

    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    if denominator == 0:
        return 0.0

    return max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denominator))


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
