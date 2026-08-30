import re
from unittest.mock import patch

from app.services.dalian import landmark
from app.services.route_engine import DALIAN_SCENARIOS, get_candidate_routes
from app.services.dalian import scenario_key


def test_get_candidate_routes_returns_list():
    with (
        patch.dict("os.environ", {"AMAP_KEY": "fake-key"}),
        patch("app.services.route_engine.requests.get") as mock_get,
    ):
        mock_get.return_value.json.return_value = {
            "route": {"paths": [{"distance": "1000", "duration": "600"}]}
        }
        routes = get_candidate_routes("116.397428,39.90923", "116.407526,39.90403", "walk")
        assert isinstance(routes, list)
        assert len(routes) == 1
        assert routes[0]["distance"] == 1000
        assert routes[0]["duration"] == 600


def test_get_candidate_routes_ignores_incomplete_amap_paths():
    with (
        patch.dict("os.environ", {"AMAP_KEY": "fake-key"}),
        patch("app.services.route_engine.requests.get") as mock_get,
    ):
        mock_get.return_value.json.return_value = {
            "route": {"paths": [{"distance": "not-a-number", "duration": "600"}]}
        }

        routes = get_candidate_routes("116.397428,39.90923", "116.407526,39.90403", "walk")

    assert routes[0]["distance"] > 0
    assert routes[0]["duration"] > 0


def test_get_candidate_routes_uses_fallback_when_amap_missing():
    with patch.dict("os.environ", {}, clear=True):
        routes = get_candidate_routes("116.397428,39.90923", "116.407526,39.90403", "+15")

    assert isinstance(routes, list)
    assert len(routes) == 1
    route = routes[0]
    assert route["distance"] > 1200
    assert route["duration"] > 900
    assert route["polyline"].startswith("116.3974,39.9092;")


def test_get_candidate_routes_fallback_waypoint_measures_distance_from_geometry():
    """R4：这两行原来断言的是

        distance == base_distance + extra_distance["+15"]
        duration == base_duration + extra_duration["+15"]

    **原断言锁定了数字与几何脱钩的缺陷**：查表加常数意味着报出的距离与画出的折线
    无关。实测三个模式的 polyline sha1 完全相同（`02149d9a7214`），而报出的距离
    差了 240 / 520 / 780 米 —— 断言全绿，用户在屏幕上看到的却是「三个模式一样」。

    现在改成断言距离是从折线量出来的。这条断言破坏时的表现是明确的：
    只要有人再把常数加回去，量出来的长度和报出的距离就对不上。
    """
    scenario = DALIAN_SCENARIOS[scenario_key("dut", "xinghai")]
    waypoint = "121.5548,38.8883"

    with patch.dict("os.environ", {}, clear=True):
        routes = get_candidate_routes(
            landmark("dut"),
            landmark("xinghai"),
            "+15",
            waypoint=waypoint,
        )

    assert isinstance(routes, list)
    assert len(routes) == 1
    route = routes[0]
    assert waypoint in route["polyline"]

    from app.services.route_engine import _parse_polyline, _polyline_length

    base_geometry = _polyline_length(scenario["polyline"])
    factor = scenario["base_distance"] / base_geometry
    speed = scenario["base_distance"] / scenario["base_duration"]
    geometry = _polyline_length(_parse_polyline(route["polyline"]))

    assert route["distance"] == round(geometry * factor)
    assert route["duration"] == round(route["distance"] / speed)
    # 标定值仍然成立：不经过 POI 时就该回到实测的 6920 米 / 5536 秒。
    with patch.dict("os.environ", {}, clear=True):
        plain = get_candidate_routes(landmark("dut"), landmark("xinghai"), "+15")[0]
    assert plain["distance"] == scenario["base_distance"]
    assert plain["duration"] == scenario["base_duration"]


def test_get_candidate_routes_reverses_demo_polyline_for_reverse_trip():
    with patch.dict("os.environ", {}, clear=True):
        route = get_candidate_routes(
            landmark("xinghai"),
            landmark("dut"),
            "+15",
        )[0]

    points = route["polyline"].split(";")
    assert points[0] == landmark("xinghai")
    assert points[-1] == landmark("dut")


def test_get_candidate_routes_fallback_waypoint_works_without_demo_scenario():
    with patch.dict("os.environ", {}, clear=True):
        routes = get_candidate_routes(
            "120.1300,30.2590",
            "120.1400,30.2550",
            "+15",
            waypoint="120.1350,30.2570",
        )

    assert isinstance(routes, list)
    assert len(routes) == 1
    assert "120.1350,30.2570" in routes[0]["polyline"]
    assert routes[0]["distance"] > 0
    assert routes[0]["duration"] > 0


def test_get_candidate_routes_rejects_implausibly_long_fallback_walk():
    with patch.dict("os.environ", {}, clear=True):
        try:
            get_candidate_routes(
                "121.4737,31.2304",
                "116.4074,39.9042",
                "+5",
            )
        except ValueError as exc:
            assert "too long" in str(exc)
        else:
            raise AssertionError("expected an overlong fallback route to be rejected")


