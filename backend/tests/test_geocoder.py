import requests_mock
import pytest

from app.services.dalian import LANDMARK_ALIASES, LANDMARKS, landmark
from app.services.geocoder import ensure_location_in_city, resolve_location


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
AMAP_REGEOCODE_URL = "https://restapi.amap.com/v3/geocode/regeo"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def test_resolve_location_uses_global_amap_geocoding_when_key_present(monkeypatch):
    """有 Key 就走高德；真实地点输入不再被固定限制在大连。"""
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
    assert "city" not in request.qs
    assert request.qs["address"] == ["星海广场"]
    # 命中高德就不该再打 Nominatim
    assert all("nominatim" not in item.hostname for item in mocker.request_history)


def test_resolve_location_sends_selected_city_to_amap(monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")
    with requests_mock.Mocker() as mocker:
        mocker.get(
            AMAP_GEOCODE_URL,
            json={"status": "1", "geocodes": [{"location": "121.588870,38.882379"}]},
        )
        assert resolve_location("星海广场", "大连市") == "121.5839,38.8816"
    assert mocker.request_history[0].qs["city"] == ["大连市"]


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
    """没有 Key 时也不能重现跨国误判：viewbox + bounded=1 必须带上。

    这里刻意用一个**不在**地标词典里的地名：六个演示地标现在离线直接命中，
    再拿它们做样本就测不到 Nominatim 的参数了。
    """
    monkeypatch.delenv("AMAP_KEY", raising=False)

    with requests_mock.Mocker() as mocker:
        mocker.get(NOMINATIM_URL, json=[{"lon": "121.6385", "lat": "38.9198"}])

        assert resolve_location("中山广场") == "121.6385,38.9198"

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


def test_demo_landmarks_resolve_to_scenario_key_coordinates(monkeypatch):
    """手打地名必须落到和演示卡片**同一个**坐标上。

    这是实测踩到的事故：无 Key 时 Nominatim 把「大连理工大学」解析成
    121.5199,38.8856，和兜底表 key 的 121.5197,38.8856 差 0.0002，
    于是整条路线绕不进演示数据 —— 界面上是「这段路没有找到亮点」加 0.0 分；
    「东港商务区」Nominatim 直接认不出，接口回 404。

    断言用 `landmark()` 生成期望值，而不是把坐标抄一遍：抄一遍的话改了
    LANDMARKS 这条测试会跟着一起「正确」，守卫就失效了。
    """
    monkeypatch.delenv("AMAP_KEY", raising=False)

    for slug, (name, _lng, _lat) in LANDMARKS.items():
        with requests_mock.Mocker() as mocker:
            assert resolve_location(name) == landmark(slug), name
            # 命中词典就不该出网 —— 省配额，也说明真的没走 Nominatim
            assert mocker.request_history == [], name


def test_demo_landmark_aliases_resolve_offline(monkeypatch):
    """简称也要能用：评委不会每次都打全名。"""
    monkeypatch.delenv("AMAP_KEY", raising=False)

    for alias, slug in LANDMARK_ALIASES.items():
        with requests_mock.Mocker() as mocker:
            assert resolve_location(alias) == landmark(slug), alias
            assert mocker.request_history == [], alias


def test_unknown_place_still_falls_back_to_nominatim(monkeypatch):
    """词典只兜六个地标，别的地名照旧走地理编码，不能被顺手截掉。"""
    monkeypatch.delenv("AMAP_KEY", raising=False)

    with requests_mock.Mocker() as mocker:
        mocker.get(NOMINATIM_URL, json=[{"lon": "121.6271", "lat": "38.9189"}])

        assert resolve_location("大连火车站") == "121.6271,38.9189"

    assert any("nominatim" in item.hostname for item in mocker.request_history)


def test_landmark_dictionary_does_not_fuzzy_match(monkeypatch):
    """只做精确匹配：把「大连火车站」匹到「大连理工大学」比认不出更难查。"""
    monkeypatch.delenv("AMAP_KEY", raising=False)

    with requests_mock.Mocker() as mocker:
        mocker.get(NOMINATIM_URL, json=[{"lon": "121.6271", "lat": "38.9189"}])

        # 含「大连」但不是地标
        assert resolve_location("大连火车站") != landmark("dut")


def test_amap_wins_over_local_dictionary_when_key_present(monkeypatch):
    """有 Key 时真实高德值优先，词典只是无 Key 的兜底，不能反过来盖住高德。"""
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        # 故意给一个和词典不同的 GCJ-02 值
        mocker.get(
            AMAP_GEOCODE_URL,
            json={"status": "1", "geocodes": [{"location": "121.600000,38.900000"}]},
        )

        resolved = resolve_location("星海广场")

    assert resolved != landmark("xinghai")
    assert any("restapi.amap.com" in item.hostname for item in mocker.request_history)


def test_landmark_dictionary_covers_amap_failure_without_nominatim(monkeypatch):
    """有 Key 但高德连不上时，地标仍应离线命中，不必依赖 Nominatim。"""
    import requests

    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        mocker.get(AMAP_GEOCODE_URL, exc=requests.ConnectTimeout)

        assert resolve_location("老虎滩海洋公园") == landmark("laohutan")

    assert all("nominatim" not in item.hostname for item in mocker.request_history)


def test_resolve_location_does_not_geocode_coordinates(monkeypatch):
    """已经是坐标就不该发任何网络请求（省配额，也省 1 req/s 的等待）。"""
    monkeypatch.setenv("AMAP_KEY", "test-key")

    with requests_mock.Mocker() as mocker:
        assert resolve_location("121.5839,38.8816") == "121.5839,38.8816"
        assert mocker.request_history == []


def test_city_validation_compares_city_level_adcodes(monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")
    with requests_mock.Mocker() as mocker:
        mocker.get(AMAP_GEOCODE_URL, json={"status": "1", "geocodes": [{"adcode": "210200"}]})
        mocker.get(
            AMAP_REGEOCODE_URL,
            json={"status": "1", "regeocode": {"addressComponent": {"adcode": "210211"}}},
        )
        assert ensure_location_in_city("121.5839,38.8816", "大连市") is True


def test_city_validation_rejects_other_city(monkeypatch):
    monkeypatch.setenv("AMAP_KEY", "test-key")
    with requests_mock.Mocker() as mocker:
        mocker.get(AMAP_GEOCODE_URL, json={"status": "1", "geocodes": [{"adcode": "210200"}]})
        mocker.get(
            AMAP_REGEOCODE_URL,
            json={"status": "1", "regeocode": {"addressComponent": {"adcode": "110101"}}},
        )
        assert ensure_location_in_city("116.4039,39.9140", "大连市") is False
