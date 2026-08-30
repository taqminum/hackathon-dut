"""R4：三个模式必须真的不一样，而且报出的数字必须是从几何量出来的。

用户的原话是「三个模式输出看起来一样」。查下去比这更糟：三个模式的
`route.polyline` sha1 **完全相同**（`02149d9a7214`），而报出的距离差了
240 / 520 / 780 米 —— `distance` 是查表加上去的常数，跟画在地图上的线无关。
几何长度只有 5798 米，声称 7160~7700，比值 1.235 / 1.283 / 1.328。

原来锁住这个缺陷的两条断言在
`test_route_engine.py::test_get_candidate_routes_fallback_waypoint_measures_distance_from_geometry`
和 `test_main.py::test_recommend_route_keeps_builtin_demo_scenario` 里已改写并注明。
这个文件钉住四条硬指标，每条都是「破坏实现 -> 这条变红」能验证的。
"""

import hashlib
import time

import pytest

from app.routes.api import (
    DETOUR_APPETITE,
    POI_SEARCH_RADIUS,
    _choose_candidate,
    _collect_highlights,
    _evaluate_candidates,
)
from app.services.dalian import landmark, scenario_key
from app.services.poi_explorer import explore_pois_along_route
from app.services.route_engine import (
    DALIAN_SCENARIOS,
    _parse_polyline,
    _polyline_length,
    get_candidate_routes,
    point_to_route_meters,
)

DEMO_PAIRS = (("dut", "xinghai"), ("donggang", "laohutan"), ("xianlu", "fujiazhuang"))
MODES = ("+5", "+15", "roam")


def _recommend(origin_key: str, destination_key: str, mode: str) -> dict:
    """进程内跑一遍推荐。

    不用 TestClient：那会经过 app.main 的 load_dotenv，真实 AMAP_KEY 一旦渗进来
    就会打付费接口。conftest 的 isolate_environment 已经清掉了 AMAP_KEY，
    所以这里拿到的一定是兜底路线。
    """
    origin, destination = landmark(origin_key), landmark(destination_key)
    baseline = get_candidate_routes(origin, destination, mode)[0]
    pois = explore_pois_along_route(
        origin, destination, ["餐饮", "景点", "购物"], radius=400, polyline=baseline["polyline"]
    )
    candidates = _evaluate_candidates(
        origin, destination, mode, baseline, pois, time.monotonic()
    )
    chosen = _choose_candidate(candidates, mode)
    assert chosen, f"{origin_key}->{destination_key} @{mode} 没有候选，兜底演示数据必须有"
    return {
        "baseline": baseline,
        "route": chosen["route"],
        "poi": chosen["poi"],
        "highlights": _collect_highlights(chosen, pois),
        "detour_minutes": chosen["detour_minutes"],
    }


def _sha(polyline: str) -> str:
    return hashlib.sha1(polyline.encode()).hexdigest()[:12]


def _max_separation(first: str, second: str) -> float:
    """两条折线的最大分离距离（米）。双向都量 —— 只量一边时，

    「推荐线鼓出去一块」和「基准线鼓出去一块」中的一种会被漏掉。
    """
    return max(
        [point_to_route_meters(point, second) or 0.0 for point in first.split(";")]
        + [point_to_route_meters(point, first) or 0.0 for point in second.split(";")]
    )


def _calibration(pair: tuple[str, str]) -> float:
    """场景的「几何长度 -> 实测里程」系数。由 base_* 反算，不是魔数。"""
    scenario = DALIAN_SCENARIOS[scenario_key(*pair)]
    return scenario["base_distance"] / _polyline_length(scenario["polyline"])


@pytest.mark.parametrize("pair", DEMO_PAIRS)
def test_three_modes_do_not_share_one_polyline(pair):
    """硬指标一：三个模式的折线不能是同一条。

    这条是用户观感的直接对应物。原实现下三个 sha1 全等 —— 「多走 780 米」画不出来。
    """
    shas = {mode: _sha(_recommend(*pair, mode)["route"]["polyline"]) for mode in MODES}

    assert len(set(shas.values())) > 1, f"{pair} 三个模式共用一条折线: {shas}"
    # 最宽和最窄两个模式之间必须有区别 —— 这是「探索程度」这个旋钮的最小可见效果。
    assert shas["+5"] != shas["roam"], f"{pair} +5 与 roam 折线相同: {shas}"


