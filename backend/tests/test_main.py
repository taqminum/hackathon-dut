import math
import re

import requests_mock

from app.services.dalian import landmark, scenario_key
from app.services.route_engine import DALIAN_SCENARIOS


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_registered_once(client):
    health_routes = [route for route in client.app.routes if route.path == "/health"]

    assert len(health_routes) == 1


def test_frontend_assets_are_served_by_backend(client):
    index_response = client.get("/")
    asset_path = re.search(r'src="([^"]+\.js)"', index_response.text).group(1)
    response = client.get(asset_path)

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_missing_frontend_asset_returns_404(client):
    response = client.get("/assets/not-found.js")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_unknown_api_route_is_not_replaced_with_frontend(client):
    # 用一个确定不存在的路径：接口名拼错时必须拿到 JSON 404，
    # 而不是 SPA 的 index.html（前端会把 HTML 拿去 JSON.parse，报错和真实原因无关）。
    response = client.get("/api/definitely/not/a/route")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_recommend_route_rejects_invalid_coordinate_range(client):
    response = client.post(
        "/api/route/recommend",
        json={"origin": "181,38", "destination": "121,39", "mode": "+5"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "\u672a\u627e\u5230\u53ef\u884c\u8def\u7ebf"}


def test_recommend_route_respects_exploration_budget(client, monkeypatch):
    poi = {
        "name": "\u6d4b\u8bd5\u4eae\u70b9",
        "type": "\u666f\u70b9",
        "rating": 5,
        "location": "120.1350,30.2570",
    }

    def fake_routes(origin, destination, mode, waypoint=None):
        return [{
            "origin": origin,
            "destination": destination,
            "distance": 1000,
            "duration": 601 if waypoint else 300,
            "steps": [],
            "polyline": f"{origin};{destination}",
        }]

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *args, **kwargs: [poi])

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "+5"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["detour_minutes"] == 0
    assert body["pois"] == []
    assert body["route"]["duration"] == 300


def test_recommend_route_leads_with_the_poi_the_route_goes_through(client, monkeypatch):
    """被选中的 POI 必须排在 pois[0]：它是路线真正经过的那个。

    其余亮点只有「确实贴着这条折线」才会跟在后面（这里第二个 POI 距折线约 40 米，
    所以应当出现）。远处的候选不该混进来 —— 见下一个用例。
    """
    pois = [
        {"name": "更近的亮点", "type": "景点", "rating": 5, "location": "120.1350,30.2570"},
        {"name": "较远的亮点", "type": "餐饮", "rating": 1, "location": "120.1360,30.2570"},
    ]

    def fake_routes(origin, destination, mode, waypoint=None):
        return [{
            "origin": origin,
            "destination": destination,
            "distance": 1000,
            "duration": 301 if waypoint == pois[0]["location"] else 800 if waypoint else 300,
            "steps": [],
            "polyline": f"{origin};{waypoint or destination};{destination}",
        }]

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *args, **kwargs: pois)

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "+15"},
    )

    assert response.status_code == 200
    body = response.json()
    # 选中的那个打头，绕行 301s 的候选胜出
    assert body["pois"][0] == pois[0]
    assert body["route"]["duration"] == 301


def test_recommend_route_excludes_pois_far_from_the_chosen_route(client, monkeypatch):
    """沿线搜到但离最终路线很远的 POI 不能说成「顺路会经过」。

    这是 P2-3 返回多个亮点时最容易注水的地方：POI 来自沿基准折线的采样，
    而最终路线是经由某个途经点的另一条折线，两者可以差几公里。
    """
    # 评分必须拉开：两个同分候选谁被选中是不确定的（线程池完成顺序 + max 破平），
    # 而**被选中**的那个 POI 无论多远都会出现在 pois[0]（路线就是经由它规划的）。
    # 这里要验的是「没被选中、且离路线很远」的候选不会被追加进来。
    chosen_poi = {"name": "顺路的店", "type": "景点", "rating": 4.8, "location": "120.1350,30.2570"}
    far_poi = {"name": "几公里外的店", "type": "餐饮", "rating": 3.6, "location": "120.1500,30.2900"}

    def fake_routes(origin, destination, mode, waypoint=None):
        return [{
            "origin": origin,
            "destination": destination,
            "distance": 1000,
            "duration": 301 if waypoint else 300,
            "steps": [],
            "polyline": f"{origin};{waypoint or destination};{destination}",
        }]

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr(
        "app.routes.api.explore_pois_along_route",
        lambda *args, **kwargs: [chosen_poi, far_poi],
    )

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "+15"},
    )

    names = [poi["name"] for poi in response.json()["pois"]]
    assert names == ["顺路的店"], f"3.9 公里外的店不该进沿途亮点: {names}"


