"""偏好归因的约束。

核心是一条：一次反馈只能影响它真正指向的类目。
这个模块是演示时「点了不喜欢之后呢」的答案，答错的代价直接落在台上。
"""

import pytest

from app.models.preference import BROAD_TAGS, UNKNOWN_TAG, PreferenceManager, tags_for_type


@pytest.fixture
def manager():
    return PreferenceManager()


def test_specific_category_suppresses_its_broad_parent():
    """`餐饮服务;咖啡厅` 只算「咖啡」，不算「餐饮」。

    同时记父类目的话，父类目会把兄弟类目一起拖下去 —— 见下面那个渗漏测试。
    """
    assert tags_for_type("餐饮服务;咖啡厅") == ["咖啡"]
    assert "餐饮" not in tags_for_type("餐饮服务;咖啡厅;星巴克")


def test_broad_parent_still_used_when_nothing_specific_matches():
    """只命中父类目时不能退化成「其它」，否则宽泛餐馆的反馈就没地方落。"""
    assert tags_for_type("餐饮服务;餐馆") == ["餐饮"]
    assert tags_for_type("购物服务;商场") == ["购物"]


def test_disliking_a_coffee_shop_does_not_penalize_unrelated_restaurants(manager):
    """真 bug 的回归测试：负反馈不能渗到从来没被反馈过的类目上。

    改之前 `scores` 会是 `{'咖啡': -1, '餐饮': -1}`，于是海鲜酒楼和烧烤
    各拿到 -0.167 —— 用户没对它们表达过任何意见。
    """
    manager.record_feedback(liked=False, pois=[{"type": "餐饮服务;咖啡厅"}])

    assert manager.affinity("餐饮服务;海鲜酒楼") == 0.0
    assert manager.affinity("餐饮服务;烧烤") == 0.0
    assert manager.affinity("餐饮服务;火锅店") == 0.0
    assert manager.snapshot() == {"咖啡": -1}, "只应记下咖啡这一个类目"


def test_the_disliked_category_itself_still_moves(manager):
    """抑制父类目不能把功能一起抑制掉：被点的那个类目必须真的动。"""
    before = manager.affinity("餐饮服务;咖啡厅")
    manager.record_feedback(liked=False, pois=[{"type": "餐饮服务;咖啡厅"}])
    after = manager.affinity("餐饮服务;咖啡厅")

    assert before == 0.0
    assert after < before


def test_liking_one_category_does_not_lift_its_siblings(manager):
    """正向反馈同样不能渗漏 —— 喜欢咖啡不等于喜欢所有餐饮。"""
    manager.record_feedback(liked=True, pois=[{"type": "餐饮服务;咖啡厅"}])

    assert manager.affinity("餐饮服务;咖啡厅") > 0
    assert manager.affinity("餐饮服务;海鲜酒楼") == 0.0


def test_broad_tags_are_a_subset_of_declared_keywords():
    """BROAD_TAGS 写错字（比如写成「餐饮服务」）会静默失效，在这里钉住。"""
    from app.models.preference import TAG_KEYWORDS

    known = {tag for _keyword, tag in TAG_KEYWORDS}
    assert BROAD_TAGS <= known, f"BROAD_TAGS 里有不存在的类目: {BROAD_TAGS - known}"


def test_feedback_without_pois_changes_nothing(manager):
    """没有 POI 就没有可归因的类目：瞎猜一个比不记更糟。"""
    manager.record_feedback(liked=False, pois=None)
    manager.record_feedback(liked=True, pois=[])

    assert manager.snapshot() == {}


def test_unrecognized_type_still_lands_somewhere(manager):
    """认不出的类型也要有地方落，否则用户点了「一般」什么都没发生。

    这条原来断言的是 `affinity("另一种没见过的") < 0` —— 那把 bug 钉死了：
    它让「一个未知类型」代表「所有未知类型」。要保护的行为是「反馈落得下去」，
    不是「落进同一个桶」。
    """
    manager.record_feedback(liked=False, pois=[{"type": "体育休闲服务;度假疗养场所"}])

    assert manager.snapshot() == {"体育休闲服务": -1}
    assert manager.affinity("体育休闲服务;度假疗养场所") < 0