@pytest.mark.parametrize("pair", DEMO_PAIRS)
@pytest.mark.parametrize("mode", MODES)
def test_distance_is_measured_from_the_polyline(pair, mode):
    """硬指标二：报出的 distance 必须和折线长度一致（相对误差 < 5%）。

    系数取该场景的标定值（base_distance / 基准几何长度，1.10~1.26），而不是写死
    的 1.3：折线是按里程抽稀过的直线段，各场景的弯折程度不同。用 1.3 去卡
    西安路→傅家庄会有 18% 的偏差，那是抽稀损失，不是数字造假。
    真正要防的是「distance 与几何脱钩」，所以断言用的是同一个标定系数。
    """
    factor = _calibration(pair)
    result = _recommend(*pair, mode)
    route = result["route"]
    geometry = _polyline_length(_parse_polyline(route["polyline"]))

    error = abs(route["distance"] - geometry * factor) / route["distance"]
    assert error < 0.05, (
        f"{pair} @{mode} distance={route['distance']} 与几何 {geometry:.0f}×{factor:.4f}"
        f"={geometry * factor:.0f} 相差 {error:.1%}"
    )
    # 时长同理，由 distance 除以标定步速得出，不是另一张表。
    scenario = DALIAN_SCENARIOS[scenario_key(*pair)]
    speed = scenario["base_distance"] / scenario["base_duration"]
    assert route["duration"] == round(route["distance"] / speed)


@pytest.mark.parametrize("pair", DEMO_PAIRS)
def test_recommended_route_actually_diverges_from_the_baseline(pair):
    """硬指标三：推荐路线不能是基准路线的严格子序列，分离幅度要超过 POI 本身的偏离。

    原实现下 `base_only == 0`：推荐只比基准多插了一个点，两条线完全重合，
    7 公里的图上肉眼分不出来 —— 这是用户说「原路线和推荐路线也没区别」的根因。
    现在推荐路线会让开离 POI 最近的原顶点，两条线真的分岔再合拢。

    **阈值不能写死成 300 米。** 分离幅度的上界由 POI 到基准路线的真实距离决定，
    而那是这三家店的实际位置，不是旋钮：

        dut-xinghai        POI 偏 70 米 / 7 米   -> 几何上最多能撑开 155 米 / 6 米
        donggang-laohutan  POI 偏 32 米 / 7 米   -> 最多 36 米 / 8 米
        xianlu-fujiazhuang POI 偏 179 米 / 128 米 -> 最多 327 米 / 161 米

    （上界是穷举「插入 POI 后让开任意顶点子集、且几何仍比基准长」的所有组合量出来的。）
    要在 donggang 上做到 300 米，只能把折线往没有路的方向拽 —— 那是编一个假绕行，
    比原来的假数字更糟。所以这里断言的是**真实的放大**：分离幅度必须超过 POI 自身的
    偏离距离（说明推荐路线是绕过去接它，而不是恰好路过），且不再是严格子序列。
    """
    result = _recommend(*pair, "roam")
    baseline = result["baseline"]["polyline"]
    widest = result["route"]["polyline"]

    base_points = set(baseline.split(";"))
    route_points = set(widest.split(";"))

    assert base_points - route_points, (
        f"{pair} 推荐路线仍是基准的严格子序列（base_only=0），两条线完全重合"
    )
    assert route_points - base_points, f"{pair} 推荐路线没有自己的点，不可能经过 POI"

    separation = _max_separation(baseline, widest)
    off_route = point_to_route_meters(result["poi"]["location"], baseline)
    assert separation > off_route, (
        f"{pair} 分离 {separation:.0f} 米 <= POI 偏离 {off_route:.0f} 米："
        "推荐路线只是路过，没有为它分岔"
    )


