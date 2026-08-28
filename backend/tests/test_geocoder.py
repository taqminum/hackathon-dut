import requests_mock
import pytest

from app.services.geocoder import resolve_location


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


AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def test_resolve_location_uses_amap_with_city_bias_when_key_present(monkeypatch):
    """有 Key 就走高德，并且必须带 city —— 城市偏置是这次换实现的唯一理由。"""
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        mocker.get(
            AMAP_GEOCODE_URL,
            json={"status": "1", "geocodes": [{"location": "121.588870,38.882379"}]},
        )

        # 高德给的是 GCJ-02，对外必须转成 WGS-84（差约 450 米）。
        assert resolve_location("星海广场") == "121.5839,38.8816"

    request = mocker.request_history[0]
    assert request.path_url.startswith("/v3/geocode/geo")
    assert request.qs["city"] == ["大连"]
    assert request.qs["address"] == ["星海广场"]
    # 命中高德就不该再打 Nominatim
    assert all("nominatim" not in item.hostname for item in mocker.request_history)


def test_resolve_location_keeps_dalian_landmarks_inside_dalian(monkeypatch):
    """这就是换实现要防的事故：Nominatim 把老虎滩解析到新西兰、星海广场到西藏。

    一次跨国误判会让整条路线跑到几千公里外，比任何显示问题都严重。
    """
    monkeypatch.setenv("AMAP_KEY", "test-key")

    # 高德实测值（GCJ-02）
    AMAP_RESULTS = {
        "老虎滩海洋公园": "121.675131,38.879093",
        "星海广场": "121.588870,38.882379",
        "大连理工大学": "121.524803,38.886490",
    }

    def geocode_callback(request, context):
        context.status_code = 200
        address = request.qs.get("address", [""])[0]
        location = AMAP_RESULTS.get(address)
        if not location:
            return {"status": "1", "geocodes": []}
        return {"status": "1", "geocodes": [{"location": location}]}

    with requests_mock.Mocker() as mocker:
        mocker.get(AMAP_GEOCODE_URL, json=geocode_callback)

        for name in AMAP_RESULTS:
            lng, lat = map(float, resolve_location(name).split(","))
            assert 121.0 < lng < 122.5, (name, lng)
            assert 38.5 < lat < 39.5, (name, lat)


def test_resolve_location_falls_back_to_nominatim_when_amap_returns_nothing(monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        mocker.get(AMAP_GEOCODE_URL, json={"status": "1", "geocodes": []})
        mocker.get(NOMINATIM_URL, json=[{"lon": "121.5839", "lat": "38.8816"}])

        assert resolve_location("某个高德查不到的地方") == "121.5839,38.8816"

    assert any("nominatim" in item.hostname for item in mocker.request_history)


def test_resolve_location_falls_back_to_nominatim_when_amap_unreachable(monkeypatch):
    """高德连不上不能让整个接口失败 —— 兜底链必须走完。"""
    import requests

    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        mocker.get(AMAP_GEOCODE_URL, exc=requests.ConnectTimeout)
        mocker.get(NOMINATIM_URL, json=[{"lon": "121.5839", "lat": "38.8816"}])

        assert resolve_location("星海广场") == "121.5839,38.8816"


def test_nominatim_fallback_is_bounded_to_dalian(monkeypatch):
    """没有 Key 时也不能重现跨国误判：viewbox + bounded=1 必须带上。"""
    monkeypatch.delenv("AMAP_KEY", raising=False)

    with requests_mock.Mocker() as mocker:
        mocker.get(NOMINATIM_URL, json=[{"lon": "121.6701", "lat": "38.8783"}])

        assert resolve_location("老虎滩") == "121.6701,38.8783"

    request = mocker.request_history[0]
    assert request.qs["bounded"] == ["1"]
    assert request.qs["viewbox"] == ["120.9,39.6,123.0,38.4"]


AMAP_MALFORMED_GEOCODES = (
    {"status": "1", "geocodes": []},
    {"status": "1", "geocodes": "not-a-list"},
    {"status": "1", "geocodes": [None]},
    # 高德把「没有这个字段」表示成 []，float([]) 会抛 TypeError
    {"status": "1", "geocodes": [{"location": []}]},
    {"status": "1", "geocodes": [{}]},
    {"status": "1", "geocodes": [{"location": "not-a-coordinate"}]},
    {"status": "0", "info": "INVALID_USER_KEY"},
    "a bare string",
    [1, 2, 3],
    None,
)


@pytest.mark.parametrize("body", AMAP_MALFORMED_GEOCODES)
def test_amap_malformed_geocode_never_raises_unexpected(monkeypatch, body):
    """高德结构不对时只能退回 Nominatim，不能漏出 TypeError/AttributeError。"""
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        mocker.get(AMAP_GEOCODE_URL, json=body)
        mocker.get(NOMINATIM_URL, json=[{"lon": "121.5839", "lat": "38.8816"}])

        assert resolve_location("星海广场") == "121.5839,38.8816"


def test_resolve_location_does_not_geocode_coordinates(monkeypatch):
    """已经是坐标就不该发任何网络请求（省配额，也省 1 req/s 的等待）。"""
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        assert resolve_location("121.5839,38.8816") == "121.5839,38.8816"
        assert mocker.request_history == []
