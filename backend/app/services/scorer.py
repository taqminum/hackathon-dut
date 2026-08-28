class SerendipityScorer:
    """一条候选路线值不值得绕：标签契合度 3 分 + POI 质量 4 分 - 绕行惩罚。

    **上限必须保持 7.0** —— 前端 `ScoreMeter` 与 `format.scoreToPercent` 都按 7 分制
    填格（webapp/src/components/ScoreMeter.vue、webapp/src/utils/format.js）。
    改这里的权重要同步改那两处，否则评分条会永远填不满或者爆表。

    `tag_affinity` 是这一维真正的输入，取值 [-1, 1]：
      * `0`  没有任何反馈（冷启动）—— 填到 NEUTRAL_FILL，留出反馈能推动的余量
      * `+1` 用户明确喜欢这类地方 -> 填满 3.0
      * `-1` 用户明确不喜欢 -> 归零

    过去这一维是 `len(matched_tags) * 3.0`，而调用方恒传单元素列表，
    于是它是个常数 3.0：打分里「标签匹配」完全没参与决策。
    """

    TAG_WEIGHT = 3.0
    QUALITY_WEIGHT = 4.0
    DETOUR_PENALTY_PER_MINUTE = 0.2
    # 冷启动时标签这一维填多少。取 0.7 而不是 1.0：满格留给「用户说了喜欢」，
    # 否则点「还不错」评分不会动，反馈闭环在界面上看不出来。
    NEUTRAL_FILL = 0.7

    def score(self, detour_minutes: float, poi_quality: float, tag_affinity: float = 0.0) -> float:
        detour_penalty = max(0.0, float(detour_minutes)) * self.DETOUR_PENALTY_PER_MINUTE
        tag_bonus = self.TAG_WEIGHT * self._tag_fill(tag_affinity)
        quality_bonus = self.QUALITY_WEIGHT * _clamp(poi_quality, 0.0, 1.0)
        return max(0.0, tag_bonus + quality_bonus - detour_penalty)

    def _tag_fill(self, tag_affinity: float) -> float:
        """affinity -> [0, 1] 的填充比例，分段线性，在 0 处连续。

        正负两侧斜率不同是有意的：冷启动已经在 NEUTRAL_FILL 上，
        往上只剩 1 - NEUTRAL_FILL 的余量，往下有 NEUTRAL_FILL 可以掉。
        """
        affinity = _clamp(tag_affinity, -1.0, 1.0)
        if affinity >= 0:
            return self.NEUTRAL_FILL + affinity * (1.0 - self.NEUTRAL_FILL)
        return self.NEUTRAL_FILL * (1.0 + affinity)


def _clamp(value, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    if number != number:  # NaN
        return low
    return min(high, max(low, number))
