"""S0 / S2：沿途亮点的两条硬约束 —— 标记不能飘出路线，米数不能是别的数字。

用户截图里「2 号标记横向飘出三四百米」和「距路线约 70 米对不上」是同一处数据缺陷的
两个表现：`_collect_highlights` 拿 400 米当「顺路」，而卡片上印的又不是它算出的那个
距离，是高德 `place/around` 回的「距搜索采样点」距离。

两条各自能破坏验证：
  * 把 `NEARBY_POI_METERS` 调回 400 -> `test_nearby_threshold_keeps_markers_on_the_route` 变红
  * 删掉 `_collect_highlights` 里写回 `off_route_meters` 的那行 ->
    `test_every_highlight_carries_its_real_distance_to_the_route` 变红
"""

import time

import pytest

from app.routes.api import (
    _choose_candidate,
    _collect_highlights,
    _evaluate_candidates,
    _prepare_poi_candidates,
)
from app.services.dalian import landmark
from app.services.poi_explorer import explore_pois_along_route
from app.services.route_engine import SOURCE_AMAP, get_candidate_routes, point_to_route_meters

DEMO_PAIRS = (("dut", "xinghai"), ("donggang", "laohutan"), ("xianlu", "fujiazhuang"))
MODES = ("+5", "+15", "roam")

# 图上「顺路」说得过去的上限，**写死**而不是引用 NEARBY_POI_METERS。
#
# 一开始这里就是引用那个常量的，结果是个假守卫：把 `NEARBY_POI_METERS` 从 150 调回 400，
# 断言的上限跟着变成 400，25 条全绿（实测过）。守卫必须独立于被守的那个值 ——
# 阈值是产品判断（150 米约等于半个街区，画到地图上还能说「沿途会经过」），
# 写在测试里才守得住。
MAX_OFF_ROUTE_METERS = 150

# 用户截图里那条路径。它**不在**三张兜底表里，所以走的是「非演示场景」的兜底分支 ——
# 三场景九组合全绿不代表这一条也绿，S0 的验收标准专门点了它。
AD_HOC_ROUTE = ("121.5537,38.8617", "121.5424,38.8901")


def _highlights(origin: str, destination: str, mode: str) -> tuple[list[dict], dict]:
    """进程内跑一遍推荐，返回 (highlights, 选中的路线)。

    不用 TestClient：那会经过 app.main 的 load_dotenv，真实 AMAP_KEY 渗进来就会打
    付费接口。conftest 的 isolate_environment 已经清掉 AMAP_KEY，这里拿到的一定是兜底。
    """
    baseline = get_candidate_routes(origin, destination, mode)[0]
    pois = explore_pois_along_route(
        origin, destination, ["餐饮", "景点", "购物"], radius=400, polyline=baseline["polyline"]
    )
    candidates = _evaluate_candidates(
        origin, destination, mode, baseline, pois, time.monotonic()
    )
    chosen = _choose_candidate(candidates, mode)
    if not chosen:
        return [], baseline
    return _collect_highlights(chosen, pois), chosen["route"]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("pair", DEMO_PAIRS)
def test_nearby_threshold_keeps_markers_on_the_route(pair, mode):
    """S0：每个返回的亮点到推荐折线的真实距离都必须 ≤ 150 米。

    这条断言的是**独立算出来的**距离，上限也是写死的 —— 引用 `NEARBY_POI_METERS`
    的话，把那个常量调回 400 会让断言的上限一起放宽，守卫形同虚设（实测全绿）。

    破坏验证：`NEARBY_POI_METERS` 改回 400，xianlu→fujiazhuang 那个 196 米的
    傅家庄公共海滩就会重新进列表，这条变红。
    """
    highlights, route = _highlights(*map(landmark, pair), mode)
    assert highlights, f"{pair} @{mode} 兜底演示数据必须给出亮点"

    for index, poi in enumerate(highlights):
        measured = point_to_route_meters(poi.get("location"), route["polyline"])
        assert measured is not None, f"{pair} @{mode} 第 {index + 1} 个亮点算不出距离"
        assert measured <= MAX_OFF_ROUTE_METERS, (
            f"{pair} @{mode} 第 {index + 1} 个亮点 {poi.get('name')} 距推荐折线 "
            f"{measured:.0f} 米，超过 {MAX_OFF_ROUTE_METERS} 米 —— 图上会飘到另一个街区"
        )


