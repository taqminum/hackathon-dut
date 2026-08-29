from unittest.mock import patch
from app.services.route_engine import get_candidate_routes


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


def test_get_candidate_routes_marks_amap_coordinates_as_gcj02():
    with (
        patch.dict("os.environ", {"AMAP_KEY": "fake-key"}),
        patch("app.services.route_engine.requests.get") as mock_get,
    ):
        mock_get.return_value.json.return_value = {
            "route": {
                "paths": [
                    {
                        "distance": "1000",
                        "duration": "600",
                        "polyline": "121.6068,38.9180;121.5854,38.9325",
                    }
                ]
            }
        }

        routes = get_candidate_routes("121.6068,38.9180", "121.5854,38.9325", "+15")

    assert routes[0]["coordinate_system"] == "gcj02"
    assert routes[0]["demo_mode"] is False


def test_get_candidate_routes_builds_polyline_from_amap_steps():
    with (
        patch.dict("os.environ", {"AMAP_KEY": "fake-key"}),
        patch("app.services.route_engine.requests.get") as mock_get,
    ):
        mock_get.return_value.json.return_value = {
            "route": {
                "paths": [
                    {
                        "distance": "1000",
                        "duration": "600",
                        "steps": [
                            {"polyline": "121.6068,38.9180;121.6000,38.9200"},
                            {"polyline": "121.6000,38.9200;121.5854,38.9325"},
                        ],
                    }
                ]
            }
        }

        routes = get_candidate_routes("121.6068,38.9180", "121.5854,38.9325", "+15")

    assert routes[0]["polyline"] == "121.6068,38.9180;121.6000,38.9200;121.5854,38.9325"


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
    assert route["coordinate_system"] == "wgs84"
    assert route["distance"] > 1200
    assert route["duration"] > 900
    assert route["polyline"].startswith("116.3974,39.9092;")


def test_get_candidate_routes_fallback_waypoint_keeps_demo_extra_budget():
    with patch.dict("os.environ", {}, clear=True):
        routes = get_candidate_routes(
            "121.6068,38.9180",
            "121.5854,38.9325",
            "+15",
            waypoint="121.6002,38.9218",
        )

    assert isinstance(routes, list)
    assert len(routes) == 1
    assert "121.6002,38.9218" in routes[0]["polyline"]
    assert routes[0]["distance"] == 2620
    assert routes[0]["duration"] == 1560


def test_get_candidate_routes_reverses_demo_polyline_for_reverse_trip():
    with patch.dict("os.environ", {}, clear=True):
        route = get_candidate_routes(
            "121.6746,38.8784",
            "121.6753,38.9307",
            "+15",
        )[0]

    points = route["polyline"].split(";")
    assert points[0] == "121.6746,38.8784"
    assert points[-1] == "121.6753,38.9307"


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
