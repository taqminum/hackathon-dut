import concurrent.futures
import itertools
import math
import os
import re
import threading
import time
from itertools import combinations

import requests
from fastapi import APIRouter, Body, HTTPException, Query

from app.models.preference import PreferenceManager
from app.services.coord import gcj02_str_to_wgs84_str
from app.services.detour_calculator import calculate_detour
from app.services.geocoder import ensure_location_in_city, normalize_coordinate, resolve_location
from app.services.narrative import DEFAULT_NARRATIVE, generate_narrative
from app.services.poi_explorer import explore_pois_along_route, poi_fit_score
from app.services.poi_judge import judge_pois, split_pois_by_verdict
from app.services.route_engine import (
    SOURCE_AMAP,
    SOURCE_FALLBACK,
    get_candidate_routes,
    get_route_via_waypoints,
    point_to_route_meters,
    point_to_route_progress,
    throttle_amap,
)
from app.services.scorer import SerendipityScorer


router = APIRouter()
scorer = SerendipityScorer()
# 反馈闭环的载体：/api/feedback 写入，_evaluate_candidate 读出（见 P2-2）。
# 进程内存储，和收藏一样重启即失。
preferences = PreferenceManager()

# roam 也有上限。产品说的是「**可控的**意外」，一个不设上限的模式跟这句话冲突：
# 高德偶尔会给出绕行 40 分钟的候选，那已经不是「随便走走」而是另一趟行程了。
# 30 分钟是 +15 的两倍，足够拉开三个模式的层次，又不至于让人以为程序算错了。
MAX_DETOUR_MINUTES = {"+5": 5, "+15": 15, "roam": 30}
SUPPORTED_MODES = {"+5", "+15", "roam"}

# R4：三个模式过去只在「预算上限」上不同，而预算在候选评估阶段就已经卡过一次，
# 进到选优的候选**都**满足上限 —— 于是三个模式挑出同一个 POI、同一条折线，
# 用户看到的三份结果只有查表加出来的假数字不一样。
#
# 真正的差异应该是「愿意为一个地方偏离主路多远」：`+5` 是顺手一绕，只肯要贴着
# 路线的地方；`roam` 是随便走走，远一点也无妨。这里的值是**排序时**每 100 米
# 离线距离扣的分（不进入返回给前端的 score —— ScoreMeter 是 7 分制的探索价值，
# 掺进模式偏好就变成两个量纲了）。
#
# 0.6 这个量级是照 MIN_RATING 到 5 分之间的分差定的：评分差 0.3 分（4.3 vs 4.6）
# 约等于 0.24 分的 quality_bonus 差，所以 +5 下 50 米的额外离线距离就足以翻盘，
# 而 roam 完全不在乎距离、只看分。
DETOUR_APPETITE = {"+5": 0.6, "+15": 0.2, "roam": 0.0}

# 每个候选要两次高德步行调用（步行接口不支持 waypoint，只能两段拼接）。
# 截断到 3 个是为了控制配额：一次请求约 7 次调用。
MAX_CANDIDATES = 6
# AI 语义把关只看质量最高的前 N 个候选，避免把几十条 POI 一次塞给 LLM。
# 取 MAX_CANDIDATES 的两倍，既覆盖候选池，也留出被 AI 剔除后的替补空间。
AI_JUDGE_POI_LIMIT = 12
# 高德对同一个 Key 有并发上限（infocode 10021），route_engine 里已按
# AMAP_MIN_INTERVAL_SECONDS 限流，这里再开大线程池只会互相排队并触发限流重试。
MAX_WORKERS = 2
# 整个 recommend 的总预算。超时就用已经算完的候选，不空手而归。
TOTAL_BUDGET_SECONDS = 25.0
# 沿线采样每个点的搜索半径。三点覆盖整条路线，搜索半径可以比最终展示的
# 「贴着路线」阈值更宽；候选先广搜，_collect_highlights 再按真实折线过滤。
POI_SEARCH_RADIUS = 400
POI_SEARCH_RADIUS_BY_MODE = {"+5": 300, "+15": 600, "roam": 1000}
# 使用高德官方分类大类，不依赖「餐饮 / 景点」这类非标准模糊词。
# 只搜索高德的风景名胜与科教文化服务大类。餐饮、商业、洗浴等类别从数据源就不
# 进入候选池；下方仍有关键词二次过滤，防止分类标错的普通商业 POI 混进来。
AMAP_POI_TYPES = [
    "110000",  # 风景名胜
    "140300", "140400", "140500", "140600", "140700", "140800", "140900",
    "141000", "141100", "141200",  # 图书/科技/天文/文化宫/档案/文物/博物/展览/会展/美术
]
DISCOVERY_EXCLUDED_WORDS = (
    "餐", "咖啡", "奶茶", "酒吧", "ktv", "夜总会", "洗浴", "洗澡", "spa", "会所",
    "足疗", "按摩", "商场", "购物", "超市", "便利店", "酒店", "宾馆", "旅馆", "美容",
    "美发", "健身", "售楼", "公司", "银行", "停车场", "培训", "教育", "学校", "幼儿园", "驾校",
    "出版社", "影视", "电视台", "广播", "报社", "通讯社", "印刷",
)
HERITAGE_WORDS = ("古迹", "遗址", "文物", "纪念", "博物", "美术", "故居", "寺", "塔", "牌坊")
SCENIC_WORDS = ("风景", "景区", "公园", "海滨", "湿地", "森林", "山", "湖", "海", "岛")
CULTURAL_WORDS = ("文化", "展览", "图书", "剧院", "大学", "书院", "艺术")
SUPPORTED_POI_COUNTS = {1, 2, 3}
MAX_ROUTE_SET_EVALUATIONS = 3