def test_recommend_route_returns_multiple_highlights_in_demo_mode(client, monkeypatch):
    """断网演示时每组场景有 2 个兜底 POI，两个都该出现在「沿途亮点」里。

    这是 P2-3 的实际收益：原来写死 `[chosen["poi"]]`，第二个兜底 POI
    永远拿不出来，「沿途几个亮点」这句话在演示里是空的。
    """
    monkeypatch.delenv("AMAP_KEY", raising=False)

    response = client.post(
        "/api/route/recommend",
        json={"origin": landmark("dut"), "destination": landmark("xinghai"), "mode": "+15"},
    )

    assert response.status_code == 200
    pois = response.json()["pois"]
    assert len(pois) == 2, [poi["name"] for poi in pois]
    # 三组演示场景走手写文案（比模板自然，优先级更高），所以这里不断言复数模板。
    # 复数模板由 test_narrative.py 覆盖。
    assert response.json()["narrative"]


def test_recommend_route_ignores_malformed_pois_and_ratings(client, monkeypatch):
    poi = {"name": "异常评分亮点", "type": "景点", "rating": "nan", "location": "120.1350,30.2570"}

    def fake_routes(origin, destination, mode, waypoint=None):
        return [{
            "origin": origin,
            "destination": destination,
            "distance": 1000,
            "duration": 300 if not waypoint else 301,
            "steps": [],
            "polyline": f"{origin};{destination}",
        }]

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr(
        "app.routes.api.explore_pois_along_route",
        lambda *args, **kwargs: [None, "malformed", poi],
    )

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "+5"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pois"] == [poi]
    assert math.isfinite(body["score"])


def test_recommend_route_skips_pois_without_coordinate(client, monkeypatch):
    poi = {"name": "无坐标亮点", "type": "景点", "rating": 5}

    def fake_routes(origin, destination, mode, waypoint=None):
        return [{
            "origin": origin,
            "destination": destination,
            "distance": 1000,
            "duration": 300,
            "steps": [],
            "polyline": f"{origin};{destination}",
        }]

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *args, **kwargs: [poi])

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "+5"},
    )

    assert response.status_code == 200
    assert response.json()["pois"] == []


def test_recommend_route_skips_pois_with_invalid_coordinate(client, monkeypatch):
    poi = {
        "name": "异常坐标亮点",
        "type": "景点",
        "rating": 5,
        "location": "181,38",
    }

    def fake_routes(origin, destination, mode, waypoint=None):
        return [{
            "origin": origin,
            "destination": destination,
            "distance": 1000,
            "duration": 300,
            "steps": [],
            "polyline": f"{origin};{destination}",
        }]

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *args, **kwargs: [poi])

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "+5"},
    )

    assert response.status_code == 200
    assert response.json()["pois"] == []


