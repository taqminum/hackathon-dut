from unittest.mock import patch
import requests
from app.services.poi_explorer import explore_pois_along_route, explore_pois_with_source


def test_explore_pois_along_route_filters_by_type():
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "pois": [
                {"type": "餐饮", "name": "A", "distance": "50", "rating": 4.5},
                {"type": "景点", "name": "B", "distance": "200", "rating": 4.0},
            ]
        }

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route("116.397428,39.90923", "116.407526,39.90403", ["餐饮"], 300)
            assert len(pois) == 1
            assert pois[0]["name"] == "A"
            mock_get.assert_called_once()


def test_explore_pois_along_route_returns_no_fake_pois_when_no_match():
    pois = explore_pois_along_route("116.397428,39.90923", "116.407526,39.90403", ["影院"], 300)

    assert pois == []


def test_explore_pois_along_route_discards_malformed_remote_pois():
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "pois": [
                None,
                "malformed",
                {"name": "缺少类型", "location": "120.1,30.2"},
                {"name": "有效亮点", "type": "景点", "location": "120.1,30.2"},
            ]
        }

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route("116.397428,39.90923", "116.407526,39.90403", ["景点"], 300)

    assert pois == [
        {
            "name": "有效亮点",
            "type": "景点",
            "distance": None,
            "rating": 0,
            "location": "120.1,30.2",
            "coordinate_system": "gcj02",
        }
    ]


def test_explore_pois_with_source_marks_real_pois_as_not_demo():
    with (
        patch.dict("os.environ", {"AMAP_KEY": "fake-key"}),
        patch("app.services.poi_explorer.requests.get") as mock_get,
    ):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "pois": [{"name": "真实亮点", "type": "景点", "location": "121.6002,38.9218"}]
        }

        pois, used_demo = explore_pois_with_source(
            "121.6068,38.9180",
            "121.5854,38.9325",
            ["景点"],
            300,
        )

    assert used_demo is False
    assert pois[0]["name"] == "真实亮点"


def test_explore_pois_with_source_flags_demo_fallback():
    with (
        patch.dict("os.environ", {"AMAP_KEY": "fake-key"}),
        patch(
            "app.services.poi_explorer.requests.get",
            side_effect=requests.RequestException("boom"),
        ),
    ):
        pois, used_demo = explore_pois_with_source(
            "121.6068,38.9180",
            "121.5854,38.9325",
            ["餐饮"],
            300,
        )

    assert used_demo is True
    assert [poi["name"] for poi in pois] == ["理工咖啡小铺"]
