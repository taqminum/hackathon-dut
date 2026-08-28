"""大连演示场景的唯一数据源（断网兜底用）。

三份兜底表（`route_engine.DALIAN_SCENARIOS`、`poi_explorer.DALIAN_POI_SCENARIOS`、
`narrative.DALIAN_SCENARIO_NARRATIVES`）过去各自写死一份 key，格式是
`"经度,纬度->经度,纬度"` 且 4 位小数必须完全相等才能命中 —— 改一处漏两处就会静默
退化成非演示模式。现在 key 统一由这里的地标坐标算出来，漏改在结构上不可能发生。

坐标一律存 **WGS-84**：兜底路线不经过高德，直接交给前端画图，而前端底图是
OSM（WGS-84）。地标的 GCJ-02 原值来自高德地理编码，用 `coord.gcj02_to_wgs84`
转换后写在下面（换算过程见 docs 交接文档「六个地标的真实坐标」）。
"""

# slug -> (中文名, WGS-84 经度, WGS-84 纬度)
# 右侧注释是高德地理编码给出的 GCJ-02 原值，便于核对。
LANDMARKS: dict[str, tuple[str, float, float]] = {
    "dut": ("大连理工大学", 121.519692, 38.885611),        # GCJ 121.524803,38.886490
    "xinghai": ("星海广场", 121.583926, 38.881623),        # GCJ 121.588870,38.882379
    "donggang": ("东港商务区", 121.678517, 38.928660),     # GCJ 121.683570,38.929545
    "laohutan": ("老虎滩海洋公园", 121.670101, 38.878254),  # GCJ 121.675131,38.879093
    "xianlu": ("西安路", 121.582538, 38.913575),           # GCJ 121.587487,38.914351
    "fujiazhuang": ("傅家庄公园", 121.616107, 38.865793),   # GCJ 121.621046,38.866543
}


def landmark(slug: str) -> str:
    """地标的 WGS-84 坐标串，4 位小数 —— 与兜底表 key 的精度一致。"""
    _, lng, lat = LANDMARKS[slug]
    return f"{lng:.4f},{lat:.4f}"


def scenario_key(origin_slug: str, destination_slug: str) -> str:
    """兜底表的 key。三张表都用这个函数生成，不再各写一遍字面量。"""
    return f"{landmark(origin_slug)}->{landmark(destination_slug)}"
