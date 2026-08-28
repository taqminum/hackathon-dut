from unittest.mock import patch

import pytest

from app.services.coord import gcj02_str_to_wgs84_str
from app.services.poi_explorer import explore_pois_along_route


def test_explore_pois_along_route_trusts_server_side_type_filter():
    """types 只发给高德，本地不再复筛一遍。

    本地复筛过是 `any(t in poi_type for t in types)`，而 types 是
    ['餐饮','景点','购物']。高德返回的分类串用的是另一套词表 ——
    「风景名胜;公园广场;公园」里没有「景点」二字，于是整个景点类别被砍光。
    对一个卖「偶遇」的产品，景点恰恰是最该出现的类别。
    """
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "pois": [
                {"type": "餐饮服务;咖啡厅;咖啡厅", "name": "A", "distance": "50",
                 "location": "120.1,30.2", "biz_ext": {"rating": "4.5"}},
                {"type": "风景名胜;公园广场;公园", "name": "B", "distance": "200",
                 "location": "120.1,30.2", "biz_ext": {"rating": "4.0"}},
            ]
        }

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route("116.397428,39.90923", "116.407526,39.90403", ["餐饮"], 300)

    assert [poi["name"] for poi in pois] == ["A", "B"]
    mock_get.assert_called_once()


SCENIC_TYPE_STRINGS = (
    "风景名胜;公园广场;公园",
    "风景名胜;风景名胜;世界遗产",
    "风景名胜;风景名胜;国家级景点",
    "体育休闲服务;度假疗养场所;度假村",
)


@pytest.mark.parametrize("poi_type", SCENIC_TYPE_STRINGS)
def test_scenic_pois_are_not_discarded(poi_type):
    """这四种串过去全被本地复筛丢掉 —— 景点一个都到不了前端。"""
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "pois": [
                {
                    "type": poi_type,
                    "name": "值得一看的地方",
                    "distance": "120",
                    "location": "120.1,30.2",
                    "biz_ext": {"rating": "4.4"},
                }
            ]
        }

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route(
                "116.397428,39.90923", "116.407526,39.90403", ["餐饮", "景点", "购物"], 300
            )

    assert [poi["name"] for poi in pois] == ["值得一看的地方"]


def test_excluded_type_keywords_still_apply_without_local_type_filter():
    """删掉 types 复筛不能顺带放开类别噪声：便利店/烟酒店仍必须挡住。"""
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "pois": [
                {"type": "购物服务;便利店;便利店", "name": "某便利店", "distance": "30",
                 "location": "120.1,30.2", "biz_ext": {"rating": "4.0"}},
                {"type": "购物服务;烟酒专卖店;烟酒专卖店", "name": "某烟酒店", "distance": "40",
                 "location": "120.1,30.2", "biz_ext": {"rating": "4.2"}},
                {"type": "风景名胜;公园广场;公园", "name": "某公园", "distance": "50",
                 "location": "120.1,30.2", "biz_ext": {"rating": "4.3"}},
            ]
        }

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route(
                "116.397428,39.90923", "116.407526,39.90403", ["餐饮", "景点", "购物"], 300
            )

    assert [poi["name"] for poi in pois] == ["某公园"]


def test_explore_pois_along_route_returns_no_fake_pois_when_no_match():
    pois = explore_pois_along_route("116.397428,39.90923", "116.407526,39.90403", ["影院"], 300)

    assert pois == []


def test_explore_pois_along_route_discards_malformed_remote_pois():
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "pois": [
                None,
                "malformed",
                {"name": "缺少类型", "location": "120.1,30.2"},
                {
                    "name": "有效亮点",
                    "type": "景点",
                    "location": "120.1,30.2",
                    "biz_ext": {"rating": "4.2"},
                },
            ]
        }

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route("116.397428,39.90923", "116.407526,39.90403", ["景点"], 300)

    # location 是高德的 GCJ-02，对外要转成 WGS-84；rating 从 biz_ext 里取并转成 float。
    assert pois == [
        {
            "name": "有效亮点",
            "type": "景点",
            "distance": None,
            "rating": 4.2,
            "location": "120.095193,30.202275",
        }
    ]


def test_explore_pois_along_route_reads_rating_from_biz_ext():
    """高德把评分放在 biz_ext.rating，顶层没有 rating 字段。"""
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "pois": [
                {
                    "name": "有评分的店",
                    "type": "餐饮服务;中餐厅;中餐厅",
                    "location": "120.1,30.2",
                    # 字符串评分 + cost 是空数组，两个已知的解析陷阱
                    "biz_ext": {"rating": "4.8", "cost": []},
                }
            ]
        }

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route("116.397428,39.90923", "116.407526,39.90403", ["餐饮"], 300)

    assert len(pois) == 1
    assert pois[0]["rating"] == 4.8


def test_explore_pois_along_route_drops_low_rated_and_unrated_pois():
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "pois": [
                {"name": "评分太低", "type": "餐饮服务;中餐厅;中餐厅",
                 "location": "120.1,30.2", "biz_ext": {"rating": "2.2"}},
                {"name": "没有评分", "type": "餐饮服务;中餐厅;中餐厅",
                 "location": "120.1,30.2", "biz_ext": {"rating": []}},
                {"name": "够好的店", "type": "餐饮服务;中餐厅;中餐厅",
                 "location": "120.1,30.2", "biz_ext": {"rating": "4.1"}},
            ]
        }

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route("116.397428,39.90923", "116.407526,39.90403", ["餐饮"], 300)

    assert [poi["name"] for poi in pois] == ["够好的店"]