# 返回给前端的沿途亮点上限。第一个必定是被选中的那个 POI（路线真的经过它），
# 其余是**确实贴着这条路线**的其他候选。
MAX_RETURNED_POIS = 3
# 「顺路」的判定半径。超过这个距离就不能说「沿途会经过」——
# 卖「偶遇」的产品不能在这句话上注水，宁可只返回一个亮点。
# 150 米足够覆盖一个街区内的旁边亮点，同时不会把地图上的标记放到另一条街。
NEARBY_POI_METERS = 150
# 目的地自身、以及和目的地同名的地铁站/公交站，会从 place/around 的采样走廊里
# 漏进来，离终点常常不足 100 米，却会被当成「途中偶遇」推荐回去 —— 读起来像
# 「为了去终点而绕路」。起终点周边这一圈也不该有「顺路偶遇」，直接剔除。
ENDPOINT_EXCLUDE_METERS = 300
# 只靠距离拦不全：同名地点（例如目的地出入口、同名地铁站）可能离终点 300~1000 米。
# 对名称与目的地一致的 POI 放宽容忍范围，避免把「目的地本身/同名交通站」当成
# 沿途亮点；远处另一座同名地点不受影响。
DEST_NAME_MATCH_METERS = 1000

INPUTTIPS_URL = "https://restapi.amap.com/v3/assistant/inputtips"
# 收藏是进程内存储：演示够用，重启即失。要持久化再接数据库，
# 但别在演示前一天做这件事。
MAX_STORED_TRIPS = 200
MAX_STORED_FEEDBACK = 500
# 每次推荐都记一条，用来把反馈归因到具体 POI 类型。演示期间几百条足够。
# 淘汰按 dict 插入顺序删最旧的（3.7+ 保证），但「插入顺序 == 最旧」只在
# `_trip_ids` 单调递增时才成立。哪天 trip_id 改成随机或复用，这里要换成显式排序。
MAX_TRACKED_RECOMMENDATIONS = 200

_storage_lock = threading.Lock()
# trip_id 在「推荐」和「收藏」之间共用一个序列：两边都会发 id 给前端，
# 用两个计数器会出现两条不同记录拿到同一个 1，反馈就归因到错的那条上。
_trip_ids = itertools.count(1)
_saved_trips: list[dict] = []
_feedback_entries: list[dict] = []
_recommendations: dict[int, dict] = {}


