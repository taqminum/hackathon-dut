"""地点名 -> WGS-84 `"lng,lat"`。

优先用高德地理编码：它支持 `city` 参数做城市偏置。Nominatim 没有城市概念，
实测「老虎滩」解析到新西兰、「星海广场」解析到西藏 —— 一次错误解析会让整条
路线跑到几千公里外，比任何显示问题都严重。

没有 AMAP_KEY 时退回 Nominatim，但**必须**带上大连的 viewbox 并且 bounded=1，
否则兜底路径会重现同样的跨国误判。

对外只有 WGS-84：高德返回的是 GCJ-02，这里转完再交出去。
"""

import functools
import math
import os

import requests

from app.services.coord import gcj02_str_to_wgs84_str, wgs84_str_to_gcj02_str
from app.services.dalian import landmark, landmark_slug

# 限流是进程级的，必须所有打高德的模块共用同一个实例，否则 10021 照旧会出现。
# 它眼下住在 route_engine 里，所以这里形成了 geocoder -> route_engine 的依赖 ——
# 方向上有点别扭（地理编码并不需要路径引擎）。要解耦就把 throttle_amap 提到
# 独立模块（比如 services/amap.py），两边一起从那里导入，别各自复制一份。
from app.services.route_engine import throttle_amap

AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"
AMAP_REGEOCODE_URL = "https://restapi.amap.com/v3/geocode/regeo"
GEOCODING_URL = "https://nominatim.openstreetmap.org/search"

# 不再把真实地点解析锁死在大连。前端从高德联想选中时直接提交坐标；手工输入地名时
# 先按全国地址编码，再按全国 POI 关键字搜索。
DEFAULT_CITY = ""
# Nominatim 的兜底边界（大连市域，WGS-84）：left,top,right,bottom
DALIAN_VIEWBOX = "120.9,39.6,123.0,38.4"


def resolve_location(location: str | None, city: str = "") -> str:
    value = str(location or "").strip()
    if not value:
        raise ValueError("location is empty")

    if "," in value:
        try:
            lng, lat = value.split(",", 1)
            return _format_coord(lng, lat)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid coordinates") from exc

    selected_city = str(city or "").strip()
    # 有 Key 就先打高德：真实路网下真实坐标最准。所选城市必须传入，不能只把
    # citylimit 用在联想框，否则手输「星海广场」仍可能解析到外省同名地点。
    if os.getenv("AMAP_KEY"):
        resolved = _resolve_with_amap(value, selected_city) or _resolve_poi_with_amap(value, selected_city)
        if resolved:
            return resolved

    # 六个演示地标的离线词典，排在 Nominatim 之前。
    #
    # 兜底表的 key 是 `dalian.landmark()` 算出的 4 位小数坐标，要求**完全相等**
    # 才命中。地理编码回来的值差 0.0002 就足以让「大连理工大学 -> 星海广场」
    # 错过演示数据 —— 实测结果页是「这段路没有找到亮点」加 0.0 分；Nominatim
    # 认不出「东港商务区」时更直接 404「未找到可行路线」。
    #
    # 词典保证无 Key 时手打地名和点演示卡片落到同一份数据上，顺带省掉一次出网。
    # 只做精确匹配（见 `landmark_slug`）：模糊匹配会把「大连火车站」匹到
    # 「大连理工大学」，错误解析比解析不出来更难查。
    slug = landmark_slug(value)
    if slug:
        return landmark(slug)

    return _resolve_with_nominatim(value)


def ensure_location_in_city(location: str, city: str) -> bool:
    """确认一个 WGS-84 坐标属于所选城市。

    输入提示的 ``citylimit`` 只能约束下拉列表；手工输入地名或直接提交坐标仍可能
    跨城。因此正式请求再用高德逆地理编码拿到行政区划代码，与城市编码的前四位
    比较。四位是地级市粒度，也同时适用于北京、上海等直辖市。
    """
    selected_city = str(city or "").strip()
    if not selected_city:
        raise ValueError("请选择城市")
    key = os.getenv("AMAP_KEY")
    if not key:
        # 调用方只在真实高德链路启用此校验；保留这个防御分支便于离线单测。
        return True

    city_adcode = _city_adcode(selected_city)
    point_adcode = _reverse_adcode(location)
    if not city_adcode or not point_adcode:
        raise RuntimeError("无法核实地点所在城市")
    return city_adcode[:4] == point_adcode[:4]