def test_missing_coordinate_raises_instead_of_falling_back_to_beijing():
    """P2-7：坐标缺失过去会静默返回天安门坐标，用户拿到一条**北京的**路线。

    大连的项目给出北京的路线，是那种「界面看起来正常、结论完全错」的故障 ——
    必须抛异常让 api.py 转成 404。
    """
    from app.services.route_engine import _parse_lng_lat

    for empty in (None, "", "   "):
        try:
            _parse_lng_lat(empty)
        except ValueError:
            pass
        else:
            raise AssertionError(f"空坐标 {empty!r} 应当抛 ValueError，而不是返回默认坐标")


def test_no_beijing_coordinate_is_returned_as_a_default():
    """天安门坐标不该作为默认值出现在**可执行代码**里。

    防的是「以后有人把这个静默默认值加回来」。只扫代码行，不扫注释和文档字符串 ——
    解释这个坑的注释本身要提到那串坐标，那是有用的，不该为了让检查通过而删掉。
    """
    import ast
    import pathlib

    from app.services import route_engine

    # 从模块自身取路径，不要写相对路径 —— 相对 cwd 的话，
    # `pytest backend`（在仓库根跑）和 `cd backend && pytest` 两种调用方式结果会不一样。
    source = pathlib.Path(route_engine.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 按节点身份排除文档字符串：get_docstring 返回的是去缩进后的文本，
    # 跟原始 Constant 的值对不上，只能靠 id 认。
    docstring_nodes = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None) or []
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            docstring_nodes.add(id(body[0].value))

    offenders = [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and id(node) not in docstring_nodes
        and "116.407526" in str(node.value)
    ]
    assert not offenders, f"天安门默认坐标又出现在代码里: {offenders}"


def test_amap_branch_returns_same_shape_as_fallback():
    """P2-5：两条路径必须同形。

    前端靠 `route.demo_mode` 决定是否显示「内置演示数据」提示、靠 `route.origin`
    做起终点回退。高德分支过去缺这三个字段，undefined 恰好为假所以不报错 ——
    属于隐性依赖，任何一处改成 `'demo_mode' in route` 就会翻车。
    """
    amap_response = {
        "route": {
            "paths": [
                {
                    "distance": "1200",
                    "duration": "900",
                    "polyline": "121.5197,38.8856;121.5839,38.8816",
                    "steps": [],
                }
            ]
        }
    }

    with patch.dict("os.environ", {"AMAP_KEY": "test-key"}, clear=True):
        import requests_mock

        with requests_mock.Mocker() as mocker:
            mocker.get(
                "https://restapi.amap.com/v3/direction/walking", json=amap_response
            )
            amap_route = get_candidate_routes(landmark("dut"), landmark("xinghai"), "+5")[0]

    with patch.dict("os.environ", {}, clear=True):
        fallback_route = get_candidate_routes(landmark("dut"), landmark("xinghai"), "+5")[0]

    assert set(fallback_route) <= set(amap_route), (
        f"高德分支缺字段: {set(fallback_route) - set(amap_route)}"
    )
    assert amap_route["origin"] == landmark("dut")
    assert amap_route["destination"] == landmark("xinghai")
    # 真实高德数据永远不是演示数据
    assert amap_route["demo_mode"] is False
    assert fallback_route["demo_mode"] is True


def test_point_to_route_meters_measures_distance_to_the_polyline():
    from app.services.route_engine import point_to_route_meters

    polyline = "121.5197,38.8856;121.5839,38.8816"

    # 折线上的点距离约为 0
    assert point_to_route_meters("121.5197,38.8856", polyline) < 1
    # 明显偏离的点应当报出可观的距离
    assert point_to_route_meters("121.5500,38.9200", polyline) > 3000


def test_point_to_route_meters_returns_none_for_unusable_input():
    """算不出距离时返回 None，不要伪造 0（会把远处的店说成顺路）或 inf。"""
    from app.services.route_engine import point_to_route_meters

    assert point_to_route_meters(None, "121.5197,38.8856;121.5839,38.8816") is None
    assert point_to_route_meters("bad", "121.5197,38.8856;121.5839,38.8816") is None
    # 单点折线构不成线段
    assert point_to_route_meters("121.5197,38.8856", "121.5197,38.8856") is None
    assert point_to_route_meters("121.5197,38.8856", "") is None


# --- T6：兜底路线的分段指引 ------------------------------------------------
# 改之前这里是硬编码的单元素 steps，`road` 塞的是起点坐标，界面上印成
#   01  按推荐路线行走 / 121.5197,38.8856 / 7.4 公里 / 1 小时 37 分钟
# 一整条路只有一步（RouteSteps 的折叠交互因此永远不出现），路名位置是经纬度。

COORD_PATTERN = re.compile(r"-?\d+\.\d+\s*,\s*-?\d+\.\d+")


def _fallback(origin_key: str = "dut", destination_key: str = "xinghai", mode: str = "+15"):
    """进程内取兜底路线。不打 HTTP —— TestClient 会真的调付费高德接口。"""
    with patch.dict("os.environ", {}, clear=True):
        return get_candidate_routes(landmark(origin_key), landmark(destination_key), mode)[0]