@router.post("/route/recommend", response_model=None)
def recommend_route(
    origin: str = Body(..., embed=True),
    destination: str = Body(..., embed=True),
    mode: str = Body("+5", embed=True),
    poi_count: int = Body(1, embed=True),
    city: str | None = Body(None, embed=True),
):
    started_at = time.monotonic()

    if mode not in SUPPORTED_MODES:
        raise HTTPException(status_code=422, detail="不支持的探索模式")
    if poi_count not in SUPPORTED_POI_COUNTS:
        raise HTTPException(status_code=422, detail="一次可绕行 1 到 3 个地点")
    city = city.strip() if isinstance(city, str) else ""

    # 校验通过后立刻记下模式：`GET /api/preference` 是演示时用来证明「它记住了」的，
    # 只靠反馈写入的话，用户连点三次 +15 那个接口还会显示 +5。
    preferences.set_mode(mode)

    if not origin or not destination:
        raise HTTPException(status_code=404, detail="未找到可行路线")

    try:
        resolved_origin = resolve_location(origin, city) if city else resolve_location(origin)
        resolved_destination = (
            resolve_location(destination, city) if city else resolve_location(destination)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未找到可行路线") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail=f"地点解析失败：{exc}") from exc

    # 网页客户端始终提交城市；保留 city 缺省兼容旧版本客户端，避免旧调用被默默
    # 改成大连市而误拒绝。新客户端缺城市时不会发生（首页有默认值）。
    if city and os.getenv("AMAP_KEY"):
        try:
            in_city = all(
                ensure_location_in_city(point, city)
                for point in (resolved_origin, resolved_destination)
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail="无法核实地点所在城市，请稍后重试") from exc
        if not in_city:
            raise HTTPException(status_code=422, detail="起点和终点必须位于所选城市内")

    if resolved_origin == resolved_destination:
        raise HTTPException(status_code=422, detail="起点和终点不能相同")

    try:
        baseline_routes = get_candidate_routes(resolved_origin, resolved_destination, mode)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未找到可行路线") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail=f"路径规划失败：{exc}") from exc

    if not baseline_routes:
        raise HTTPException(status_code=404, detail="未找到可行路线")

    baseline = baseline_routes[0]
    # 正式推荐只接受真实高德路网。无 Key、Key 失效、限流或网络失败时
    # route_engine 会给 fallback；这里必须明确拦住，不能把估算路线伪装成在线结果。
    offline_fallback_enabled = os.getenv("ALLOW_OFFLINE_FALLBACK") == "1"
    if baseline.get("source") == SOURCE_FALLBACK and not offline_fallback_enabled:
        raise HTTPException(
            status_code=503,
            detail="真实高德路线服务未就绪，请检查 AMAP_KEY 和网络后重试",
        )
    baseline_minutes = round(baseline["duration"] / 60)

    try:
        # 按路线长度自适应采样，形成近似连续的沿线搜索走廊。
        pois = explore_pois_along_route(
            resolved_origin,
            resolved_destination,
            ["餐饮", "景点", "购物"] if baseline.get("source") == SOURCE_FALLBACK else AMAP_POI_TYPES,
            radius=POI_SEARCH_RADIUS_BY_MODE[mode],
            polyline=baseline.get("polyline"),
            allow_fallback=offline_fallback_enabled,
            strict=baseline.get("source") == SOURCE_AMAP,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    pois = _drop_destination_neighbors(pois, resolved_destination, destination_name=destination)

    if not pois:
        raise HTTPException(status_code=404, detail="这条路线沿线没有找到可核实的值得绕行地点")

    if baseline.get("source") == SOURCE_AMAP:
        pois = [poi for poi in pois if _discovery_kind(poi)]
        if not pois:
            raise HTTPException(status_code=404, detail="这条路线沿线没有找到文化或风景类绕行地点")

        # AI 语义把关：类别规则拦不住的小馆子/连锁门店，让 LLM 判一次是否值得绕路。
        # 只取质量最高的前 N 个给 LLM；失败时 judge_pois 返回 None，rejected 为空，
        # 候选原样保留 —— AI 把关不能改变原来的推荐行为。
        judge_pool = sorted(
            pois,
            key=_preliminary_poi_quality,
            reverse=True,
        )[:AI_JUDGE_POI_LIMIT]
        _judged, rejected = split_pois_by_verdict(judge_pool, judge_pois(judge_pool))
        rejected_ids = {id(poi) for poi in rejected}
        if rejected_ids:
            pois = [poi for poi in pois if id(poi) not in rejected_ids]
        if not pois:
            raise HTTPException(status_code=404, detail="这条路线沿线没有找到值得绕行的地点")

    # 单点候选需要逐个走真实路网，才能比较绕行时间；多点如果也先逐个规划，
    # 6 个候选会额外消耗 12 次步行请求，等真正组合路线时总预算已经耗尽。
    # 多点先只用真实 POI 元数据和它到基准折线的实测距离做组合初筛，最后对
    # 排名前三的组合调用真实高德分段路线。最终返回值仍全部来自真实路网。
    candidates = (
        _evaluate_candidates(
            resolved_origin,
            resolved_destination,
            mode,
            baseline,
            pois,
            started_at,
        )
        if poi_count == 1
        else _metadata_candidates(pois, baseline)
    )

    chosen = _choose_route_candidate(
        candidates,
        poi_count,
        mode,
        baseline,
        resolved_origin,
        resolved_destination,
        started_at,
    )

    if not chosen:
        if baseline.get("source") == SOURCE_AMAP:
            raise HTTPException(
                status_code=404,
                detail=f"没有找到能在当前时间预算内一次经过 {poi_count} 个地点的真实路线",
            )
        return {
            "baseline_minutes": baseline_minutes,
            "detour_minutes": 0,
            "score": 0,
            "pois": [],
            "narrative": _safe_narrative(
                baseline, mode, [], resolved_origin, resolved_destination
            ),
            "route": baseline,
            # P3-4：两个出口都要带 baseline_route，否则响应形状变成条件式的 ——
            # 前端拿不到就静默不画灰虚线，表现为「有时候有对比、有时候没有」且不报错，
            # 正是 P2-5 修过的那类隐性依赖。这里降级后推荐路线就是基准本身。
            "baseline_route": baseline,
            # 同理，trip_id 也必须两个出口都有。少了它前端反馈按钮会带
            # trip_id=null 发出去，接口 422，用户看到的是「点了喜欢没反应」——
            # 而这条降级路径恰恰是最需要收集反馈的一条（没挑出亮点）。
            # pois 为空时反馈无从归因，但模式偏好照样要记下来。
            "trip_id": _remember_recommendation([], mode),
        }

    highlights = _waypoint_highlights(chosen, baseline)

    return {
        "baseline_minutes": baseline_minutes,
        "detour_minutes": chosen["detour_minutes"],
        "score": round(chosen["score"], 2),
        "pois": highlights,
        "narrative": _safe_narrative(
            chosen["route"], mode, highlights, resolved_origin, resolved_destination
        ),
        "route": chosen["route"],
        # P3-4：基准路线原样带出，前端用灰虚线同图画上，「换掉了什么」才看得见。
        # polyline 出 route_engine 时已经是 WGS-84，前端直接用，再转一次会偏约 450 米。
        "baseline_route": baseline,
        # 反馈要能归因到具体的 POI 类型才有意义（见 PreferenceManager）。
        # 前端 ResultView 已经在反馈时回传 result.trip_id，所以这里发一个
        # 轻量的 ticket 出去，不需要改前端 bundle 就能闭环。
        "trip_id": _remember_recommendation(highlights, mode),
        "poi_count": len(highlights),
        "data_source": "amap" if chosen["route"].get("source") == SOURCE_AMAP else "test",
    }


def _collect_highlights(chosen: dict, pois: list) -> list[dict]:
    """返回给前端的沿途亮点：被选中的 POI 打头，再补上确实贴着这条路线的其他候选。

    过去这里写死 `[chosen["poi"]]`，「沿途几个亮点」这个说法给不出来。
    但也不能把沿线搜到的 POI 全塞进去凑数 —— 它们中的大多数并不在最终路线上，
    说「顺路会经过」就是假的。所以按到**选中路线折线**的真实距离过滤。

    距离算不出来（折线退化成单点）时一律跳过：宁可少一个亮点，
    不能把一个可能在两公里外的店说成顺路。
    """
    chosen_poi = chosen["poi"]
    polyline = chosen["route"].get("polyline")
    chosen_distance = point_to_route_meters(chosen_poi.get("location"), polyline)
    if chosen_distance is None:
        return []

    # `distance` is the search-sample distance, not distance to the selected route.
    # Write the measured value for the selected waypoint too.
    chosen_poi = {**chosen_poi, "off_route_meters": chosen_distance}
    highlights = [chosen_poi]
    seen = {_poi_identity(chosen_poi)}

    nearby: list[tuple[float, dict]] = []
    for poi in pois:
        if not isinstance(poi, dict):
            continue
        identity = _poi_identity(poi)
        if identity in seen:
            continue
        distance = point_to_route_meters(poi.get("location"), polyline)
        if distance is None or distance > NEARBY_POI_METERS:
            continue
        seen.add(identity)
        nearby.append((distance, {**poi, "off_route_meters": distance}))

    # 先按贴题度挑「值得说」的，再看评分，最后按贴近路线的程度破平。
    nearby.sort(
        key=lambda item: (
            -poi_fit_score(item[1].get("type")),
            -_normalize_rating(item[1].get("rating", 0)),
            item[0],
        )
    )
    highlights.extend(poi for _distance, poi in nearby[: MAX_RETURNED_POIS - 1])
    return highlights


def _poi_identity(poi: dict) -> tuple:
    """去重用的身份。同一家店在多个采样点会被查到两次，name 相同但 distance 不同。"""
    return (poi.get("name") or "", poi.get("location") or "")


def _remember_recommendation(pois: list[dict], mode: str) -> int:
    """记下这次推荐了哪些 POI，返回 trip_id。

    反馈接口只拿到 trip_id 时要能查回类型 —— 否则 PreferenceManager 无法归因，
    「点了喜欢之后呢」就还是答不上来。
    """
    with _storage_lock:
        trip_id = next(_trip_ids)
        _recommendations[trip_id] = {"mode": mode, "pois": list(pois)}
        if len(_recommendations) > MAX_TRACKED_RECOMMENDATIONS:
            for stale in list(_recommendations)[: len(_recommendations) - MAX_TRACKED_RECOMMENDATIONS]:
                del _recommendations[stale]
    return trip_id


def _safe_narrative(route: dict, mode: str, pois: list, origin: str, destination: str) -> str:
    """叙事永远不该让主接口失败。

    narrative.py 内部已经吃掉了已知的结构异常，这里再包一层是因为它会打外部
    LLM：新的失败形态（连接池耗尽、DNS 异常）不该由主流程承担。

    origin / destination 传的是解析后的请求坐标：手写演示文案靠它们匹配，
    不能靠高德返回的折线首点（会被吸附到最近的路上，差约 11 米就匹配不上）。
    """
    try:
        return generate_narrative(
            route,
            mode,
            pois=pois,
            origin=origin,
            destination=destination,
            allow_demo_narrative=route.get("source") != SOURCE_AMAP,
        )
    except Exception:
        return DEFAULT_NARRATIVE


def _drop_destination_neighbors(pois: list, destination: str, destination_name: str | None = None) -> list:
    """剔除贴着目的地、被当成「途中偶遇」的 POI。

    高德的 place/around 会把终点本身以及同名的地铁站、公交站一起捞进采样走廊，
    它们离终点往往不足 100 米。这类地点不是沿途偶遇，推荐回去会变成
    「为了去终点而绕路」，叙事也跟着串味。
    无坐标的 POI 在这里放行，由后面的候选准备阶段统一丢弃。
    """
    anchor = _parse_coord(destination)
    if anchor is None:
        return list(pois)
    destination_label = _normalize_name(destination_name)
    kept: list = []
    for poi in pois:
        if not isinstance(poi, dict):
            kept.append(poi)
            continue
        coord = _parse_coord(poi.get("navigation_location") or poi.get("location"))
        if coord is None:
            kept.append(poi)
            continue
        distance = _haversine_meters(coord, anchor)
        poi_label = _normalize_name(poi.get("name"))
        same_name = bool(destination_label) and bool(poi_label) and (
            destination_label in poi_label or poi_label in destination_label
        )
        if distance <= ENDPOINT_EXCLUDE_METERS or (same_name and distance <= DEST_NAME_MATCH_METERS):
            continue
        kept.append(poi)
    return kept


def _normalize_name(value) -> str:
    """地名归一化：去空白和括号内的解释性文字，保留用于同名判断的主名。"""
    if not isinstance(value, str):
        return ""
    return re.sub(r"[（(][^）)]*[）)]", "", value).replace(" ", "").replace("　", "")


def _parse_coord(value) -> tuple[float, float] | None:
    """解析 "lng,lat"（WGS-84），非法输入返回 None。"""
    if not isinstance(value, str) or "," not in value:
        return None
    try:
        lng, lat = (float(part) for part in value.split(",", 1))
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lng) and math.isfinite(lat)):
        return None
    return lng, lat


