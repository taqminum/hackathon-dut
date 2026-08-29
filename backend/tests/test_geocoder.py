import requests_mock
import pytest

from app.services.geocoder import resolve_location, search_places


@pytest.mark.parametrize(
    "location",
    ["181,38", "121,91", "nan,30", "121,inf"],
)
def test_resolve_location_rejects_invalid_coordinates(location):
    with requests_mock.Mocker() as mocker:
        with pytest.raises(ValueError, match="invalid coordinates"):
            resolve_location(location)

        assert mocker.request_history == []


def test_resolve_location_normalizes_valid_coordinates():
    assert resolve_location(" 121.6, 38.9 ") == "121.6000,38.9000"


def test_search_places_prefers_specific_scenic_poi_over_generic_place_name(monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")
    with requests_mock.Mocker() as mocker:
        mocker.get(
            "https://restapi.amap.com/v3/place/text",
            json={
                "status": "1",
                "pois": [
                    {
                        "name": "东港",
                        "address": "中山区",
                        "location": "121.6000,38.9000",
                        "type": "地名地址信息;热点地名;热点地名",
                    },
                    {
                        "name": "东港音乐喷泉广场",
                        "address": "五五路9号",
                        "location": "121.675287,38.930747",
                        "type": "风景名胜;公园广场;城市广场",
                    },
                ],
            },
        )

        places = search_places("东港", city="大连", limit=6, preferred_types=["景点"])

    assert places[0]["name"] == "东港音乐喷泉广场"
    assert places[0]["location"] == "121.6753,38.9307"
    assert places[0]["confidence"] > places[1]["confidence"]


def test_resolve_location_raises_ambiguity_with_ranked_candidates(monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")
    with requests_mock.Mocker() as mocker:
        mocker.get(
            "https://restapi.amap.com/v3/place/text",
            json={
                "status": "1",
                "pois": [
                    {
                        "name": "人民广场",
                        "address": "大连市西岗区",
                        "location": "121.6200,38.9200",
                        "type": "风景名胜;公园广场;城市广场",
                    },
                    {
                        "name": "人民广场地铁站",
                        "address": "大连市西岗区",
                        "location": "121.6210,38.9210",
                        "type": "交通设施服务;地铁站;地铁站",
                    },
                ],
            },
        )

        with pytest.raises(Exception) as exc_info:
            resolve_location("人民广场")

    assert exc_info.value.candidates[0]["name"] == "人民广场"


def test_resolve_location_accepts_high_confidence_preferred_place(monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")
    with requests_mock.Mocker() as mocker:
        mocker.get(
            "https://restapi.amap.com/v3/place/text",
            json={
                "status": "1",
                "pois": [
                    {
                        "name": "东港",
                        "address": "中山区",
                        "location": "121.6000,38.9000",
                        "type": "地名地址信息;热点地名;热点地名",
                    },
                    {
                        "name": "东港音乐喷泉广场",
                        "address": "五五路9号",
                        "location": "121.675287,38.930747",
                        "type": "风景名胜;公园广场;城市广场",
                    },
                ],
            },
        )

        resolved = resolve_location("东港", preferred_types=["景点"])

    assert resolved == "121.6753,38.9307"
