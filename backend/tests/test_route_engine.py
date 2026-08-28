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


def test_get_candidate_routes_fallback_waypoint_keeps_demo_extra_budget():
    # 坐标从 dalian.landmark 取，不写字面量：兜底表改坐标时用例跟着走，
    # 不会再出现「表改了、用例还钉在旧坐标上」。
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
    assert waypoint in routes[0]["polyline"]
    assert routes[0]["distance"] == scenario["base_distance"] + scenario["extra_distance"]["+15"]
    assert routes[0]["duration"] == scenario["base_duration"] + scenario["extra_duration"]["+15"]


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
