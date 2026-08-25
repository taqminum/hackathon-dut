class SerendipityScorer:
    def score(self, detour_minutes: float, matched_tags: list[str], poi_quality: float) -> float:
        detour_penalty = detour_minutes * 0.5
        tag_bonus = len(matched_tags) * 2.0
        quality_bonus = poi_quality * 3.0
        return max(0.0, tag_bonus + quality_bonus - detour_penalty)
