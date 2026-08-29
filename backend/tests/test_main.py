import math
import re

import requests_mock


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


def test_place_suggest_returns_ranked_real_candidates(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.api.search_places",
        lambda keyword, city="大连", limit=6, preferred_types=None: [
            {
                "name": "东港音乐喷泉广场",
                "address": "五五路9号",
                "location": "121.6753,38.9307",
                "type": "风景名胜;公园广场;城市广场",
                "coordinate_system": "gcj02",
                "confidence": 0.94,
            }
        ],
    )

    response = client.get("/api/place/suggest", params={"keyword": "东港"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "东港音乐喷泉广场"


def test_unknown_api_route_is_not_replaced_with_frontend(client):
    response = client.get("/api/not-real")

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

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value, **kwargs: value)
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


def test_recommend_route_only_returns_poi_for_selected_route(client, monkeypatch):
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

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value, **kwargs: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *args, **kwargs: pois)

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "+15"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pois"] == [pois[0]]
    assert body["route"]["duration"] == 301


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

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value, **kwargs: value)
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

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value, **kwargs: value)
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

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value, **kwargs: value)
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
    monkeypatch.setattr("app.routes.api.resolve_location", lambda value, **kwargs: "120.1300,30.2590")

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

    def walking_response(duration):
        return {
            "route": {
                "paths": [
                    {
                        "distance": "2380",
                        "duration": str(duration),
                        "polyline": ";".join(
                            [
                                "120.1300,30.2590",
                                "120.1350,30.2570",
                                "120.1400,30.2550",
                            ]
                        ),
                        "steps": [
                            {
                                "instruction": "\u524d\u5f80\u7ec8\u70b9",
                                "road": "120.1300,30.2590",
                                "distance": "2380",
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
        duration = 1720 if request.qs.get("waypoint") else 1420
        return walking_response(duration)

    payload = {
        "origin": "\u8d77\u70b9",
        "destination": "\u7ec8\u70b9",
        "mode": "+5",
    }

    with requests_mock.Mocker() as mocker:
        mocker.get(
            "https://nominatim.openstreetmap.org/search",
            json=nominatim_callback,
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
    assert walking_requests[0].qs["origin"] == ["120.1300,30.2590"]
    assert walking_requests[0].qs["destination"] == ["120.1400,30.2550"]

    assert body["pois"] == [{**poi_response["pois"][0], "coordinate_system": "gcj02"}]
    assert body["baseline_minutes"] == 24
    assert body["detour_minutes"] == 5
    assert body["route"]["distance"] == 2380
    assert body["route"]["duration"] == 1720


def test_recommend_route_prioritizes_scenic_pois_for_roam_mode(client, monkeypatch):
    captured = {}

    def capture_pois(*args, **kwargs):
        captured["types"] = args[2]
        return []

    monkeypatch.setattr("app.routes.api.explore_pois_along_route", capture_pois)
    response = client.post(
        "/api/route/recommend",
        json={
            "origin": "120.1300,30.2590",
            "destination": "120.1400,30.2550",
            "mode": "roam",
        },
    )

    assert response.status_code == 200
    assert captured["types"] == ["景点"]


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

    response = client.post(
        "/api/route/recommend",
        json={
            "origin": "121.6068,38.9180",
            "destination": "121.5854,38.9325",
            "mode": "+15",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"]["demo_mode"] is True
    assert len(body["pois"]) == 1
    assert body["baseline_minutes"] == 21
    assert body["detour_minutes"] == 5