def test_explore_pois_along_route_excludes_types_without_serendipity():
    """便利店 4.0、烟酒专卖店 4.2 都能过评分门槛，但不该拿来当"偶遇"推荐。"""
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "pois": [
                {"name": "某便利店", "type": "购物服务;便民商店/便利店;便民商店/便利店",
                 "location": "120.1,30.2", "biz_ext": {"rating": "4.0"}},
                {"name": "某烟酒店", "type": "购物服务;专卖店;烟酒专卖店",
                 "location": "120.1,30.2", "biz_ext": {"rating": "4.2"}},
                {"name": "某超市", "type": "购物服务;超级市场;超市",
                 "location": "120.1,30.2", "biz_ext": {"rating": "3.9"}},
                {"name": "某咖啡厅", "type": "餐饮服务;咖啡厅;咖啡厅",
                 "location": "120.1,30.2", "biz_ext": {"rating": "3.6"}},
            ]
        }

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route(
                "116.397428,39.90923", "116.407526,39.90403", ["餐饮", "购物"], 300
            )

    assert [poi["name"] for poi in pois] == ["某咖啡厅"]


def _poi(name, rating):
    return {
        "name": name,
        "type": "餐饮服务;咖啡厅;咖啡厅",
        "location": "120.1,30.2",
        "biz_ext": {"rating": rating},
    }


def test_explore_pois_along_route_samples_three_points_of_polyline():
    """沿基准折线按里程 25%/50%/75% 各查一次，而不是只查中点。"""
    # 沿同一纬度的直线，里程比例直接对应经度，便于断言取样位置。
    polyline = ";".join(f"{120.0 + step * 0.05},30.0" for step in range(9))  # 120.00 -> 120.40
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"pois": [_poi("咖啡", "4.5")]}

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            explore_pois_along_route(
                "120.0,30.0", "120.4,30.0", ["餐饮"], radius=400, polyline=polyline
            )

    locations = [call.kwargs["params"]["location"] for call in mock_get.call_args_list]
    assert len(locations) == 3

    # 发出去的必须是 GCJ-02，转回 WGS-84 后应落在 25%/50%/75% 处。
    got_lngs = [float(gcj02_str_to_wgs84_str(loc).split(",")[0]) for loc in locations]
    for got, expected in zip(got_lngs, (120.1, 120.2, 120.3)):
        assert abs(got - expected) < 0.001

    assert all(call.kwargs["params"]["radius"] == 400 for call in mock_get.call_args_list)


def test_explore_pois_along_route_falls_back_to_midpoint_without_polyline():
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"pois": [_poi("咖啡", "4.5")]}

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            explore_pois_along_route("120.0,30.0", "120.4,30.0", ["餐饮"], radius=400)

    assert mock_get.call_count == 1
    location = mock_get.call_args.kwargs["params"]["location"]
    assert abs(float(gcj02_str_to_wgs84_str(location).split(",")[0]) - 120.2) < 0.001


def test_explore_pois_along_route_merges_samples_by_name():
    """相邻取样点的搜索圈会重叠，同名 POI 只保留一份（评分高的那份）。"""
    batches = [
        {"pois": [_poi("重复的店", "4.1"), _poi("只在第一个点", "4.4")]},
        {"pois": [_poi("重复的店", "4.6")]},
        {"pois": [_poi("只在第三个点", "3.9")]},
    ]
    polyline = ";".join(f"{120.0 + step * 0.05},30.0" for step in range(9))

    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.side_effect = batches

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route(
                "120.0,30.0", "120.4,30.0", ["餐饮"], radius=400, polyline=polyline
            )

    by_name = {poi["name"]: poi for poi in pois}
    assert set(by_name) == {"重复的店", "只在第一个点", "只在第三个点"}
    assert by_name["重复的店"]["rating"] == 4.6


def test_explore_pois_along_route_survives_one_failing_sample():
    polyline = ";".join(f"{120.0 + step * 0.05},30.0" for step in range(9))

    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.side_effect = [
            ValueError("bad json"),
            {"pois": [_poi("活下来的店", "4.3")]},
            {"pois": []},
        ]

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            pois = explore_pois_along_route(
                "120.0,30.0", "120.4,30.0", ["餐饮"], radius=400, polyline=polyline
            )

    assert [poi["name"] for poi in pois] == ["活下来的店"]


def test_explore_pois_along_route_ignores_malformed_polyline():
    with patch("app.services.poi_explorer.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"pois": [_poi("咖啡", "4.5")]}

        with patch.dict("os.environ", {"AMAP_KEY": "fake-key"}):
            explore_pois_along_route(
                "120.0,30.0", "120.4,30.0", ["餐饮"], radius=400, polyline="not-a-polyline;;x,y"
            )

    # 折线不可用时退回中点单点查询，而不是抛错。
    assert mock_get.call_count == 1
