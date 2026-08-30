"""真实高德全链路验收。

默认测试套件不会消耗高德配额。显式设置 ``RUN_LIVE_AMAP=1`` 和真实
``AMAP_KEY`` 后，本文件不使用 monkeypatch、requests mock 或内置演示数据，
直接穿过 FastAPI 接口、地点联想、POI 搜索和多段步行规划。
"""

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_AMAP") != "1" or not os.getenv("AMAP_KEY"),
    reason="需要 RUN_LIVE_AMAP=1 和真实 AMAP_KEY",
)


def test_live_amap_suggests_places_nationwide(client):
    response = client.get("/api/place/suggest", params={"keyword": "天安门"})

    assert response.status_code == 200, response.text
    suggestions = response.json()["suggestions"]
    assert suggestions
    assert any("天安门" in item["name"] for item in suggestions)
    assert all(item["location"] and "," in item["location"] for item in suggestions)


def test_live_amap_builds_a_route_through_two_verified_places(client):
    response = client.post(
        "/api/route/recommend",
        json={
            # 大连理工大学西门 -> 星海广场，均为 WGS-84；不依赖地名解析兜底。
            "origin": "121.5197,38.8856",
            "destination": "121.5839,38.8816",
            "mode": "roam",
            "poi_count": 2,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data_source"] == "amap"
    assert body["route"]["source"] == "amap"
    assert body["route"]["waypoint_count"] == 2
    assert body["poi_count"] == 2
    assert len(body["pois"]) == 2
    assert body["route"]["distance"] > 0
    assert body["route"]["duration"] > 0
    assert body["route"]["polyline"]
    assert [poi["visit_order"] for poi in body["pois"]] == [1, 2]
    assert all(poi["source"] == "amap" for poi in body["pois"])
    assert all(poi["id"] and poi["name"] and poi["reason"] for poi in body["pois"])
    # 每个高德入口坐标都被当作分段终点，拼接后只允许路网吸附造成的小偏差。
    assert all(poi["off_route_meters"] is not None for poi in body["pois"])
    assert all(poi["off_route_meters"] < 120 for poi in body["pois"])
