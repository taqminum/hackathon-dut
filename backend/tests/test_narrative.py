from unittest.mock import patch
from app.services.narrative import generate_narrative


def test_generate_narrative_success():
    with patch("app.services.narrative.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "推荐理由"}}]
        }
        with patch.dict("os.environ", {"LLM_API_BASE": "http://localhost", "LLM_MODEL": "demo"}):
            text = generate_narrative({"routes": []}, "+5")
            assert text == "推荐理由"
            mock_post.assert_called_once()


def test_generate_narrative_timeout_fallback():
    with patch("app.services.narrative.requests.post", side_effect=TimeoutError):
        text = generate_narrative({"routes": []}, "+5")
        assert text == "这条路线上有几个值得停留的小地方，适合慢慢走。"