def _haversine_meters(start: tuple[float, float], end: tuple[float, float]) -> float:
    lng1, lat1 = map(math.radians, start)
    lng2, lat2 = map(math.radians, end)
    value = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 6_371_000 * 2 * math.asin(math.sqrt(value))


def _prepare_poi_candidates(pois: list) -> list[tuple[dict, str]]:
    """挑出坐标可用的 POI，按质量初筛后截断。

    优先使用高德给的大型 POI 入口坐标，避免把路线规划到景区/商场的几何中心。
    无评分的人文和公园候选保留一个中性质量，不能被商业门店全部挤掉。
    """
    prepared: list[tuple[dict, str]] = []
    seen: set[str] = set()

    for poi in pois:
        if not isinstance(poi, dict):
            continue
        try:
            coord = normalize_coordinate(poi.get("navigation_location") or poi.get("location"))
        except ValueError:
            continue
        if coord in seen:
            continue
        seen.add(coord)
        prepared.append((poi, coord))

    prepared.sort(key=lambda item: _preliminary_poi_quality(item[0]), reverse=True)
    return prepared[:MAX_CANDIDATES]


def _preliminary_poi_quality(poi: dict) -> tuple[float, int, str]:
    rating = _normalize_rating(poi.get("rating", 0))
    # 类别优先，评分只作为同类目的次级排序，不能让一家高分餐饮挤掉文化地点。
    return _recommendation_quality(poi), rating, str(poi.get("name") or "")