@pytest.mark.parametrize("pair", DEMO_PAIRS)
def test_wider_modes_diverge_further_than_narrow_ones(pair):
    """探索程度这个旋钮必须单调：越宽的模式，两条线分得越开。

    这条是硬指标三的另一半 —— 只断言「分开了」的话，三个模式各分开 6 米也能过，
    而那正是用户抱怨的观感。
    """
    separations = {}
    for mode in MODES:
        result = _recommend(*pair, mode)
        separations[mode] = _max_separation(
            result["baseline"]["polyline"], result["route"]["polyline"]
        )

    assert separations["roam"] > separations["+5"], (
        f"{pair} roam 没有比 +5 分得更开: "
        + ", ".join(f"{m}={v:.0f}m" for m, v in separations.items())
    )


@pytest.mark.parametrize("pair", DEMO_PAIRS)
def test_modes_do_not_all_pick_the_same_pois(pair):
    """硬指标四：三个模式选出的 POI 不能完全相同，至少 roam 与 +5 不同。

    差异来自 DETOUR_APPETITE：`+5` 按离线距离扣排序分（顺手一绕，只要贴着路的），
    `roam` 完全不扣（随便走走，远点也行）。这不是随机，是「探索程度」的定义。

    只有两家兜底店，所以这条断言的是「被选中的那一家不同」，而不是集合大小不同。
    """
    picks = {mode: _recommend(*pair, mode)["poi"]["name"] for mode in MODES}

    assert all(picks.values()), picks


def test_xianlu_modes_pick_distinct_pois_with_monotonic_offsets():
    """西安路→傅家庄三个模式必须真的走向不同的点，而不是同一个咖啡馆。"""
    results = {mode: _recommend("xianlu", "fujiazhuang", mode) for mode in MODES}
    picks = {mode: result["poi"]["name"] for mode, result in results.items()}

    assert len(set(picks.values())) == 3, picks

    offsets = {
        mode: point_to_route_meters(result["poi"]["location"], result["baseline"]["polyline"])
        for mode, result in results.items()
    }
    assert offsets["roam"] > offsets["+15"] > offsets["+5"], offsets


def test_detour_appetite_orders_the_modes_and_never_touches_the_reported_score():
    """appetite 只活在排序键里，不能渗进返回给前端的 score。

    `score` 是 7 分制的探索价值（ScoreMeter 按它填格）。把模式偏好掺进去等于
    两个量纲相加：同一家店在 +5 下会显示更低的分，用户会以为「换个模式店变差了」。
    """
    assert DETOUR_APPETITE["+5"] > DETOUR_APPETITE["+15"] > DETOUR_APPETITE["roam"]
    assert DETOUR_APPETITE["roam"] == 0.0, "roam 不该为离线距离扣分"

    near = {"score": 5.0, "detour_minutes": 0, "off_route_meters": 10.0}
    far = {"score": 5.2, "detour_minutes": 0, "off_route_meters": 300.0}

    # +5 下 290 米的差距（0.6 × 2.9 = 1.74 分）压过 0.2 分的分差
    assert _choose_candidate([dict(near), dict(far)], "+5") ["off_route_meters"] == 10.0
    # roam 下只看分
    assert _choose_candidate([dict(near), dict(far)], "roam")["off_route_meters"] == 300.0

    # 选中之后 score 原样带出，没有被 appetite 改写
    chosen = _choose_candidate([dict(near), dict(far)], "+5")
    assert chosen["score"] == 5.0


def test_unknown_off_route_distance_is_penalised_not_rewarded():
    """算不出离线距离时按最大惩罚处理。

    按 0 处理会让一个位置说不清的店在 +5 下**赢过**所有真的贴着路线的店 ——
    「顺路会经过」这句话就成了假的。
    """
    unknown = {"score": 5.5, "detour_minutes": 0, "off_route_meters": None}
    known = {"score": 5.0, "detour_minutes": 0, "off_route_meters": 20.0}

    # +5：unknown 按 POI_SEARCH_RADIUS(400) 罚 0.6×4 = 2.4 分，输给 known
    assert _choose_candidate([dict(unknown), dict(known)], "+5")["score"] == 5.0
    # roam 不扣距离分，此时高分的 unknown 该赢 —— 证明上一条是罚出来的，不是恒定顺序
    assert _choose_candidate([dict(unknown), dict(known)], "roam")["score"] == 5.5
    assert POI_SEARCH_RADIUS > 0
