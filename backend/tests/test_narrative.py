from unittest.mock import patch

import pytest

from app.services.dalian import landmark, scenario_key
from app.services.narrative import (
    DALIAN_SCENARIO_NARRATIVES,
    DEFAULT_NARRATIVE,
    generate_narrative,
)
from app.services.route_engine import DALIAN_SCENARIOS


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


def test_generate_narrative_sends_bearer_token_when_key_configured():
    with patch("app.services.narrative.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "推荐理由"}}]
        }
        with patch.dict(
            "os.environ",
            {
                "LLM_API_BASE": "http://localhost",
                "LLM_API_KEY": "sk-test-123",
                "LLM_MODEL": "demo",
            },
        ):
            generate_narrative({"routes": []}, "+5")

    _, kwargs = mock_post.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer sk-test-123"}


def test_generate_narrative_timeout_fallback():
    with patch("app.services.narrative.requests.post", side_effect=TimeoutError):
        text = generate_narrative({"routes": []}, "+5")
        assert text == "这条路线上有几个值得停留的小地方，适合慢慢走。"


MALFORMED_LLM_BODIES = (
    {"choices": "not-a-list"},
    {"choices": [None]},
    {"choices": [{"message": "a string not a dict"}]},
    {"choices": [{}]},
    {"choices": [{"message": {"content": ""}}]},
    {"response": []},
    "a bare string, not a dict",
    ["a", "list"],
    42,
    None,
)