def _evaluate_candidate(
    origin: str,
    destination: str,
    mode: str,
    baseline: dict,
    poi: dict,
    poi_coord: str,
) -> dict | None:
    """算一个候选：经由该 POI 的两段路线、绕行、评分。超预算或算不出返回 None。"""
    try:
        poi_routes = get_candidate_routes(origin, destination, mode, waypoint=poi_coord)
    except Exception:
        return None

    if not poi_routes:
        return None

    candidate_route = poi_routes[0]

    # 关键：候选和基准必须来自同一个数据源。高德被限流或出错时，
    # get_candidate_routes 会静默退回直线几何的兜底路线；拿它跟真实基准比绕行
    # 会算出一个看起来合理、实际编造的「多花 N 分钟」。宁可少一个候选。
    if candidate_route.get("source") != baseline.get("source"):
        return None

    # calculate_detour 已经 clamp 到 0：两段拼接偶尔比基准还短（高德路径规划有
    # 非确定性），界面不能显示「多花 -0.3 分钟」。
    detour_seconds = calculate_detour(baseline["duration"], candidate_route["duration"])
    budget = MAX_DETOUR_MINUTES.get(mode)
    if budget is not None and detour_seconds > budget * 60:
        return None

    detour_minutes = round(detour_seconds / 60, 1)
    # R4：这个 POI 离基准路线多远。这是模式差异的输入 —— 兜底数据下绕行分钟数
    # 常常是 0（7 公里的路上绕 100 米不到一分钟），只靠 detour_minutes 分不开三个模式。
    off_route_meters = point_to_route_meters(poi_coord, baseline.get("polyline"))
    # 标签这一维现在真的参与打分：affinity 来自用户此前的反馈（PreferenceManager）。
    # 没有任何反馈时是 0.0（中性），行为与改造前接近；点过「一般」的类目会被压低，
    # 点过「还不错」的会被抬高 —— 这就是「下次帮你换一条」的实现。
    score = scorer.score(
        detour_minutes=detour_minutes,
        poi_quality=_recommendation_quality(poi),
        tag_affinity=preferences.affinity(poi.get("type")),
    )

    return {
        "poi": poi,
        "route": candidate_route,
        "detour_minutes": detour_minutes,
        "score": score,
        # 只用于 _choose_candidate 排序，不出接口。None 表示算不出（折线退化），
        # 按 0 处理会把一个位置未知的店说成「就在路边」。
        "off_route_meters": off_route_meters,
    }


def _evaluate_candidates(
    origin: str,
    destination: str,
    mode: str,
    baseline: dict,
    pois: list,
    started_at: float,
) -> list[dict]:
    """并发评估候选，受 TOTAL_BUDGET_SECONDS 总预算约束。

    requests 是阻塞 IO，线程池够用。超时的候选直接丢掉，已算完的照常参与选优。
    """
    prepared = _prepare_poi_candidates(pois)
    if not prepared:
        return []

    candidates: list[dict] = []
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(prepared)))
    try:
        futures = [
            executor.submit(_evaluate_candidate, origin, destination, mode, baseline, poi, coord)
            for poi, coord in prepared
        ]
        remaining = TOTAL_BUDGET_SECONDS - (time.monotonic() - started_at)
        done, _pending = concurrent.futures.wait(futures, timeout=max(0.0, remaining))

        for future in done:
            try:
                result = future.result()
            except Exception:
                continue
            if result:
                candidates.append(result)
    finally:
        # 不能等未完成的线程：那会把总预算又拖回串行的时长。
        executor.shutdown(wait=False, cancel_futures=True)

    return candidates


