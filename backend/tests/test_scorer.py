from app.services.scorer import SerendipityScorer


def test_serendipity_scorer():
    scorer = SerendipityScorer()
    score = scorer.score(detour_minutes=10, matched_tags=["food"], poi_quality=0.8)
    assert score > 0