def test_fallback_route_is_split_into_multiple_steps():
    route = _fallback()

    # 演示场景的折线有 7 个点，分段后必须多于 1 段，而且要多于前端的
    # collapsedCount（RouteSteps.vue 的默认值 4），折叠按钮才会真的出现
    assert len(route["steps"]) > 1
    assert len(route["steps"]) > 4, f"只有 {len(route['steps'])} 段，前端折叠按钮不会出现"


def test_fallback_steps_never_put_coordinates_in_the_road_field():
    """`road` 是给人看的路名。兜底数据没有真实路名，留空即可 ——
    前端 RouteSteps.vue 的 `v-if="step.road"` 会把这一行隐掉。"""
    for mode in ("+5", "+15", "roam"):
        route = _fallback(mode=mode)
        for step in route["steps"]:
            assert not COORD_PATTERN.search(step["road"]), f"road 里出现坐标: {step['road']!r}"
            # instruction 同样不该印坐标 —— 那是给用户读的一句话
            assert not COORD_PATTERN.search(step["instruction"]), step["instruction"]


def test_fallback_step_distances_and_durations_sum_to_the_route_totals():
    """逐段按比例取整会累积误差，各段加起来对不上整条路的数字。
    界面上「全程 7.4 公里」和指引里六段之和必须是同一个数。"""
    for origin_key, destination_key, mode in (
        ("dut", "xinghai", "+15"),
        ("xinghai", "dut", "roam"),
        ("donggang", "laohutan", "+5"),
    ):
        route = _fallback(origin_key, destination_key, mode)
        distance_sum = sum(int(step["distance"]) for step in route["steps"])
        duration_sum = sum(int(step["duration"]) for step in route["steps"])
        assert distance_sum == route["distance"], f"{origin_key}->{destination_key} 距离对不上"
        assert duration_sum == route["duration"], f"{origin_key}->{destination_key} 时长对不上"
        # 每一段都必须是正数，0 米的段在界面上是一行废话
        assert all(int(step["distance"]) > 0 for step in route["steps"])


def test_fallback_step_directions_follow_the_polyline():
    """方向词必须来自折线的真实走向。反向走同一条路，方向词要整体翻转 ——
    如果方向是写死的或者算错了，正反两趟会给出同一串词。"""
    forward = [step["instruction"] for step in _fallback("dut", "xinghai")["steps"]]
    backward = [step["instruction"] for step in _fallback("xinghai", "dut")["steps"]]

    assert all("向东" in text for text in forward), forward
    assert all("向西" in text for text in backward), backward
    # 首尾措辞要能读出这是一条路的开头和结尾
    assert forward[0].startswith("从起点")
    assert forward[-1].endswith("到达终点")


def test_fallback_steps_survive_a_degenerate_polyline():
    """折线退化成单点时不能返回空 steps（界面整块消失），
    也不能回头去塞坐标。总量照旧对得上。"""
    from app.services.route_engine import _fallback_steps

    steps = _fallback_steps("121.5197,38.8856", 500, 400)

    assert len(steps) == 1
    assert steps[0]["road"] == ""
    assert not COORD_PATTERN.search(steps[0]["instruction"])
    assert int(steps[0]["distance"]) == 500
    assert int(steps[0]["duration"]) == 400


def test_bearing_accounts_for_latitude_convergence():
    """方位角必须是球面公式，不能把经度差当平面用。

    `y = sin(Δlng) * cos(lat2)` 里的 `cos(lat2)` 是经线在该纬度上的收敛因子。
    丢掉它，在大连这个纬度上偏差 5 度以上 —— 八向分桶大多数时候还能落在同一格，
    所以只断言方向词抓不住这个错。这里直接钉数值。
    """
    from app.services.route_engine import _bearing_degrees, _direction_word

    start = (121.50, 38.88)
    # 正东：两点同纬度，方位角就是 90（此时 cos 因子在分子分母上抵消）
    assert abs(_bearing_degrees(start, (121.60, 38.88)) - 90.0) < 0.1
    # 正北 / 正南同理不受影响
    assert abs(_bearing_degrees(start, (121.50, 38.98)) - 0.0) < 0.1
    assert abs(_bearing_degrees(start, (121.50, 38.78)) - 180.0) < 0.1

    # 斜向才看得出收敛因子。平面近似会算成 68.19 度（东北），球面是 62.79（东北）——
    # 数值差 5.4 度，且下面这一对恰好跨过方向词的分桶边界。
    assert abs(_bearing_degrees(start, (121.55, 38.90)) - 62.79) < 0.05
    assert _direction_word(start, (121.55, 38.90)) == "东北"
    # 22.5 度边界附近：球面 17.94（北），平面近似会给 22.62（东北）
    assert abs(_bearing_degrees(start, (121.55, 39.00)) - 17.94) < 0.05
    assert _direction_word(start, (121.55, 39.00)) == "北"
