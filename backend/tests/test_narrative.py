from unittest.mock import patch
from app.services.narrative import generate_narrative


def test_generate_narrative_success():
    with patch("app.services.narrative.requests.post") as mock_post:
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "推荐理由"}}]
        }
        text = generate_narrative({"routes": []}, "+5")
        assert text == "推荐理由"


def test_generate_narrative_timeout_fallback():
    with patch("app.services.narrative.requests.post", side_effect=TimeoutError):
        text = generate_narrative({"routes": []}, "+5")
        assert "推荐" in text