def _metadata_candidates(pois: list, baseline: dict) -> list[dict]:
    """为多途经点组合做无网络初筛；真实绕行只在组合入围后计算。"""
    candidates: list[dict] = []
    for poi, coord in _prepare_poi_candidates(pois):
        offset = point_to_route_meters(coord, baseline.get("polyline"))
        if offset is None:
            continue
        candidates.append(
            {
                "poi": poi,
                "off_route_meters": offset,
                "score": scorer.score(
                    detour_minutes=0,
                    poi_quality=_recommendation_quality(poi),
                    tag_affinity=preferences.affinity(poi.get("type")),
                ),
            }
        )
    return candidates


def _choose_candidate(candidates: list[dict], mode: str) -> dict | None:
    """在预算内挑最值得的候选，模式决定「愿意为它偏离主路多远」。

    `+5` 过去取 `min(detour_minutes)` —— 但预算在 _evaluate_candidate 里已经
    卡过一次了，进到这里的候选**都**满足 +5 的 5 分钟上限，再取最小绕行等于
    让 3.5 分零绕行的店赢过 4.9 分绕 1 分钟的店：默认模式下评分体系完全不
    参与选择。既然是「顺手一绕」而不是「尽量别绕」，就该在预算内挑最值得的。

    R4：但「三个模式一视同仁」走到了另一个极端 —— 三个模式挑出同一个 POI、
    同一条折线，界面上三份结果只有假数字不同。现在按 DETOUR_APPETITE 给离线距离
    记一笔排序代价：`+5` 偏向贴着路线的地方，`roam` 只看分。**返回给前端的 score
    不受影响**（那是探索价值，7 分制），这笔代价只活在排序键里。

    并列时用绕行少的那个破平；仍并列再按离线距离和名字排序，
    保证结果稳定、不依赖并发线程的完成顺序。
    """
    if not candidates:
        return None

    appetite = DETOUR_APPETITE.get(mode, 0.2)

    def rank(item: dict) -> tuple:
        off_route = item.get("off_route_meters")
        # 算不出距离时按最大惩罚处理：位置说不清的店不该因为「距离未知」占到便宜。
        penalty = appetite * (POI_SEARCH_RADIUS if off_route is None else off_route) / 100
        # 同分同绕行时，评分相同的地点先比离线距离（远点更符合 roam 的探索感），
        # 再比名字，杜绝 max 依赖线程完成顺序的隐性随机。
        farther_first = off_route if off_route is not None else 0.0
        name = str(item.get("poi", {}).get("name") or "")
        return (item["score"] - penalty, -item["detour_minutes"], farther_first, name)

    return max(candidates, key=rank)


def _choose_route_candidate(
    candidates: list[dict],
    poi_count: int,
    mode: str,
    baseline: dict,
    origin: str,
    destination: str,
    started_at: float,
) -> dict | None:
    """选出一个或多个真实途经点，并返回经过它们的完整路线。"""
    if poi_count == 1:
        chosen = _choose_candidate(candidates, mode)
        if chosen:
            chosen = {**chosen, "items": [chosen]}
        return chosen

    if len(candidates) < poi_count:
        return None

    ranked_sets: list[tuple[float, list[dict]]] = []
    appetite = DETOUR_APPETITE.get(mode, 0.2)
    for group in combinations(candidates, poi_count):
        with_progress = [
            (
                point_to_route_progress(
                    item["poi"].get("navigation_location") or item["poi"].get("location"),
                    baseline.get("polyline"),
                ),
                item,
            )
            for item in group
        ]
        if any(progress is None for progress, _item in with_progress):
            continue
        with_progress.sort(key=lambda pair: pair[0])
        progresses = [progress for progress, _item in with_progress]
        ordered = [item for _progress, item in with_progress]

        # 太靠近的两个点不是一次「绕两个地方」，只是同一街区重复计数。
        separation_bonus = sum(
            min(0.2, max(0.0, progresses[index + 1] - progresses[index]))
            for index in range(len(progresses) - 1)
        )
        categories = {str(item["poi"].get("type") or "").split(";", 1)[0] for item in ordered}
        diversity_bonus = 0.25 * max(0, len(categories) - 1)
        distance_penalty = sum(
            appetite
            * float(
                POI_SEARCH_RADIUS
                if item.get("off_route_meters") is None
                else item["off_route_meters"]
            )
            / 100
            for item in ordered
        )
        cheap_rank = (
            sum(float(item["score"]) for item in ordered) / len(ordered)
            + separation_bonus
            + diversity_bonus
            - distance_penalty
        )
        ranked_sets.append((cheap_rank, ordered))

    ranked_sets.sort(key=lambda entry: entry[0], reverse=True)
    feasible: list[dict] = []
    for _cheap_rank, items in ranked_sets[:MAX_ROUTE_SET_EVALUATIONS]:
        if time.monotonic() - started_at >= TOTAL_BUDGET_SECONDS:
            break
        waypoint_coords = [
            normalize_coordinate(item["poi"].get("navigation_location") or item["poi"].get("location"))
            for item in items
        ]
        try:
            route = get_route_via_waypoints(origin, destination, waypoint_coords)
        except Exception:
            continue
        if not route:
            continue
        detour_seconds = calculate_detour(baseline["duration"], route["duration"])
        if detour_seconds > MAX_DETOUR_MINUTES[mode] * 60:
            continue
        detour_minutes = round(detour_seconds / 60, 1)
        score = _score_poi_set(items, detour_minutes)
        feasible.append(
            {
                "items": items,
                "poi": items[0]["poi"],
                "route": route,
                "detour_minutes": detour_minutes,
                "score": score,
            }
        )

    if not feasible:
        return None
    return max(feasible, key=lambda item: (item["score"], -item["detour_minutes"]))


