import concurrent.futures
import itertools
import math
import os
import threading
import time

import requests
from fastapi import APIRouter, Body, HTTPException, Query

from app.models.preference import PreferenceManager
from app.services.coord import gcj02_str_to_wgs84_str
from app.services.detour_calculator import calculate_detour
from app.services.geocoder import normalize_coordinate, resolve_location
from app.services.narrative import DEFAULT_NARRATIVE, generate_narrative
from app.services.poi_explorer import explore_pois_along_route
from app.services.route_engine import get_candidate_routes, point_to_route_meters, throttle_amap
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

# 每个候选要两次高德步行调用（步行接口不支持 waypoint，只能两段拼接）。
# 截断到 3 个是为了控制配额：一次请求约 7 次调用。
MAX_CANDIDATES = 3
# 高德对同一个 Key 有并发上限（infocode 10021），route_engine 里已按
# AMAP_MIN_INTERVAL_SECONDS 限流，这里再开大线程池只会互相排队并触发限流重试。
MAX_WORKERS = 2
# 整个 recommend 的总预算。超时就用已经算完的候选，不空手而归。
TOTAL_BUDGET_SECONDS = 8.0
# 沿线采样每个点的搜索半径。三点覆盖整条路线，单点半径可以放大到 400 米。
POI_SEARCH_RADIUS = 400

# 返回给前端的沿途亮点上限。第一个必定是被选中的那个 POI（路线真的经过它），
# 其余是**确实贴着这条路线**的其他候选。
MAX_RETURNED_POIS = 3
# 「顺路」的判定半径。超过这个距离就不能说「沿途会经过」——
# 卖「偶遇」的产品不能在这句话上注水，宁可只返回一个亮点。
# 400 米约等于步行 5 分钟的绕行，与 POI_SEARCH_RADIUS 同量级。
NEARBY_POI_METERS = 400

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
):
    started_at = time.monotonic()

    if mode not in SUPPORTED_MODES:
        raise HTTPException(status_code=422, detail="不支持的探索模式")

    # 校验通过后立刻记下模式：`GET /api/preference` 是演示时用来证明「它记住了」的，
    # 只靠反馈写入的话，用户连点三次 +15 那个接口还会显示 +5。
    preferences.set_mode(mode)

    if not origin or not destination:
        raise HTTPException(status_code=404, detail="未找到可行路线")

    try:
        resolved_origin = resolve_location(origin)
        resolved_destination = resolve_location(destination)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未找到可行路线") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail=f"地点解析失败：{exc}") from exc

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
    baseline_minutes = round(baseline["duration"] / 60)

    try:
        # 传基准折线：POI 按里程 25%/50%/75% 三点采样，而不是只看起终点中点。
        pois = explore_pois_along_route(
            resolved_origin,
            resolved_destination,
            ["餐饮", "景点", "购物"],
            radius=POI_SEARCH_RADIUS,
            polyline=baseline.get("polyline"),
        )
    except Exception:
        pois = []

    candidates = _evaluate_candidates(
        resolved_origin,
        resolved_destination,
        mode,
        baseline,
        pois,
        started_at,
    )

    chosen = _choose_candidate(candidates, mode)

    if not chosen:
        return {
            "baseline_minutes": baseline_minutes,
            "detour_minutes": 0,
            "score": 0,
            "pois": [],
            "narrative": _safe_narrative(
                baseline, mode, [], resolved_origin, resolved_destination
            ),
            "route": baseline,
        }

    highlights = _collect_highlights(chosen, pois)

    return {
        "baseline_minutes": baseline_minutes,
        "detour_minutes": chosen["detour_minutes"],
        "score": round(chosen["score"], 2),
        "pois": highlights,
        "narrative": _safe_narrative(
            chosen["route"], mode, highlights, resolved_origin, resolved_destination
        ),
        "route": chosen["route"],
        # 反馈要能归因到具体的 POI 类型才有意义（见 PreferenceManager）。
        # 前端 ResultView 已经在反馈时回传 result.trip_id，所以这里发一个
        # 轻量的 ticket 出去，不需要改前端 bundle 就能闭环。
        "trip_id": _remember_recommendation(highlights, mode),
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
    highlights = [chosen_poi]
    polyline = chosen["route"].get("polyline")
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
        nearby.append((distance, poi))

    # 先按评分挑「值得说」的，同分再按贴近路线的程度破平。
    nearby.sort(key=lambda item: (-_normalize_rating(item[1].get("rating", 0)), item[0]))
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
            route, mode, pois=pois, origin=origin, destination=destination
        )
    except Exception:
        return DEFAULT_NARRATIVE