def test_one_unknown_type_does_not_drag_down_an_unrelated_unknown(manager):
    """第二个渗漏实例的回归测试：未知类型之间不能互相拖累。

    改之前 `snapshot` 是 `{'其它': -1}`，于是药店、酒店、电影院全部拿到 -0.333。
    按高德真实分类打表，共享的「其它」横跨 7 个互不相关的大类。
    """
    manager.record_feedback(liked=False, pois=[{"type": "体育休闲服务;度假疗养场所"}])

    assert manager.affinity("医疗保健服务;医疗保健;药店") == 0.0
    assert manager.affinity("住宿服务;宾馆酒店;酒店") == 0.0
    assert manager.affinity("金融保险服务;银行;银行") == 0.0
    assert manager.affinity("交通设施服务;公交车站;公交站") == 0.0


def test_unknown_bucket_granularity_is_the_amap_top_category(manager):
    """**有意的取舍**：未知桶的粒度是高德大类，不是完整 type 串。

    所以同一大类下的两个不同小类会互相影响（度假场所 <-> 电影院，都在
    体育休闲服务下）。按完整串分桶几乎学不到东西（每个小类各自一个桶，
    演示时点一次几乎不可能再遇到同一个串）；按大类分桶既能落地又不跨类。
    这条测试的作用是让这个取舍显式，改动时能看见。
    """
    manager.record_feedback(liked=False, pois=[{"type": "体育休闲服务;度假疗养场所"}])

    assert manager.affinity("体育休闲服务;影剧院;电影院") < 0, "同大类：有意会被影响"
    assert manager.affinity("医疗保健服务;药店") == 0.0, "跨大类：绝不能被影响"


def test_type_without_a_separator_becomes_its_own_bucket(manager):
    """没有分号的 type 串（不该出现，但别炸）也要各自成桶。"""
    assert tags_for_type("无分隔符类型") == ["无分隔符类型"]

    manager.record_feedback(liked=False, pois=[{"type": "无分隔符类型"}])
    assert manager.affinity("另一种无分隔符") == 0.0


@pytest.mark.parametrize("blank", [None, "", "   ", 123, [], {}])
def test_blank_or_nonstring_type_falls_back_to_the_shared_unknown(blank):
    """完全没有 type 可用时才回到共享的「其它」—— 此时没有任何可分桶的信息。"""
    assert tags_for_type(blank) == [UNKNOWN_TAG]


def test_magnitude_is_capped_so_opinions_can_be_reversed(manager):
    """连点十次不能让类目永久沉底 —— 演示时改主意得能翻回来。"""
    for _ in range(10):
        manager.record_feedback(liked=False, pois=[{"type": "餐饮服务;咖啡厅"}])
    bottom = manager.affinity("餐饮服务;咖啡厅")
    assert bottom == -1.0

    for _ in range(manager.MAX_MAGNITUDE * 2):
        manager.record_feedback(liked=True, pois=[{"type": "餐饮服务;咖啡厅"}])
    assert manager.affinity("餐饮服务;咖啡厅") == 1.0


# 高德分类体系里的真实 type 串形态（大类;中类;小类），覆盖 recommend 实际请求的
# 餐饮/景点/购物，外加 place/around 会顺带返回的邻近大类。
AMAP_TYPE_SAMPLES = (
    "餐饮服务;咖啡厅;咖啡厅", "餐饮服务;茶艺馆;茶艺馆", "餐饮服务;糕饼店;面包店",
    "餐饮服务;糕饼店;蛋糕店", "餐饮服务;冷饮店;甜品店", "餐饮服务;中餐厅;海鲜酒楼",
    "餐饮服务;中餐厅;火锅店", "餐饮服务;中餐厅;烧烤", "餐饮服务;快餐厅;快餐厅",
    "餐饮服务;休闲餐饮场所;小吃店", "餐饮服务;中餐厅;中餐厅",
    "餐饮服务;中餐厅;特色/地方风味餐厅", "餐饮服务;外国餐厅;日本料理",
    "风景名胜;公园广场;公园", "风景名胜;公园广场;城市广场",
    "风景名胜;风景名胜相关;海滨浴场", "旅游景点;风景名胜;景点",
    "科教文化服务;博物馆;博物馆", "科教文化服务;展览馆;展览馆",
    "科教文化服务;美术馆;美术馆", "购物服务;商场;商场",
    "购物服务;超级市场;超市", "购物服务;综合市场;购物中心",
    "体育休闲服务;度假疗养场所;度假疗养场所", "体育休闲服务;影剧院;电影院",
    "医疗保健服务;医疗保健;药店", "住宿服务;宾馆酒店;酒店",
    "生活服务;美容美发;美发", "商务住宅;楼宇;商务写字楼",
    "交通设施服务;公交车站;公交站", "金融保险服务;银行;银行",
)