def _score_poi_set(items: list[dict], detour_minutes: float) -> float:
    qualities = [_recommendation_quality(item["poi"]) for item in items]
    affinities = [preferences.affinity(item["poi"].get("type")) for item in items]
    return scorer.score(
        detour_minutes=detour_minutes,
        poi_quality=sum(qualities) / len(qualities),
        tag_affinity=sum(affinities) / len(affinities),
    )


def _waypoint_highlights(chosen: dict, baseline: dict) -> list[dict]:
    """把真正参与规划的途经点按访问顺序返回，并生成可核实的推荐理由。"""
    highlights = []
    route = chosen["route"]
    for index, item in enumerate(chosen.get("items") or [chosen], start=1):
        poi = item["poi"]
        location = poi.get("navigation_location") or poi.get("location")
        baseline_offset = point_to_route_meters(location, baseline.get("polyline"))
        route_offset = point_to_route_meters(location, route.get("polyline"))
        enriched = {
            **poi,
            "visit_order": index,
            "is_waypoint": True,
            "baseline_offset_meters": baseline_offset,
            "off_route_meters": route_offset,
        }
        enriched["introduction"] = _poi_introduction(enriched)
        enriched["discovery_kind"] = _discovery_kind(enriched)
        enriched["reason"] = _poi_reason(enriched)
        highlights.append(enriched)
    return highlights


def _poi_introduction(poi: dict) -> str:
    parts = []
    poi_type = str(poi.get("type") or "").split(";")
    readable_type = next((part for part in reversed(poi_type) if part and not part.endswith("服务")), "")
    if readable_type:
        parts.append(readable_type)
    if poi.get("address"):
        parts.append(str(poi["address"]))
    return " · ".join(parts)


def _poi_reason(poi: dict) -> str:
    kind = _discovery_kind(poi)
    facts = [{"heritage": "古迹与人文地标优先", "scenic": "风景与自然地点优先", "cultural": "文化场馆优先"}.get(kind, "真实地点信息")]
    rating = _normalize_rating(poi.get("rating", 0))
    if rating > 0:
        facts.append(f"高德评分 {rating:.1f}")
    else:
        facts.append("高德暂无评分")
    offset = poi.get("baseline_offset_meters")
    if isinstance(offset, (int, float)) and math.isfinite(offset):
        facts.append(f"距原本路线约 {round(offset)} 米")
    poi_type = str(poi.get("type") or "").split(";")[-1].strip()
    if poi_type:
        facts.append(poi_type)
    return "，".join(facts)


def _discovery_kind(poi: dict) -> str:
    """只保留文化/风景候选，并抵挡高德分类不精确时的商业名称。"""
    typecode = str(poi.get("typecode") or "")
    text = " ".join(str(poi.get(field) or "") for field in ("name", "type", "address")).lower()
    if any(word in text for word in DISCOVERY_EXCLUDED_WORDS):
        return ""
    if typecode.startswith("14") and not typecode.startswith(
        ("1403", "1404", "1405", "1406", "1407", "1408", "1409", "1410", "1411", "1412")
    ):
        return ""
    if any(word in text for word in HERITAGE_WORDS):
        return "heritage"
    if any(word in text for word in SCENIC_WORDS):
        return "scenic"
    if any(word in text for word in CULTURAL_WORDS):
        return "cultural"
    if typecode.startswith("140"):
        return "cultural"
    if typecode.startswith("110"):
        return "scenic"
    return ""


def _discovery_quality(poi: dict) -> float:
    """类别是主信号；高德评分仅作小幅同类打破平局，不假造客流数据。"""
    base = {"heritage": 0.98, "scenic": 0.91, "cultural": 0.85}.get(_discovery_kind(poi), 0.0)
    rating = _normalize_rating(poi.get("rating", 0))
    # 高德 v3 POI 响应并不稳定提供评价人数，不能把「高分」谎称为「小众宝藏」。
    return min(1.0, base + (rating / 5.0) * 0.02)


def _recommendation_quality(poi: dict) -> float:
    """线上真实候选使用发现策略；仅用于旧离线演示数据时保留原评分行为。"""
    if poi.get("source") == SOURCE_AMAP:
        return _discovery_quality(poi)
    rating = _normalize_rating(poi.get("rating", 0))
    return (rating if rating > 0 else 3.8) / 5.0


def _normalize_rating(value) -> float:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(rating):
        return 0.0
    return min(5.0, max(0.0, rating))