@functools.lru_cache(maxsize=64)
def _city_adcode(city: str) -> str | None:
    try:
        throttle_amap()
        response = requests.get(
            AMAP_GEOCODE_URL,
            params={"address": city, "key": os.getenv("AMAP_KEY")},
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise RuntimeError("城市范围校验服务不可用") from exc
    geocodes = data.get("geocodes") if isinstance(data, dict) else None
    first = geocodes[0] if isinstance(geocodes, list) and geocodes else None
    adcode = first.get("adcode") if isinstance(first, dict) else None
    return str(adcode) if isinstance(adcode, str) and len(adcode) >= 4 else None


def _reverse_adcode(location: str) -> str | None:
    gcj_location = wgs84_str_to_gcj02_str(location) or location
    try:
        throttle_amap()
        response = requests.get(
            AMAP_REGEOCODE_URL,
            params={"location": gcj_location, "key": os.getenv("AMAP_KEY"), "radius": 0},
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise RuntimeError("城市范围校验服务不可用") from exc
    component = data.get("regeocode", {}).get("addressComponent", {}) if isinstance(data, dict) else {}
    adcode = component.get("adcode") if isinstance(component, dict) else None
    return str(adcode) if isinstance(adcode, str) and len(adcode) >= 4 else None


def _resolve_with_amap(value: str, city: str = "") -> str | None:
    """高德地理编码。任何异常都返回 None，让调用方退回 Nominatim。"""
    params = {
        "address": value,
        "key": os.getenv("AMAP_KEY"),
    }
    if city:
        params["city"] = city

    try:
        throttle_amap()
        response = requests.get(AMAP_GEOCODE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception:
        # 地点解析是多级链路；关键字搜索的任何客户端/响应异常都交给下一层兜底。
        return None

    if not isinstance(data, dict):
        return None

    geocodes = data.get("geocodes")
    if not isinstance(geocodes, list) or not geocodes:
        return None

    first = geocodes[0]
    if not isinstance(first, dict):
        return None

    # 高德把「没有这个字段」表示成 []，float([]) 会抛 TypeError。
    raw_location = first.get("location")
    if not isinstance(raw_location, str) or "," not in raw_location:
        return None

    converted = gcj02_str_to_wgs84_str(raw_location) or raw_location
    try:
        lng, lat = converted.split(",", 1)
        return _format_coord(lng, lat)
    except (TypeError, ValueError):
        return None


def _resolve_poi_with_amap(value: str, city: str = "") -> str | None:
    """地址编码找不到时，用高德 POI 关键字搜索补足商店、景点和场馆名称。"""
    params = {
        "keywords": value,
        "offset": 1,
        "page": 1,
        "key": os.getenv("AMAP_KEY"),
    }
    if city:
        params.update({"city": city, "citylimit": "true"})
    try:
        throttle_amap()
        response = requests.get(AMAP_PLACE_TEXT_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    if not isinstance(data, dict) or str(data.get("status")) != "1":
        return None
    pois = data.get("pois")
    if not isinstance(pois, list) or not pois or not isinstance(pois[0], dict):
        return None
    raw_location = pois[0].get("location")
    if not isinstance(raw_location, str) or "," not in raw_location:
        return None
    converted = gcj02_str_to_wgs84_str(raw_location) or raw_location
    try:
        lng, lat = converted.split(",", 1)
        return _format_coord(lng, lat)
    except (TypeError, ValueError):
        return None


def _resolve_with_nominatim(value: str) -> str:
    """Nominatim 兜底。bounded=1 + viewbox 把结果钉在大连，避免跨国误判。"""
    try:
        response = requests.get(
            GEOCODING_URL,
            params={
                "q": value,
                "format": "json",
                "limit": 1,
                "viewbox": DALIAN_VIEWBOX,
                "bounded": 1,
            },
            headers={"User-Agent": "hackathon-dut/1.0"},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or not data:
            raise ValueError("empty geocode result")
        return _format_coord(data[0]["lon"], data[0]["lat"])
    except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
        raise ValueError(f"geocode failed: {value}") from exc


def normalize_coordinate(location: str | None) -> str:
    value = str(location or "").strip()
    if "," not in value:
        raise ValueError("invalid coordinates")
    try:
        lng, lat = value.split(",", 1)
        return _format_coord(lng, lat)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid coordinates") from exc


def _format_coord(lng, lat) -> str:
    longitude = float(lng)
    latitude = float(lat)
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise ValueError("invalid coordinates")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("invalid coordinates")
    return f"{longitude:.4f},{latitude:.4f}"
