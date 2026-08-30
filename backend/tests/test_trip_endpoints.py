"""收藏 / 反馈接口。

修的是 UI 上可见的「收藏失败」：前端 saveTrip 拿不到 200 就报错降级。
存储是进程内的，所以每个用例先清干净再断言。
"""

import pytest

from app.routes import api


@pytest.fixture(autouse=True)
def clear_storage():
    with api._storage_lock:
        api._saved_trips.clear()
        api._feedback_entries.clear()
        api._recommendations.clear()
    # 偏好由 conftest 的 isolate_preferences 统一清理（模块级单例，全局泄漏）。
    yield


def test_save_trip_returns_ok_and_id(client):
    response = client.post(
        "/api/trip/save",
        json={"route": {"distance": 1000}, "mode": "+5", "narrative": "文案"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["id"], int)


def test_save_trip_ids_are_distinct(client):
    first = client.post("/api/trip/save", json={"mode": "+5"}).json()["id"]
    second = client.post("/api/trip/save", json={"mode": "+15"}).json()["id"]

    assert first != second


def test_save_trip_accepts_empty_body(client):
    """前端可能只发一个空对象。收藏不该因为字段缺失而失败。"""
    response = client.post("/api/trip/save", json={})

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_list_trips_returns_most_recent_first(client):
    client.post("/api/trip/save", json={"mode": "+5"})
    client.post("/api/trip/save", json={"mode": "roam"})

    response = client.get("/api/trip/list")

    assert response.status_code == 200
    trips = response.json()["trips"]
    assert [item["trip"]["mode"] for item in trips] == ["roam", "+5"]


def test_list_trips_is_empty_before_any_save(client):
    response = client.get("/api/trip/list")

    assert response.status_code == 200
    assert response.json()["trips"] == []


def test_saved_trips_are_capped(client, monkeypatch):
    """长时间演示不能让收藏把内存吃掉。"""
    monkeypatch.setattr(api, "MAX_STORED_TRIPS", 3)

    for index in range(6):
        client.post("/api/trip/save", json={"index": index})

    trips = client.get("/api/trip/list").json()["trips"]
    assert len(trips) == 3
    # 保留的是最近的三条
    assert [item["trip"]["index"] for item in trips] == [5, 4, 3]


def test_submit_feedback_returns_ok(client):
    response = client.post(
        "/api/feedback",
        json={"trip_id": 1, "liked": True, "mode": "+15", "comment": "不错"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_submit_feedback_records_payload(client):
    client.post("/api/feedback", json={"trip_id": 7, "liked": False})

    with api._storage_lock:
        assert api._feedback_entries[-1]["feedback"]["trip_id"] == 7
        assert api._feedback_entries[-1]["feedback"]["liked"] is False


def test_feedback_entries_are_capped(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_STORED_FEEDBACK", 2)

    for index in range(5):
        client.post("/api/feedback", json={"index": index})

    with api._storage_lock:
        assert len(api._feedback_entries) == 2
        assert [entry["feedback"]["index"] for entry in api._feedback_entries] == [3, 4]
