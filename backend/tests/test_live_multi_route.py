from app.services.poi_explorer import _sample_points
from app.services.route_engine import SOURCE_AMAP, get_route_via_waypoints


def _route(origin, destination, duration=300, waypoint=None):
    middle = f";{waypoint}" if waypoint else ""
    return {
        "source": SOURCE_AMAP,
        "origin": origin,
        "destination": destination,
        "demo_mode": False,
        "distance": duration,
        "duration": duration,
        "steps": [],
        "polyline": f"{origin}{middle};{destination}",
    }


def test_formal_recommendation_never_uses_offline_fallback(client, monkeypatch):
    monkeypatch.delenv("AMAP_KEY", raising=False)
    monkeypatch.delenv("ALLOW_OFFLINE_FALLBACK", raising=False)

    response = client.post(
        "/api/route/recommend",
        json={
            "origin": "121.5197,38.8856",
            "destination": "121.5839,38.8816",
            "mode": "+15",
            "poi_count": 2,
        },
    )

    assert response.status_code == 503
    assert "真实高德路线服务未就绪" in response.json()["detail"]


def test_two_requested_places_are_both_real_waypoints_and_ordered(client, monkeypatch):
    origin = "120.0000,30.0000"
    destination = "120.1000,30.0000"
    pois = [
        {
            "id": "late",
            "name": "后半程公园",
            "type": "风景名胜;公园广场;公园",
            "rating": 4.6,
            "location": "120.0750,30.0000",
            "navigation_location": "120.0750,30.0000",
            "address": "后半程",
            "source": "amap",
        },
        {
            "id": "early",
            "name": "前半程展馆",
            "type": "科教文化服务;展览馆;展览馆",
            "rating": 4.5,
            "location": "120.0250,30.0000",
            "navigation_location": "120.0250,30.0000",
            "address": "前半程",
            "source": "amap",
        },
        {
            "id": "middle",
            "name": "中段咖啡",
            "type": "餐饮服务;咖啡厅;咖啡厅",
            "rating": 3.6,
            "location": "120.0500,30.0000",
            "navigation_location": "120.0500,30.0000",
            "address": "中段",
            "source": "amap",
        },
    ]
    captured = []
    single_route_waypoints = []

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *a, **k: pois)

    def fake_candidates(start, end, mode, waypoint=None):
        single_route_waypoints.append(waypoint)
        return [_route(start, end, duration=330 if waypoint else 300, waypoint=waypoint)]

    def fake_multi(start, end, waypoints):
        captured.append(list(waypoints))
        route = _route(start, end, duration=420)
        route["waypoint_count"] = len(waypoints)
        route["polyline"] = ";".join([start, *waypoints, end])
        return route

    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_candidates)
    monkeypatch.setattr("app.routes.api.get_route_via_waypoints", fake_multi)

    response = client.post(
        "/api/route/recommend",
        json={
            "origin": origin,
            "destination": destination,
            "mode": "+15",
            "poi_count": 2,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data_source"] == "amap"
    assert body["poi_count"] == 2
    assert body["route"]["waypoint_count"] == 2
    assert [poi["visit_order"] for poi in body["pois"]] == [1, 2]
    assert all(poi["is_waypoint"] for poi in body["pois"])
    assert all(poi["source"] == "amap" for poi in body["pois"])
    assert captured
    assert captured[0] == sorted(captured[0], key=lambda value: float(value.split(",")[0]))
    # 多点组合不能先为每个 POI 再查两段路线；这里只允许基准路线这一笔。
    assert single_route_waypoints == [None]
    assert all(poi["reason"] for poi in body["pois"])


def test_live_corridor_sampling_adapts_to_route_length():
    polyline = "120.0000,30.0000;120.0700,30.0000"
    samples = _sample_points(
        "120.0000,30.0000",
        "120.0700,30.0000",
        polyline,
        radius=400,
        adaptive=True,
    )

    assert 3 < len(samples) <= 10
    longitudes = [float(point.split(",")[0]) for point in samples]
    assert longitudes == sorted(longitudes)
    assert longitudes[0] > 120.0
    assert longitudes[-1] < 120.07


def test_multi_waypoint_engine_concatenates_every_real_leg(monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")
    calls = []

    def fake_leg(start, end):
        calls.append((start, end))
        return {
            "source": SOURCE_AMAP,
            "distance": 100,
            "duration": 80,
            "steps": [{"instruction": f"{start}->{end}"}],
            "polyline": f"{start};{end}",
        }

    monkeypatch.setattr("app.services.route_engine._walk_leg", fake_leg)
    route = get_route_via_waypoints("A", "B", ["P1", "P2", "P3"])

    assert calls == [("A", "P1"), ("P1", "P2"), ("P2", "P3"), ("P3", "B")]
    assert route["source"] == SOURCE_AMAP
    assert route["waypoint_count"] == 3
    assert route["distance"] == 400
    assert route["duration"] == 320
    assert route["polyline"] == "A;P1;P2;P3;B"
