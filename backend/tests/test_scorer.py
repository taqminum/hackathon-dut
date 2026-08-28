"""打分。

重点钉住 P2-2 修的那个缺陷：标签这一维过去是 `len(matched_tags) * 3.0`，
而调用方恒传单元素列表 —— 于是它是个常数，打分里「标签匹配」完全没参与决策。
现在它由用户反馈驱动（tag_affinity），必须能真的改变排序。
"""

import math

import pytest

from app.services.scorer import SerendipityScorer


@pytest.fixture
def scorer():
    return SerendipityScorer()


def test_serendipity_scorer(scorer):
    score = scorer.score(detour_minutes=10, poi_quality=0.8, tag_affinity=0.0)
    assert score > 0


def test_score_upper_bound_stays_seven(scorer):
    """上限必须是 7.0：前端 ScoreMeter 与 scoreToPercent 都按 7 分制填格。

    改权重而不改前端，评分条会永远填不满（或者爆表）。
    """
    best = scorer.score(detour_minutes=0, poi_quality=1.0, tag_affinity=1.0)
    assert best == pytest.approx(7.0)


def test_affinity_changes_the_score(scorer):
    """同一个 POI，用户喜欢过这类地方就该得更高分 —— 这一维不再是常数。"""
    neutral = scorer.score(detour_minutes=2, poi_quality=0.8, tag_affinity=0.0)
    liked = scorer.score(detour_minutes=2, poi_quality=0.8, tag_affinity=1.0)
    disliked = scorer.score(detour_minutes=2, poi_quality=0.8, tag_affinity=-1.0)

    assert disliked < neutral < liked


def test_affinity_can_outweigh_a_small_rating_gap(scorer):
    """「下次帮你换一条」要成立：明确不喜欢的类目应当输给评分略低但用户喜欢的。

    评分差 0.4 星（quality 差 0.08 -> 0.32 分），而反馈能动 3.0 分的量级。
    """
    disliked_but_better_rated = scorer.score(
        detour_minutes=2, poi_quality=4.8 / 5, tag_affinity=-1.0
    )
    liked_slightly_worse = scorer.score(
        detour_minutes=2, poi_quality=4.4 / 5, tag_affinity=1.0
    )

    assert liked_slightly_worse > disliked_but_better_rated


def test_neutral_leaves_headroom_for_positive_feedback(scorer):
    """冷启动不能已经满格，否则点「还不错」评分不动，闭环在界面上看不出来。"""
    neutral = scorer.score(detour_minutes=0, poi_quality=0.0, tag_affinity=0.0)
    liked = scorer.score(detour_minutes=0, poi_quality=0.0, tag_affinity=1.0)

    assert 0 < neutral < liked


def test_detour_is_penalised(scorer):
    near = scorer.score(detour_minutes=1, poi_quality=0.8)
    far = scorer.score(detour_minutes=12, poi_quality=0.8)

    assert far < near


def test_score_never_goes_negative(scorer):
    """绕行极大时分数落到 0，不能是负数：前端按比例填格，负值会画反。"""
    assert scorer.score(detour_minutes=500, poi_quality=0.0, tag_affinity=-1.0) == 0.0


@pytest.mark.parametrize("bad", [None, "", "abc", float("nan"), [], {}])
def test_score_survives_malformed_inputs(scorer, bad):
    """脏数据不该让主接口 500 —— 评分只是锦上添花。"""
    score = scorer.score(detour_minutes=1, poi_quality=bad, tag_affinity=bad)
    assert math.isfinite(score)
    assert score >= 0.0


def test_affinity_is_clamped_beyond_the_declared_range(scorer):
    """affinity 超出 [-1, 1] 时按边界处理，不要外推出 7 分以上的分数。"""
    assert scorer.score(detour_minutes=0, poi_quality=1.0, tag_affinity=99) == pytest.approx(7.0)
    assert scorer.score(
        detour_minutes=0, poi_quality=1.0, tag_affinity=-99
    ) == scorer.score(detour_minutes=0, poi_quality=1.0, tag_affinity=-1.0)
