"""兜底表的一致性约束。

三张表的 key 必须完全相同（4 位小数），漏改一张就会静默退化成非演示模式 ——
这类回归不会让任何现有用例变红，所以在这里显式钉住。
"""

from unittest.mock import patch

import pytest

from app.services.dalian import LANDMARKS, landmark, scenario_key
from app.services.narrative import DALIAN_SCENARIO_NARRATIVES
from app.services.poi_explorer import DALIAN_POI_SCENARIOS
from app.routes.api import MAX_DETOUR_MINUTES
from app.services.route_engine import DALIAN_SCENARIOS, get_candidate_routes

DEMO_PAIRS = (("dut", "xinghai"), ("donggang", "laohutan"), ("xianlu", "fujiazhuang"))


def test_three_fallback_tables_share_identical_keys():
    assert set(DALIAN_SCENARIOS) == set(DALIAN_POI_SCENARIOS)
    assert set(DALIAN_SCENARIOS) == set(DALIAN_SCENARIO_NARRATIVES)


def test_expected_demo_pairs_are_present_in_every_table():
    for origin, destination in DEMO_PAIRS:
        key = scenario_key(origin, destination)
        assert key in DALIAN_SCENARIOS, key
        assert key in DALIAN_POI_SCENARIOS, key
        assert key in DALIAN_SCENARIO_NARRATIVES, key


def test_scenario_polyline_endpoints_match_landmarks():
    """折线首尾必须正好是地标坐标，否则兜底路线会从起点旁边几十米处开始画。"""
    for origin, destination in DEMO_PAIRS:
        scenario = DALIAN_SCENARIOS[scenario_key(origin, destination)]
        assert scenario["polyline"][0] == landmark(origin)
        assert scenario["polyline"][-1] == landmark(destination)


def test_fallback_pois_sit_close_to_their_scenario_polyline():
    """兜底 POI 必须真的在兜底路线附近，不然「沿途亮点」这个说法就是假的。"""
    from app.services.route_engine import _parse_lng_lat, _point_to_segment_meters

    for origin, destination in DEMO_PAIRS:
        key = scenario_key(origin, destination)
        points = [_parse_lng_lat(point) for point in DALIAN_SCENARIOS[key]["polyline"]]

        for poi in DALIAN_POI_SCENARIOS[key]:
            location = _parse_lng_lat(poi["location"])
            nearest = min(
                _point_to_segment_meters(location, points[i], points[i + 1])
                for i in range(len(points) - 1)
            )
            assert nearest < 500, f"{poi['name']} 距兜底折线 {nearest:.0f} 米"


def test_fallback_pois_are_on_theme_not_ordinary_dining():
    """演示路线不该推荐满屏烧烤/海鲜：兜底 POI 必须是有贴题度的地点。"""
    from app.services.poi_explorer import poi_fit_score

    for key, pois in DALIAN_POI_SCENARIOS.items():
        for poi in pois:
            assert poi_fit_score(poi["type"]) > 0, (
                f"{poi['name']} 不是贴题的风景/人文/书店/咖啡地点: {poi['type']}"
            )


def test_landmark_coordinates_are_inside_dalian():
    for slug, (name, lng, lat) in LANDMARKS.items():
        assert 121.0 < lng < 122.5, (slug, name, lng)
        assert 38.5 < lat < 39.5, (slug, name, lat)


def test_fallback_waypoint_polyline_does_not_double_back():
    """途经点固定插到索引 2 会画出折返线。改成插到最近线段之后，折线保持单向。

    途经点取路线后段（星海一侧），这是旧实现出错最明显的位置。
    """
    late_waypoint = "121.5735,38.8823"

    with patch.dict("os.environ", {}, clear=True):
        route = get_candidate_routes(
            landmark("dut"), landmark("xinghai"), "+15", waypoint=late_waypoint
        )[0]

    points = route["polyline"].split(";")
    assert late_waypoint in points
    # 途经点应该出现在折线后半段，而不是被硬塞到第 2 个位置
    assert points.index(late_waypoint) > len(points) // 2


def test_fallback_waypoint_on_existing_vertex_is_not_duplicated():
    """途经点正好落在折线顶点上时不能产生零长度线段。"""
    vertex = DALIAN_SCENARIOS[scenario_key("dut", "xinghai")]["polyline"][3]

    with patch.dict("os.environ", {}, clear=True):
        route = get_candidate_routes(
            landmark("dut"), landmark("xinghai"), "+15", waypoint=vertex
        )[0]

    points = route["polyline"].split(";")
    assert all(points[i] != points[i + 1] for i in range(len(points) - 1))


@pytest.mark.parametrize("mode", ["+5", "+15", "roam"])
@pytest.mark.parametrize("pair", DEMO_PAIRS)
def test_offline_demo_nine_combinations(client, monkeypatch, pair, mode):
    """断网演示 9 组（三场景 × 三模式）必须全部命中兜底表。

    过去这条是手工跑的。第三轮改了 roam 上限和沿途亮点数量，
    两者都会影响这 9 组的结果 —— 手工清单靠不住，钉成测试。
    """
    monkeypatch.delenv("AMAP_KEY", raising=False)
    origin_key, destination_key = pair

    response = client.post(
        "/api/route/recommend",
        json={
            "origin": landmark(origin_key),
            "destination": landmark(destination_key),
            "mode": mode,
        },
    )

    assert response.status_code == 200, f"{origin_key}->{destination_key} @{mode}"
    body = response.json()

    assert body["route"]["demo_mode"] is True, "断网时必须走兜底表，不能是空路线"
    assert body["route"]["polyline"], "兜底路线必须有 polyline，否则地图是空的"
    assert body["pois"], "演示场景必须给出沿途亮点"
    assert body["narrative"], "演示场景必须有文案"
    assert body["score"] > 0
    assert body["detour_minutes"] <= MAX_DETOUR_MINUTES[mode], "兜底数据不能超出模式预算"


def test_frontend_constants_match_backend_landmarks():
    """`webapp/src/constants.js` 的演示坐标必须和 `dalian.py` 的 `LANDMARKS` 一致。

    这两处对不上时，前端按钮发出的坐标就落不进兜底表的 key，断网演示会静默退化成
    非演示模式 —— 页面还是有东西，只是不再是准备好的那条路线，台上很难当场发现。
    交接文档一直把这条列为硬约束，但过去只有人工核对。
    """
    import pathlib

    constants = pathlib.Path(__file__).resolve().parents[2] / "webapp" / "src" / "constants.js"
    if not constants.exists():  # 只跑后端的环境里不因为缺前端而失败
        pytest.skip("webapp/src/constants.js 不在这个 checkout 里")

    source = constants.read_text(encoding="utf-8")
    missing = [
        (slug, name, landmark(slug))
        for slug, (name, _lng, _lat) in LANDMARKS.items()
        if f"'{landmark(slug)}'" not in source
    ]
    assert not missing, f"前端演示坐标与后端 LANDMARKS 不一致: {missing}"