@router.post("/trip/save", response_model=None)
def save_trip(payload: dict = Body(default_factory=dict)):
    """收藏一条路线。进程内存储，返回 {ok, id}。

    前端 saveTrip 拿不到 200 就显示「收藏失败」，所以这里不校验业务字段：
    存不下也不该让用户看到失败，最多是重启后丢历史。
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="收藏内容格式不正确")

    with _storage_lock:
        trip_id = next(_trip_ids)
        _saved_trips.append({"id": trip_id, "saved_at": time.time(), "trip": payload})
        # 只保留最近的若干条，避免长时间运行把内存吃掉。
        if len(_saved_trips) > MAX_STORED_TRIPS:
            del _saved_trips[: len(_saved_trips) - MAX_STORED_TRIPS]

    return {"ok": True, "id": trip_id}


@router.get("/trip/list", response_model=None)
def list_trips():
    """收藏列表，最近收藏的在前。"""
    with _storage_lock:
        trips = list(reversed(_saved_trips))
    return {"trips": trips}


@router.post("/feedback", response_model=None)
def submit_feedback(payload: dict = Body(default_factory=dict)):
    """路线反馈（喜欢 / 不喜欢）。写进 PreferenceManager，影响**后续**推荐的打分。

    这是 P2-2 的闭环入口。归因链：前端回传 trip_id -> `_recommendations` 查出
    当时推荐的 POI -> `tags_for_type` 归并成粗类目 -> 计数 -> 下次
    `scorer.score` 的 tag_affinity。

    归因失败（没有 trip_id、或 id 已被淘汰）时仍然返回 200：反馈按钮不该报错，
    只是这一次学不到东西。响应里的 `learned` 会说明有没有真的学到。
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="反馈内容格式不正确")

    liked = bool(payload.get("liked"))
    mode = payload.get("mode")

    with _storage_lock:
        _feedback_entries.append({"received_at": time.time(), "feedback": payload})
        if len(_feedback_entries) > MAX_STORED_FEEDBACK:
            del _feedback_entries[: len(_feedback_entries) - MAX_STORED_FEEDBACK]
        tracked = _recommendations.get(_coerce_trip_id(payload.get("trip_id")))

    # 优先用服务端记下的 POI：前端只发 trip_id 时也能归因。
    # payload 里带 pois 的话（未来前端直接回传）就用它，省一次查表。
    pois = payload.get("pois")
    if not isinstance(pois, list) or not pois:
        pois = (tracked or {}).get("pois") or []

    learned = preferences.record_feedback(
        liked, pois=pois, mode=mode if isinstance(mode, str) else None
    )

    return {"ok": True, "learned": learned}


def _coerce_trip_id(value) -> int | None:
    """trip_id 可能是 int、字符串数字、None，或前端塞来的任意脏值。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@router.get("/preference", response_model=None)
def read_preference():
    """当前学到的偏好。给演示时「证明反馈真的生效」用 —— 台上可以直接打开看。"""
    return {"mode": preferences.get_mode(), "tags": preferences.snapshot()}


@router.get("/place/suggest", response_model=None)
def suggest_places(
    keyword: str = Query(..., min_length=1),
    city: str = Query(""),
):
    """地点联想，转发高德 /v3/assistant/inputtips。

    正式联调不再把配置错误和高德故障伪装成「没有结果」：缺 Key 返回 503，
    上游失败返回 502。city 为空时全国搜索，传入城市时才严格限制城市。
    """
    keyword = keyword.strip()
    if not keyword:
        return {"suggestions": []}

    amap_key = os.getenv("AMAP_KEY")
    if not amap_key:
        raise HTTPException(status_code=503, detail="真实高德地点联想服务未配置")

    params = {"keywords": keyword, "key": amap_key}
    if city.strip():
        params.update({"city": city.strip(), "citylimit": "true"})

    try:
        throttle_amap()
        response = requests.get(INPUTTIPS_URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=502, detail=f"高德地点联想失败：{exc}") from exc

    if not isinstance(data, dict) or str(data.get("status")) != "1":
        info = data.get("info") if isinstance(data, dict) else "响应格式错误"
        infocode = data.get("infocode") if isinstance(data, dict) else ""
        raise HTTPException(
            status_code=502,
            detail=f"高德地点联想失败：{info or '未知错误'} ({infocode})",
        )

    tips = data.get("tips", []) if isinstance(data, dict) else []
    return {"suggestions": [tip for tip in map(_normalize_tip, tips) if tip]}


def _normalize_tip(tip) -> dict | None:
    """高德联想条目 -> 前端结构。location 从 GCJ-02 转成 WGS-84。

    两个坑：无坐标的行政区条目 location 是空数组 `[]`；
    district 也可能是 `[]`。都得当成「没有」而不是直接塞给前端。
    """
    if not isinstance(tip, dict):
        return None

    name = tip.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    location = tip.get("location")
    # 联想列表只返回可直接用于规划的实体地点。行政区等没有坐标的提示虽然有名称，
    # 但不能可靠地成为“从这里出发”的位置，保留它会让前端看起来可选、提交后才失败。
    if not isinstance(location, str) or "," not in location:
        return None
    location = gcj02_str_to_wgs84_str(location) or ""
    if not location:
        return None

    district = tip.get("district")
    address = tip.get("address")

    return {
        "id": tip.get("id") if isinstance(tip.get("id"), str) else "",
        "name": name.strip(),
        "typecode": tip.get("typecode") if isinstance(tip.get("typecode"), str) else "",
        "address": address if isinstance(address, str) else "",
        "district": district if isinstance(district, str) else "",
        "location": location,
    }
