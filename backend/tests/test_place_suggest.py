"""地点联想接口，转发高德 /v3/assistant/inputtips。

前端 suggestPlaces 已经在调这个接口（此前 404 静默降级）。
降级路径必须保留：没有 Key 或高德出错时返回空列表，不能抛 500 ——
输入框退化成纯文本输入是可接受的，弹错误提示不是。
"""

import requests
import requests_mock

INPUTTIPS_URL = "https://restapi.amap.com/v3/assistant/inputtips"


def test_suggest_reports_unavailable_without_amap_key(client):
    # conftest 的 autouse fixture 已清掉 AMAP_KEY
    response = client.get("/api/place/suggest", params={"keyword": "星海"})

    assert response.status_code == 503
    assert "未配置" in response.json()["detail"]


def test_suggest_normalizes_tips_to_wgs84(client, monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        mocker.get(
            INPUTTIPS_URL,
            json={
                "status": "1",
                "tips": [
                    {
                        "name": "星海广场",
                        "district": "辽宁省大连市沙河口区",
                        "address": "中山路",
                        "location": "121.588870,38.882379",
                    }
                ],
            },
        )
        response = client.get("/api/place/suggest", params={"keyword": "星海"})

    assert response.status_code == 200
    suggestion = response.json()["suggestions"][0]
    assert suggestion["name"] == "星海广场"
    assert suggestion["address"] == "中山路"
    # 高德给的是 GCJ-02，对外必须转成 WGS-84（差约 450 米）
    lng, lat = (float(part) for part in suggestion["location"].split(","))
    assert abs(lng - 121.583926) < 0.001
    assert abs(lat - 38.881623) < 0.001


def test_suggest_sends_keyword_and_city_to_amap(client, monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        mocker.get(INPUTTIPS_URL, json={"status": "1", "tips": []})
        client.get("/api/place/suggest", params={"keyword": " 星海 ", "city": "大连"})

    query = mocker.request_history[0].qs
    assert query["keywords"] == ["星海"]
    assert query["city"] == ["大连"]
    assert query["citylimit"] == ["true"]


def test_suggest_filters_tips_without_coordinates(client, monkeypatch):
    """行政区条目的 location / district 是空数组，不能作为可规划地点返回。"""
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        mocker.get(
            INPUTTIPS_URL,
            json={
                "status": "1",
                "tips": [
                    {"name": "沙河口区", "district": [], "address": [], "location": []},
                    None,
                    "malformed",
                    {"name": "", "location": "121.5,38.8"},
                    {"name": "有坐标的点", "location": "121.588870,38.882379"},
                ],
            },
        )
        response = client.get("/api/place/suggest", params={"keyword": "沙河口"})

    suggestions = response.json()["suggestions"]
    assert [item["name"] for item in suggestions] == ["有坐标的点"]
    assert suggestions[0]["location"] != ""


def test_suggest_reports_amap_failure(client, monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        mocker.get(INPUTTIPS_URL, exc=requests.exceptions.ConnectTimeout)
        response = client.get("/api/place/suggest", params={"keyword": "星海"})

    assert response.status_code == 502
    assert "高德地点联想失败" in response.json()["detail"]


def test_suggest_reports_malformed_payload(client, monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        mocker.get(INPUTTIPS_URL, text="not json at all")
        response = client.get("/api/place/suggest", params={"keyword": "星海"})

    assert response.status_code == 502
    assert "高德地点联想失败" in response.json()["detail"]


def test_suggest_rejects_empty_keyword(client):
    response = client.get("/api/place/suggest", params={"keyword": ""})

    assert response.status_code == 422