def test_recommend_route_rejects_unknown_mode_without_geocoding(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.api.resolve_location",
        lambda value: (_ for _ in ()).throw(AssertionError("should not geocode")),
    )

    response = client.post(
        "/api/route/recommend",
        json={"origin": "A", "destination": "B", "mode": "unknown"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "不支持的探索模式"}


def test_recommend_route_rejects_same_resolved_endpoints(client, monkeypatch):
    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: "120.1300,30.2590")

    response = client.post(
        "/api/route/recommend",
        json={"origin": "起点", "destination": "终点", "mode": "+5"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "起点和终点不能相同"}


def test_recommend_route_returns_404_when_geocode_has_no_result(client):
    payload = {
        "origin": "\u65e0\u7ed3\u679c\u8d77\u70b9",
        "destination": "\u65e0\u7ed3\u679c\u7ec8\u70b9",
        "mode": "+5",
    }

    with requests_mock.Mocker() as mocker:
        mocker.get("https://nominatim.openstreetmap.org/search", json=[])
        response = client.post("/api/route/recommend", json=payload)

    assert response.status_code == 404
    assert response.json() == {"detail": "\u672a\u627e\u5230\u53ef\u884c\u8def\u7ebf"}


def test_recommend_route_returns_success_when_places_have_pois(client, monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")

    origin_geo = {"lat": "30.2590", "lon": "120.1300"}
    destination_geo = {"lat": "30.2550", "lon": "120.1400"}
    poi_geo = {"lat": "30.2570", "lon": "120.1350"}

    # 高德步行接口不支持 waypoint（传了被静默忽略），所以经由 POI 的路线是
    # `起点->POI` + `POI->终点` 两段拼接。下面的桩按 origin/destination 分派。
    ORIGIN_GCJ = "120.134759,30.256708"
    # POI 经 normalize_coordinate 取到 4 位小数再转回 GCJ-02，与原值差约 1 米。
    POI_GCJ = "120.134958,30.257008"
    DEST_GCJ = "120.144734,30.252694"

    def walking_response(distance, duration, points):
        return {
            "route": {
                "paths": [
                    {
                        "distance": str(distance),
                        "duration": str(duration),
                        "polyline": ";".join(points),
                        "steps": [
                            {
                                "instruction": "\u524d\u5f80\u7ec8\u70b9",
                                "road": points[0],
                                "distance": str(distance),
                                "duration": str(duration),
                            }
                        ],
                    }
                ]
            }
        }

    poi_response = {
        "pois": [
            {
                "name": "\u5076\u9047\u5c0f\u5e97",
                "type": "\u9910\u996e",
                "distance": "320",
                "rating": "4.6",
                "location": f"{poi_geo['lon']},{poi_geo['lat']}",
            }
        ]
    }

    def nominatim_callback(request, context):
        context.status_code = 200
        query = request.qs.get("q", [""])[0]

        if query == "\u8d77\u70b9":
            return [origin_geo]
        if query == "\u7ec8\u70b9":
            return [destination_geo]
        return []

    def walking_callback(request, context):
        context.status_code = 200
        origin = request.qs["origin"][0]
        destination = request.qs["destination"][0]

        # 第一段：起点 -> POI
        if origin == ORIGIN_GCJ and destination == POI_GCJ:
            return walking_response(1190, 860, ["120.1300,30.2590", "120.1350,30.2570"])
        # 第二段：POI -> 终点
        if origin == POI_GCJ and destination == DEST_GCJ:
            return walking_response(1190, 860, ["120.1350,30.2570", "120.1400,30.2550"])
        # 基准：起点 -> 终点
        return walking_response(
            2380, 1420, ["120.1300,30.2590", "120.1350,30.2570", "120.1400,30.2550"]
        )

    payload = {
        "origin": "\u8d77\u70b9",
        "destination": "\u7ec8\u70b9",
        "mode": "+5",
    }

    with requests_mock.Mocker() as mocker:
        # 有 AMAP_KEY 时 geocoder 先打高德地理编码（带 city 偏置做城市约束），
        # Nominatim 只是没 Key 时的兜底。高德返回 GCJ-02，转回 WGS-84 后正好是
        # origin_geo / destination_geo。
        def amap_geocode_callback(request, context):
            context.status_code = 200
            address = request.qs.get("address", [""])[0]

            if address == payload["origin"]:
                return {"status": "1", "geocodes": [{"location": ORIGIN_GCJ}]}
            if address == payload["destination"]:
                return {"status": "1", "geocodes": [{"location": DEST_GCJ}]}
            return {"status": "1", "geocodes": []}

        mocker.get(
            "https://nominatim.openstreetmap.org/search",
            json=nominatim_callback,
        )
        mocker.get(
            "https://restapi.amap.com/v3/geocode/geo",
            json=amap_geocode_callback,
        )
        mocker.get(
            "https://restapi.amap.com/v3/direction/walking",
            json=walking_callback,
        )
        mocker.get(
            "https://restapi.amap.com/v3/place/around",
            json=poi_response,
        )
        response = client.post("/api/route/recommend", json=payload)

    assert response.status_code == 200
    body = response.json()

    walking_requests = [
        request
        for request in mocker.request_history
        if request.path_url.startswith("/v3/direction/walking")
    ]
    # 入参是 WGS-84，发给高德的必须是 GCJ-02（差约 450 米，不转折线会整体偏离街道）。
    assert walking_requests[0].qs["origin"] == ["120.134759,30.256708"]
    assert walking_requests[0].qs["destination"] == ["120.144734,30.252694"]

    # 候选路线由两段拼接而成，不再有 waypoint 参数。
    assert all("waypoint" not in request.qs for request in walking_requests)
    leg_pairs = {
        (request.qs["origin"][0], request.qs["destination"][0]) for request in walking_requests
    }
    assert (ORIGIN_GCJ, POI_GCJ) in leg_pairs
    assert (POI_GCJ, DEST_GCJ) in leg_pairs

    # 反过来，高德返回的 GCJ-02 必须转回 WGS-84 再给前端。
    # rating 由高德的字符串解析成 float 后再返回给前端。
    assert body["pois"] == [
        {**poi_response["pois"][0], "location": "120.130242,30.259292", "rating": 4.6}
    ]
    assert body["route"]["polyline"].split(";")[0] == "120.125231,30.261286"
    assert body["baseline_minutes"] == 24
    # 两段合计 1720s vs 基准 1420s -> 绕行 5 分钟
    assert body["detour_minutes"] == 5
    assert body["route"]["distance"] == 2380
    assert body["route"]["duration"] == 1720
    # 拼接处重复的点要去掉
    assert len(body["route"]["polyline"].split(";")) == 3


def test_recommend_route_geocodes_place_names_without_fake_pois(client, monkeypatch):
    monkeypatch.delenv("AMAP_KEY", raising=False)

    locations = {
        "\u8d77\u70b9": {"lat": "30.2590", "lon": "120.1300"},
        "\u7ec8\u70b9": {"lat": "30.2550", "lon": "120.1400"},
    }

    def nominatim_callback(request, context):
        context.status_code = 200
        return [locations[request.qs["q"][0]]]

    with requests_mock.Mocker() as mocker:
        mocker.get(
            "https://nominatim.openstreetmap.org/search",
            json=nominatim_callback,
        )
        response = client.post(
            "/api/route/recommend",
            json={"origin": "\u8d77\u70b9", "destination": "\u7ec8\u70b9", "mode": "+5"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["route"]["origin"] == "120.1300,30.2590"
    assert body["route"]["destination"] == "120.1400,30.2550"
    assert body["pois"] == []


def test_recommend_route_keeps_builtin_demo_scenario(client, monkeypatch):
    monkeypatch.delenv("AMAP_KEY", raising=False)

    scenario = DALIAN_SCENARIOS[scenario_key("dut", "xinghai")]
    response = client.post(
        "/api/route/recommend",
        json={
            "origin": landmark("dut"),
            "destination": landmark("xinghai"),
            "mode": "+15",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"]["demo_mode"] is True
    assert body["pois"], "演示场景必须给出沿途亮点"
    assert body["baseline_minutes"] == round(scenario["base_duration"] / 60)
    assert body["detour_minutes"] == round(scenario["extra_duration"]["+15"] / 60)


def test_roam_mode_has_a_detour_ceiling(client, monkeypatch):
    """P2-4：roam 过去完全不过滤绕行。

    产品说的是「**可控的**意外」，一个无上限的模式跟这句话冲突 ——
    高德偶尔会给出绕行 40 分钟的候选，那已经是另一趟行程了。
    """
    from app.routes.api import MAX_DETOUR_MINUTES

    assert MAX_DETOUR_MINUTES["roam"] > MAX_DETOUR_MINUTES["+15"], "roam 应当比 +15 宽松"

    poi = {"name": "太远的店", "type": "景点", "rating": 5, "location": "120.1350,30.2570"}
    over_budget_seconds = MAX_DETOUR_MINUTES["roam"] * 60 + 60

    def fake_routes(origin, destination, mode, waypoint=None):
        return [{
            "origin": origin,
            "destination": destination,
            "distance": 1000,
            "duration": 300 + (over_budget_seconds if waypoint else 0),
            "steps": [],
            "polyline": f"{origin};{destination}",
        }]

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *args, **kwargs: [poi])

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "roam"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pois"] == [], "超出 roam 上限的候选不该被选中"
    assert body["detour_minutes"] == 0


def test_roam_still_accepts_a_detour_beyond_the_plus_15_budget(client, monkeypatch):
    """给 roam 设上限不能把它变成 +15：20 分钟的绕行仍然应该被接受。"""
    poi = {"name": "值得走一趟", "type": "景点", "rating": 5, "location": "120.1350,30.2570"}

    def fake_routes(origin, destination, mode, waypoint=None):
        return [{
            "origin": origin,
            "destination": destination,
            "distance": 1000,
            "duration": 300 + (20 * 60 if waypoint else 0),
            "steps": [],
            "polyline": f"{origin};{destination}",
        }]

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *args, **kwargs: [poi])

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "roam"},
    )

    body = response.json()
    assert body["pois"] == [poi]
    assert body["detour_minutes"] == 20


def test_recommend_returns_404_when_coordinate_is_missing(client, monkeypatch):
    """P2-7：坐标缺失必须是 404，而不是一条北京的路线。"""
    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)

    response = client.post(
        "/api/route/recommend",
        json={"origin": "121.5197,38.8856", "destination": "   ", "mode": "+5"},
    )

    assert response.status_code == 404
    body = response.text
    assert "116.4" not in body, "不能返回北京坐标"


def test_recommend_includes_trip_id_for_feedback_attribution(client, monkeypatch):
    """反馈要能归因到具体 POI 类型，recommend 必须发一个 trip_id 出去。

    前端 ResultView 已经在反馈时回传 result.trip_id，所以这个字段一加上，
    反馈闭环就不需要改前端 bundle。
    """
    monkeypatch.delenv("AMAP_KEY", raising=False)

    response = client.post(
        "/api/route/recommend",
        json={"origin": landmark("dut"), "destination": landmark("xinghai"), "mode": "+15"},
    )

    assert isinstance(response.json()["trip_id"], int)


def test_feedback_shifts_later_scoring(client, monkeypatch):
    """P2-2 的完整闭环：推荐 → 点「不喜欢」→ 下一次同样的候选得分更低。

    这是整个偏好系统唯一真正需要证明的事。单元测试证明了 scorer 会用 affinity，
    这个测试证明 affinity 真的从用户的一次点击里来。
    """
    from app.routes.api import preferences

    coffee = {"name": "某咖啡", "type": "餐饮服务;咖啡厅", "rating": 4.5, "location": "121.5250,38.8800"}

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr(
        "app.routes.api.get_candidate_routes",
        lambda origin, destination, mode, waypoint=None: [{
            "origin": origin,
            "destination": destination,
            "distance": 1200,
            "duration": 600 + (240 if waypoint else 0),
            "steps": [],
            "polyline": f"{origin};{destination}",
        }],
    )
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *a, **k: [coffee])

    payload = {"origin": "121.5197,38.8856", "destination": "121.5400,38.8700", "mode": "+15"}

    first = client.post("/api/route/recommend", json=payload).json()
    neutral_score = first["score"]
    trip_id = first["trip_id"]

    feedback = client.post("/api/feedback", json={"trip_id": trip_id, "liked": False})
    assert feedback.status_code == 200
    assert "咖啡" in feedback.json()["learned"], "反馈必须落到咖啡这个标签上"

    after_dislike = client.post("/api/route/recommend", json=payload).json()
    assert after_dislike["score"] < neutral_score, "说了不喜欢，同一个候选得分必须下降"

    preferences.reset()
    liked_trip = client.post("/api/route/recommend", json=payload).json()["trip_id"]
    client.post("/api/feedback", json={"trip_id": liked_trip, "liked": True})
    after_like = client.post("/api/route/recommend", json=payload).json()
    assert after_like["score"] > neutral_score, "说了喜欢，得分必须上升"