def _prepare_poi_candidates(pois: list) -> list[tuple[dict, str]]:
    """挑出坐标可用的 POI，按评分降序去重，截断到 MAX_CANDIDATES 个。"""
    prepared: list[tuple[dict, str]] = []
    seen: set[str] = set()

    for poi in pois:
        if not isinstance(poi, dict):
            continue
        try:
            coord = normalize_coordinate(poi.get("location"))
        except ValueError:
            continue
        if coord in seen:
            continue
        seen.add(coord)
        prepared.append((poi, coord))

    prepared.sort(key=lambda item: _normalize_rating(item[0].get("rating", 0)), reverse=True)
    return prepared[:MAX_CANDIDATES]


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

    detour_minutes = round(detour_seconds / 60)
    rating = _normalize_rating(poi.get("rating", 0))
    # 标签这一维现在真的参与打分：affinity 来自用户此前的反馈（PreferenceManager）。
    # 没有任何反馈时是 0.0（中性），行为与改造前接近；点过「一般」的类目会被压低，
    # 点过「还不错」的会被抬高 —— 这就是「下次帮你换一条」的实现。
    score = scorer.score(
        detour_minutes=detour_minutes,
        poi_quality=rating / 5.0,
        tag_affinity=preferences.affinity(poi.get("type")),
    )

    return {
        "poi": poi,
        "route": candidate_route,
        "detour_minutes": detour_minutes,
        "score": score,
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


def _choose_candidate(candidates: list[dict], mode: str) -> dict | None:
    """在预算内挑分最高的候选。三个模式一视同仁。

    `+5` 过去取 `min(detour_minutes)` —— 但预算在 _evaluate_candidate 里已经
    卡过一次了，进到这里的候选**都**满足 +5 的 5 分钟上限，再取最小绕行等于
    让 3.5 分零绕行的店赢过 4.9 分绕 1 分钟的店：默认模式下评分体系完全不
    参与选择。既然是「顺手一绕」而不是「尽量别绕」，就该在预算内挑最值得的。

    并列时用绕行少的那个破平，保证结果稳定、不依赖候选顺序。
    """
    if not candidates:
        return None

    return max(candidates, key=lambda item: (item["score"], -item["detour_minutes"]))


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
    city: str = Query("大连"),
):
    """地点联想，转发高德 /v3/assistant/inputtips。

    没有 AMAP_KEY 或高德出错时返回空列表 —— 输入框退化成纯文本输入，
    这比抛 500 让前端弹错误提示好。
    """
    keyword = keyword.strip()
    if not keyword:
        return {"suggestions": []}

    amap_key = os.getenv("AMAP_KEY")
    if not amap_key:
        return {"suggestions": []}

    params = {"keywords": keyword, "city": city, "citylimit": "true", "key": amap_key}

    try:
        throttle_amap()
        response = requests.get(INPUTTIPS_URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, TypeError, ValueError, AttributeError):
        return {"suggestions": []}

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
    if not isinstance(location, str) or "," not in location:
        # 没有坐标的条目留着也能用：前端会把 name 当文本再走一次地理编码。
        location = ""
    else:
        location = gcj02_str_to_wgs84_str(location) or ""

    district = tip.get("district")
    address = tip.get("address")

    return {
        "name": name.strip(),
        "address": address if isinstance(address, str) else "",
        "district": district if isinstance(district, str) else "",
        "location": location,
    }
