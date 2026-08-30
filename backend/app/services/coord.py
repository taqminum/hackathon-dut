"""GCJ-02（高德/火星坐标）与 WGS-84（GPS / OSM 瓦片）互转。

约定（全项目统一，改动前请先读这段）：

* **对外一律 WGS-84**：返回给前端的 polyline / POI location、以及兜底表里写死的坐标，
  都是 WGS-84。前端 Leaflet 用的是 OSM 瓦片，属 WGS-84。
* **对高德一律 GCJ-02**：发给 restapi.amap.com 的 origin / destination / location
  必须先转成 GCJ-02，返回的坐标必须转回 WGS-84。

大连一带两者相差约 450 米，不转换的话折线会整体偏离街道。
"""

import math

PI = math.pi
A = 6378245.0  # 克拉索夫斯基椭球长半轴（米）
EE = 0.00669342162296594323  # 第一偏心率的平方

# 中国大陆粗略包围盒。境外坐标两个坐标系一致，直接返回。
CHINA_BBOX = (73.66, 3.86, 135.05, 53.55)


def _out_of_china(lng: float, lat: float) -> bool:
    west, south, east, north = CHINA_BBOX
    return not (west < lng < east and south < lat < north)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def _delta(lng: float, lat: float) -> tuple[float, float]:
    d_lat = _transform_lat(lng - 105.0, lat - 35.0)
    d_lng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
    d_lng = (d_lng * 180.0) / (A / sqrt_magic * math.cos(rad_lat) * PI)
    return d_lng, d_lat


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    """WGS-84 -> GCJ-02。发给高德之前用。"""
    lng, lat = float(lng), float(lat)
    if _out_of_china(lng, lat):
        return lng, lat
    d_lng, d_lat = _delta(lng, lat)
    return lng + d_lng, lat + d_lat


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    """GCJ-02 -> WGS-84。高德返回之后、给前端之前用。

    偏移量 _delta 是定义在 WGS-84 点上的，所以反向不能直接减一阶近似
    （那样残差约 1.5 米）。这里用不动点迭代：每轮在当前 WGS-84 估计值上
    重算偏移。3 轮后往返残差 < 1e-9 度（约 0.1 毫米）。
    """
    lng, lat = float(lng), float(lat)
    if _out_of_china(lng, lat):
        return lng, lat
    wgs_lng, wgs_lat = lng, lat
    for _ in range(3):
        d_lng, d_lat = _delta(wgs_lng, wgs_lat)
        wgs_lng = lng - d_lng
        wgs_lat = lat - d_lat
    return wgs_lng, wgs_lat


def _parse(coord: str | None) -> tuple[float, float] | None:
    if not coord:
        return None
    try:
        lng, lat = str(coord).split(",", 1)
        lng, lat = float(lng), float(lat)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lng) or not math.isfinite(lat):
        return None
    if not -180 <= lng <= 180 or not -90 <= lat <= 90:
        return None
    return lng, lat


def _fmt(lng: float, lat: float, precision: int = 6) -> str:
    return f"{lng:.{precision}f},{lat:.{precision}f}"


def wgs84_str_to_gcj02_str(coord: str | None, precision: int = 6) -> str | None:
    """`"lng,lat"` 形式的 WGS-84 转 GCJ-02 串；无法解析时返回 None。"""
    parsed = _parse(coord)
    if parsed is None:
        return None
    return _fmt(*wgs84_to_gcj02(*parsed), precision=precision)


def gcj02_str_to_wgs84_str(coord: str | None, precision: int = 6) -> str | None:
    """`"lng,lat"` 形式的 GCJ-02 转 WGS-84 串；无法解析时返回 None。"""
    parsed = _parse(coord)
    if parsed is None:
        return None
    return _fmt(*gcj02_to_wgs84(*parsed), precision=precision)


def gcj02_polyline_to_wgs84(polyline: str | None, precision: int = 6) -> str:
    """把高德的明文折线 `"lng,lat;lng,lat"` 整条转成 WGS-84。

    解析不了的点原样保留，避免一个脏点毁掉整条折线。
    """
    if not polyline:
        return ""
    points = []
    for chunk in str(polyline).split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        converted = gcj02_str_to_wgs84_str(chunk, precision=precision)
        points.append(converted if converted else chunk)
    return ";".join(points)