def test_preference_endpoint_exposes_learned_state(client):
    """GET /api/preference —— 演示时用来现场证明「它真的记住了」。"""
    response = client.get("/api/preference")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] in {"+5", "+15", "roam"}
    assert isinstance(body["tags"], dict)


def test_preference_endpoint_reflects_the_mode_actually_requested(client, monkeypatch):
    """`GET /api/preference` 是演示时的证据接口，模式必须跟着推荐走。

    过去 `_mode` 只有 `/api/feedback` 会写，所以连点三次 +15 之后
    这个接口还显示 +5 —— 台上拿它当证据会当场翻车。
    """
    monkeypatch.delenv("AMAP_KEY", raising=False)

    client.post(
        "/api/route/recommend",
        json={"origin": landmark("dut"), "destination": landmark("xinghai"), "mode": "+15"},
    )
    assert client.get("/api/preference").json()["mode"] == "+15"

    client.post(
        "/api/route/recommend",
        json={"origin": landmark("donggang"), "destination": landmark("laohutan"), "mode": "roam"},
    )
    assert client.get("/api/preference").json()["mode"] == "roam"


def test_rejected_mode_does_not_get_recorded(client):
    """422 的请求不该留下痕迹。"""
    before = client.get("/api/preference").json()["mode"]
    response = client.post(
        "/api/route/recommend",
        json={"origin": landmark("dut"), "destination": landmark("xinghai"), "mode": "+999"},
    )

    assert response.status_code == 422
    assert client.get("/api/preference").json()["mode"] == before