@pytest.mark.parametrize("body", MALFORMED_LLM_BODIES)
def test_generate_narrative_never_raises_on_malformed_llm_response(body):
    """响应是合法 JSON 但结构不对时不能抛异常 —— 之前会漏出 AttributeError
    让主接口 500（narrative.py 只捞了 TimeoutError / RequestException）。
    """
    with patch("app.services.narrative.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = body

        with patch.dict("os.environ", {"LLM_API_BASE": "http://localhost", "LLM_MODEL": "demo"}):
            text = generate_narrative({"polyline": "120.1,30.2;120.2,30.3"}, "+5")

    assert isinstance(text, str)
    assert text.strip()


def test_generate_narrative_accepts_openai_text_field():
    with patch("app.services.narrative.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"choices": [{"text": "另一种结构"}]}

        with patch.dict("os.environ", {"LLM_API_BASE": "http://localhost", "LLM_MODEL": "demo"}):
            assert generate_narrative({"routes": []}, "+5") == "另一种结构"


def test_generate_narrative_accepts_ollama_response_field():
    with patch("app.services.narrative.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"response": "ollama 文案"}

        with patch.dict("os.environ", {"LLM_API_BASE": "http://localhost", "LLM_MODEL": "demo"}):
            assert generate_narrative({"routes": []}, "+5") == "ollama 文案"


def test_generate_narrative_fills_real_poi_names_into_template():
    """拿到了真实店名就不该再说通用兜底句 —— 那等于把最有说服力的部分丢掉。"""
    pois = [
        {"name": "瑞幸咖啡(软件园店)", "type": "餐饮服务;咖啡厅;咖啡厅"},
        {"name": "星海公园", "type": "风景名胜;公园广场"},
    ]

    text = generate_narrative({"polyline": "120.1,30.2;120.2,30.3"}, "+5", pois=pois)

    assert "瑞幸咖啡(软件园店)" in text
    assert "星海公园" in text
    assert text != DEFAULT_NARRATIVE
    # 高德的 type 串太技术，不能原样出现在文案里
    assert "餐饮服务;" not in text
    assert "咖啡馆" in text


@pytest.mark.parametrize("mode", ["+5", "+15", "roam"])
def test_template_narrative_covers_every_mode(mode):
    pois = [{"name": "老王海鲜馆", "type": "餐饮服务;中餐厅;海鲜酒楼"}]

    text = generate_narrative({"polyline": "120.1,30.2;120.2,30.3"}, mode, pois=pois)

    assert "老王海鲜馆" in text
    assert text != DEFAULT_NARRATIVE


def test_template_narrative_ignores_malformed_pois():
    pois = [None, "malformed", {"name": ""}, {"type": "餐饮"}, {"name": "有名字的店"}]

    text = generate_narrative({"polyline": "120.1,30.2;120.2,30.3"}, "+5", pois=pois)

    assert "有名字的店" in text


def test_generate_narrative_falls_back_to_default_without_pois():
    text = generate_narrative({"polyline": "120.1,30.2;120.2,30.3"}, "+5", pois=[])

    assert text == DEFAULT_NARRATIVE


def test_handwritten_demo_narrative_wins_over_template():
    """三组演示路线的手写文案比模板自然，优先用它。"""
    scenario_polyline = ";".join(DALIAN_SCENARIOS[scenario_key("dut", "xinghai")]["polyline"])
    pois = [{"name": "某个店", "type": "餐饮服务;咖啡厅;咖啡厅"}]

    text = generate_narrative({"polyline": scenario_polyline}, "+15", pois=pois)

    assert text == DALIAN_SCENARIO_NARRATIVES[scenario_key("dut", "xinghai")]["+15"]
    assert "某个店" not in text


def test_handwritten_narrative_survives_amap_snapping_the_start_point():
    """高德会把起点吸附到最近的路上。

    实测东港那条真实折线首点是 121.6786,38.9286，而地标 key 是 121.6785,38.9287 ——
    4 位小数差一个单位（约 11 米）。靠折线首尾点匹配会静默退回模板文案，
    所以必须用请求坐标匹配。
    """
    snapped_polyline = "121.6786,38.9286;121.6725,38.9219;121.6701,38.8783"
    pois = [{"name": "肯德基(中南路店)", "type": "餐饮服务;快餐厅;快餐厅"}]

    text = generate_narrative(
        {"polyline": snapped_polyline},
        "+15",
        pois=pois,
        origin=landmark("donggang"),
        destination=landmark("laohutan"),
    )

    assert text == DALIAN_SCENARIO_NARRATIVES[scenario_key("donggang", "laohutan")]["+15"]
    assert "肯德基(中南路店)" not in text


def test_handwritten_narrative_matches_reversed_request():
    text = generate_narrative(
        {"polyline": "121.6701,38.8783;121.6786,38.9286"},
        "+5",
        pois=[{"name": "某个店", "type": "餐饮服务;中餐厅;中餐厅"}],
        origin=landmark("laohutan"),
        destination=landmark("donggang"),
    )

    assert text == DALIAN_SCENARIO_NARRATIVES[scenario_key("donggang", "laohutan")]["+5"]


def test_narrative_falls_back_to_route_endpoints_when_request_coords_absent():
    """兜底路线自带 origin/destination，没有请求坐标时用它们匹配。"""
    text = generate_narrative(
        {
            "origin": landmark("dut"),
            "destination": landmark("xinghai"),
            "polyline": "121.5197,38.8856;121.5839,38.8816",
        },
        "roam",
        pois=[{"name": "某个店", "type": "餐饮服务;中餐厅;中餐厅"}],
    )

    assert text == DALIAN_SCENARIO_NARRATIVES[scenario_key("dut", "xinghai")]["roam"]


def test_narrative_ignores_malformed_request_coordinates():
    text = generate_narrative(
        {"polyline": "120.1,30.2;120.2,30.3"},
        "+5",
        pois=[{"name": "有名字的店", "type": "餐饮服务;咖啡厅;咖啡厅"}],
        origin="not-a-coordinate",
        destination="also,not,valid",
    )

    assert "有名字的店" in text


@pytest.mark.parametrize("mode", ["+5", "+15", "roam"])
def test_single_poi_narrative_does_not_use_plural_phrasing(mode):
    """线上永远只有一个 POI（api.py 传 [chosen["poi"]]），不能说「依次经过」。"""
    pois = [{"name": "老王海鲜馆", "type": "餐饮服务;中餐厅;海鲜酒楼"}]

    text = generate_narrative({"polyline": "120.1,30.2;120.2,30.3"}, mode, pois=pois)

    assert "老王海鲜馆" in text
    assert "依次" not in text
    assert "、" not in text


def test_multiple_pois_still_read_as_a_sequence():
    pois = [
        {"name": "瑞幸咖啡", "type": "餐饮服务;咖啡厅;咖啡厅"},
        {"name": "星海公园", "type": "风景名胜;公园广场"},
    ]

    text = generate_narrative({"polyline": "120.1,30.2;120.2,30.3"}, "+15", pois=pois)

    assert "依次经过" in text
    assert "、" in text
