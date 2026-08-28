"""地点名 -> WGS-84 `"lng,lat"`。

优先用高德地理编码：它支持 `city` 参数做城市偏置。Nominatim 没有城市概念，
实测「老虎滩」解析到新西兰、「星海广场」解析到西藏 —— 一次错误解析会让整条
路线跑到几千公里外，比任何显示问题都严重。

没有 AMAP_KEY 时退回 Nominatim，但**必须**带上大连的 viewbox 并且 bounded=1，
否则兜底路径会重现同样的跨国误判。

对外只有 WGS-84：高德返回的是 GCJ-02，这里转完再交出去。
"""

import math
import os

import requests

from app.services.coord import gcj02_str_to_wgs84_str

# 限流是进程级的，必须所有打高德的模块共用同一个实例，否则 10021 照旧会出现。
# 它眼下住在 route_engine 里，所以这里形成了 geocoder -> route_engine 的依赖 ——
# 方向上有点别扭（地理编码并不需要路径引擎）。要解耦就把 throttle_amap 提到
# 独立模块（比如 services/amap.py），两边一起从那里导入，别各自复制一份。
from app.services.route_engine import throttle_amap

AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
GEOCODING_URL = "https://nominatim.openstreetmap.org/search"

# 城市偏置。演示全程在大连，跨城搜索没有需求。
DEFAULT_CITY = "大连"
# Nominatim 的兜底边界（大连市域，WGS-84）：left,top,right,bottom
DALIAN_VIEWBOX = "120.9,39.6,123.0,38.4"


def resolve_location(location: str | None) -> str:
    value = str(location or "").strip()
    if not value:
        raise ValueError("location is empty")

    if "," in value:
        try:
            lng, lat = value.split(",", 1)
            return _format_coord(lng, lat)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid coordinates") from exc

    if os.getenv("AMAP_KEY"):
        resolved = _resolve_with_amap(value)
        if resolved:
            return resolved

    return _resolve_with_nominatim(value)


def _resolve_with_amap(value: str) -> str | None:
    """高德地理编码。任何异常都返回 None，让调用方退回 Nominatim。"""
    params = {
        "address": value,
        "city": DEFAULT_CITY,
        "key": os.getenv("AMAP_KEY"),
    }

    try:
        throttle_amap()
        response = requests.get(AMAP_GEOCODE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, TypeError, ValueError, AttributeError):
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