# 有意跨大类的合并，逐个都有理由，不算共享桶：
#   风景 <- 风景名胜 + 旅游景点：高德把同一批景点分散在这两个大类下，
#           不合并的话「公园」和「景点」会被当成两类偏好。
#   人文 <- 科教文化服务 + 购物服务;专卖店;书店：书店在分类体系里挂在购物下，
#           但用户心里它跟博物馆是一类。
INTENTIONAL_CROSS_CATEGORY_TAGS = frozenset({"风景", "人文"})


def test_no_tag_is_a_shared_bucket_across_unrelated_categories():
    """结构性卫兵：任何一个桶都不许横跨多个不相关的高德大类。

    这条能同时抓住已经修过的两个实例 —— 「餐饮」（父类目渗到兄弟类目）和
    「其它」（所有未知类型共用）。写成按大类聚合而不是逐个断言，
    是为了以后往 TAG_KEYWORDS 里加词时能自动覆盖。
    """
    from collections import defaultdict

    top_categories = defaultdict(set)
    for sample in AMAP_TYPE_SAMPLES:
        head = sample.split(";", 1)[0]
        for tag in tags_for_type(sample):
            top_categories[tag].add(head)

    offenders = {
        tag: sorted(heads)
        for tag, heads in top_categories.items()
        if len(heads) > 1 and tag not in INTENTIONAL_CROSS_CATEGORY_TAGS
    }
    assert not offenders, f"这些桶横跨多个大类，是共享桶: {offenders}"


def test_every_sample_type_lands_on_at_least_one_tag():
    """反馈必须永远有地方落 —— 一个样本都不能返回空列表。"""
    for sample in AMAP_TYPE_SAMPLES:
        assert tags_for_type(sample), sample


def test_disliking_each_sample_never_moves_an_unrelated_top_category():
    """把渗漏检查跑遍所有样本：一次反馈不能影响其它大类的类型。"""
    for sample in AMAP_TYPE_SAMPLES:
        manager = PreferenceManager()
        manager.record_feedback(liked=False, pois=[{"type": sample}])
        head = sample.split(";", 1)[0]
        affected_tags = set(tags_for_type(sample))

        for other in AMAP_TYPE_SAMPLES:
            if other.split(";", 1)[0] == head:
                continue
            # 跨大类的类型只有在共享某个有意合并的桶时才允许被影响
            if affected_tags & set(tags_for_type(other)):
                continue
            assert manager.affinity(other) == 0.0, f"{sample} 的反馈渗到了 {other}"


def test_no_type_carries_both_a_specific_tag_and_a_broad_one():
    """结构性卫兵之二：渗漏的另一种形状 —— 同一大类内部的兄弟渗漏。

    上面那条按大类聚合的卫兵抓不到实例 1：「餐饮」全部落在 `餐饮服务` 这一个
    大类下，跨大类检查看不见它。实例 1 的不变量是另一句话：
    **一个 type 命中了具体子类目，就不该同时带上宽泛父类目**，
    否则父类目会把同大类的兄弟一起拖下去。两条卫兵合起来覆盖两种形状。
    """
    offenders = []
    for sample in AMAP_TYPE_SAMPLES:
        tags = set(tags_for_type(sample))
        broad_hits = tags & BROAD_TAGS
        if broad_hits and tags - BROAD_TAGS:
            offenders.append((sample, sorted(tags)))
    assert not offenders, f"这些 type 同时带了具体类目和宽泛父类目: {offenders}"
