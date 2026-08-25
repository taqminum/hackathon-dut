from unittest.mock import patch
from app.services.poi_explorer import explore_pois_along_route


def test_explore_pois_along_route_filters_by_type():
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "pois": [
                {"type": "餐饮", "name": "A", "distance": "50", "rating": 4.5},
                {"type": "景点", "name": "B", "distance": "200", "rating": 4.0},
            ]
        }
        pois = explore_pois_along_route("116.397428,39.90923", "116.407526,39.90403", ["餐饮"], 300)
        assert len(pois) == 1
        assert pois[0]["name"] == "A"
