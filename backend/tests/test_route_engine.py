from unittest.mock import patch
from app.services.route_engine import get_candidate_routes


def test_get_candidate_routes_returns_list():
    with patch("app.services.route_engine.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "route": {"paths": [{"distance": "1000", "duration": "600"}]}
        }
        routes = get_candidate_routes("116.397428,39.90923", "116.407526,39.90403", "walk")
        assert isinstance(routes, list)
        assert len(routes) == 1