@pytest.mark.parametrize("mode", MODES)
def test_nearby_threshold_holds_for_a_route_outside_the_demo_tables(mode):
    """S0 的第二半：非演示场景的真实路径同样不能飘。

    三张兜底表只覆盖三条预置路线，用户截图那条不在表里。这条用一对任意大连坐标走
    「无 scenario」的兜底分支，确认阈值对它也生效（这条分支下 POI 池为空时
    highlights 也为空，那同样满足「没有飘出去的标记」）。
    """
    highlights, route = _highlights(*AD_HOC_ROUTE, mode)

    for poi in highlights:
        measured = point_to_route_meters(poi.get("location"), route["polyline"])
        assert measured is not None and measured <= MAX_OFF_ROUTE_METERS, (
            f"任意坐标路线 @{mode} 的亮点 {poi.get('name')} 距折线 {measured} 米"
        )


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("pair", DEMO_PAIRS)
def test_every_highlight_carries_its_real_distance_to_the_route(pair, mode):
    """S2：`off_route_meters` 必须等于独立算出的真实距离，**含 highlights[0]**。

    首项走的是另一条代码路径（它来自候选评估的途经点，不经过 nearby 循环），
    修复前它身上根本没有这个字段，卡片只能退回显示高德的「距采样点」距离。

    破坏验证：删掉 `_collect_highlights` 里 `chosen_poi = {**chosen_poi,
    "off_route_meters": chosen_distance}` 那行 -> 首项缺字段，这条变红。
    """
    highlights, route = _highlights(*map(landmark, pair), mode)
    assert highlights, f"{pair} @{mode} 兜底演示数据必须给出亮点"

    for index, poi in enumerate(highlights):
        assert "off_route_meters" in poi, (
            f"{pair} @{mode} 第 {index + 1} 个亮点没有 off_route_meters，"
            "前端会退回显示高德的「距采样点」距离"
        )
        expected = point_to_route_meters(poi["location"], route["polyline"])
        assert poi["off_route_meters"] == pytest.approx(expected, abs=0.5), (
            f"{pair} @{mode} 第 {index + 1} 个亮点报 {poi['off_route_meters']:.1f} 米，"
            f"真实 {expected:.1f} 米"
        )


@pytest.mark.parametrize("pair", DEMO_PAIRS)
def test_off_route_meters_is_not_the_amap_sample_distance(pair):
    """S2 的要点：新字段不能只是把 `distance` 改个名字。

    兜底数据里 `distance` 是实测的「距采样点」距离（70 / 7 / 32 ...），与到推荐折线的
    距离是两回事。这条钉住「至少有一个亮点的两个数字不同」—— 如果有人图省事写成
    `off_route_meters = distance`，这条就红。
    """
    highlights, _route = _highlights(*map(landmark, pair), "+15")
    assert highlights

    differs = [
        poi
        for poi in highlights
        if poi.get("distance") is not None
        and abs(float(poi["off_route_meters"]) - float(poi["distance"])) > 1.0
    ]
    assert differs, (
        f"{pair} 所有亮点的 off_route_meters 都等于 distance —— "
        "新字段疑似只是旧字段改了个名字"
    )


def test_highlight_without_a_measurable_distance_is_dropped():
    """折线退化成单点时算不出距离，此时不能猜一个 0 蒙过去。

    返回空列表是对的：0 会把一个位置未知的店说成「就在路边」，而这正是
    「卖偶遇的产品不能在这句话上注水」要防的。
    """
    chosen = {
        "poi": {"name": "位置说不清的店", "type": "餐饮", "location": "121.5197,38.8856"},
        # 单点折线构不成线段 -> point_to_route_meters 返回 None
        "route": {"polyline": "121.5197,38.8856"},
    }

    assert _collect_highlights(chosen, []) == []


def test_highlights_prefer_on_theme_pois_over_higher_rated_dining():
    chosen = {
        "poi": {"name": "途经咖啡馆", "type": "餐饮服务;咖啡厅;咖啡厅", "location": "121.5200,38.8850"},
        "route": {"polyline": "121.5197,38.8856;121.5205,38.8851"},
    }
    pois = [
        {"name": "高分烧烤店", "type": "餐饮服务;中餐厅;烧烤", "rating": 4.9,
         "location": "121.5201,38.8851"},
        {"name": "路边书店", "type": "购物服务;专卖店;书店", "rating": 4.2,
         "location": "121.5202,38.8851"},
    ]

    highlights = _collect_highlights(chosen, pois)

    assert [poi["name"] for poi in highlights] == ["途经咖啡馆", "路边书店", "高分烧烤店"]


def test_prepare_poi_candidates_prefers_on_theme_pois_with_close_ratings():
    pois = [
        {"name": "高分烧烤店", "type": "餐饮服务;中餐厅;烧烤", "rating": 4.6, "source": SOURCE_AMAP,
         "location": "121.5200,38.8850", "navigation_location": "121.5200,38.8850"},
        {"name": "沿途公园", "type": "风景名胜;公园广场;公园", "rating": 4.5, "source": SOURCE_AMAP,
         "location": "121.5201,38.8851", "navigation_location": "121.5201,38.8851"},
    ]

    prepared = _prepare_poi_candidates(pois)

    assert [item[0]["name"] for item in prepared] == ["沿途公园", "高分烧烤店"]
