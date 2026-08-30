import json
from unittest.mock import patch

import pytest

from app.services.poi_judge import judge_pois, split_pois_by_verdict


def _poi(name, type_="风景名胜;公园广场", rating="4.5", location="120.1350,30.2570"):
    return {
        "name": name,
        "type": type_,
        "typecode": "110200",
        "rating": rating,
        "location": location,
        "source": "amap",
    }


@pytest.fixture(autouse=True)
def reset_poi_judge_state():
    """每个用例都清掉 AI 把关的模块级缓存和失败退避，避免跨用例泄漏。"""
    import app.services.poi_judge as poi_judge

    with poi_judge._cache_lock:
        poi_judge._cache.clear()
    with poi_judge._failure_lock:
        poi_judge._last_failure_ts = 0.0
    yield
    with poi_judge._cache_lock:
        poi_judge._cache.clear()
    with poi_judge._failure_lock:
        poi_judge._last_failure_ts = 0.0


def test_split_drops_rejected_dining_and_keeps_scenic():
    pois = [
        _poi("星海公园"),
        _poi("老王海鲜烧烤", type_="风景名胜;海鲜酒楼"),
        _poi("大连现代博物馆", type_="科教文化服务;博物馆"),
    ]
    verdicts = {
        0: {"worth": True, "reason": "公园值得逛"},
        1: {"worth": False, "reason": "普通海鲜小馆"},
        2: {"worth": True, "reason": "博物馆值得看"},
    }

    kept, rejected = split_pois_by_verdict(pois, verdicts)

    assert [p["name"] for p in kept] == ["星海公园", "大连现代博物馆"]
    assert [p["name"] for p in rejected] == ["老王海鲜烧烤"]


def test_split_keeps_everything_when_verdicts_missing():
    pois = [_poi("星海公园"), _poi("老王海鲜烧烤", type_="风景名胜;海鲜酒楼")]

    kept, rejected = split_pois_by_verdict(pois, None)

    assert len(kept) == 2
    assert rejected == []


def test_split_keeps_unjudged_poi_to_avoid_murdering_scenic_spots():
    pois = [_poi("星海公园"), _poi("大连现代博物馆", type_="科教文化服务;博物馆")]
    # 模型只回答了 0，没提到 1 —— 漏判默认保留
    verdicts = {0: {"worth": True, "reason": ""}}

    kept, rejected = split_pois_by_verdict(pois, verdicts)

    assert len(kept) == 2
    assert rejected == []


def test_judge_pois_parses_llm_verdicts():
    payload = [
        {"index": 0, "worth": True, "reason": "公园值得逛"},
        {"index": 1, "worth": False, "reason": "普通小馆"},
    ]
    with patch("app.services.poi_judge.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]
        }
        with patch.dict("os.environ", {"LLM_API_BASE": "http://localhost", "LLM_MODEL": "demo"}):
            verdicts = judge_pois(
                [_poi("星海公园"), _poi("老王海鲜烧烤", type_="风景名胜;海鲜酒楼")]
            )

    assert verdicts == {
        0: {"worth": True, "reason": "公园值得逛"},
        1: {"worth": False, "reason": "普通小馆"},
    }
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["model"] == "demo"
    assert "老王海鲜烧烤" in kwargs["json"]["messages"][0]["content"]


def test_judge_pois_sends_bearer_token_when_key_configured():
    with patch("app.services.poi_judge.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": '[{"index": 0, "worth": true, "reason": "ok"}]'}}]
        }
        with patch.dict(
            "os.environ",
            {
                "LLM_API_BASE": "http://localhost",
                "LLM_API_KEY": "sk-test-123",
                "LLM_MODEL": "demo",
            },
        ):
            judge_pois([_poi("星海公园")])

    _, kwargs = mock_post.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer sk-test-123"}


def test_judge_pois_accepts_code_fenced_json():
    content = '```json\n[{"index": 0, "worth": true, "reason": "ok"}]\n```'
    with patch("app.services.poi_judge.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"response": content}
        with patch.dict("os.environ", {"LLM_API_BASE": "http://localhost", "LLM_MODEL": "demo"}):
            verdicts = judge_pois([_poi("星海公园")])

    assert verdicts == {0: {"worth": True, "reason": "ok"}}


def test_judge_pois_returns_none_without_llm_config():
    assert judge_pois([_poi("星海公园")]) is None


def test_judge_pois_returns_none_on_request_failure():
    with patch("app.services.poi_judge.requests.post", side_effect=TimeoutError):
        with patch.dict("os.environ", {"LLM_API_BASE": "http://localhost", "LLM_MODEL": "demo"}):
            assert judge_pois([_poi("星海公园")]) is None


def test_judge_pois_returns_none_on_unparsable_response():
    with patch("app.services.poi_judge.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"choices": [{"message": {"content": "不是 JSON"}}]}
        with patch.dict("os.environ", {"LLM_API_BASE": "http://localhost", "LLM_MODEL": "demo"}):
            assert judge_pois([_poi("星海公园")]) is None


def test_judge_pois_backs_off_after_failure():
    with patch("app.services.poi_judge.requests.post", side_effect=TimeoutError):
        with patch.dict("os.environ", {"LLM_API_BASE": "http://localhost", "LLM_MODEL": "demo"}):
            assert judge_pois([_poi("星海公园")]) is None
    # 30 秒退避期内不再发请求
    with patch("app.services.poi_judge.requests.post") as mock_post:
        with patch.dict("os.environ", {"LLM_API_BASE": "http://localhost", "LLM_MODEL": "demo"}):
            assert judge_pois([_poi("星海公园")]) is None
    mock_post.assert_not_called()


def test_recommend_drops_small_restaurant_via_ai_judge(client, monkeypatch):
    """端到端：海鲜烧烤店名字含「海」能穿过类别规则，AI 把关负责把它剔掉。"""
    park = _poi("星海公园")
    seafood = _poi("老王海鲜烧烤", type_="风景名胜;海鲜酒楼")

    def fake_routes(origin, destination, mode, waypoint=None):
        return [{
            "origin": origin,
            "destination": destination,
            "source": "amap",
            "distance": 1000,
            "duration": 400 if waypoint else 300,
            "steps": [],
            "polyline": f"{origin};{waypoint or destination};{destination}",
        }]

    def fake_judge(pool):
        return {
            i: {
                "worth": p["name"] != "老王海鲜烧烤",
                "reason": "普通海鲜小馆" if p["name"] == "老王海鲜烧烤" else "值得看",
            }
            for i, p in enumerate(pool)
        }

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *a, **k: [park, seafood])
    monkeypatch.setattr("app.routes.api.judge_pois", fake_judge)

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "+5"},
    )

    assert response.status_code == 200
    body = response.json()
    names = [p["name"] for p in body["pois"]]
    assert "老王海鲜烧烤" not in names
    assert "星海公园" in names


def test_recommend_keeps_all_when_ai_judge_fails(client, monkeypatch):
    """LLM 不可用时 judge_pois 返回 None，小馆子按原规则保留，接口行为不变。"""
    park = _poi("星海公园")
    seafood = _poi("老王海鲜烧烤", type_="风景名胜;海鲜酒楼", location="120.1360,30.2570")

    def fake_routes(origin, destination, mode, waypoint=None):
        return [{
            "origin": origin,
            "destination": destination,
            "source": "amap",
            "distance": 1000,
            # 公园绕行 1200s 超 +15 预算被丢弃，海鲜店 301s 在预算内成为唯一候选
            "duration": 301 if waypoint == seafood["location"] else 1200 if waypoint else 300,
            "steps": [],
            "polyline": f"{origin};{waypoint or destination};{destination}",
        }]

    monkeypatch.setattr("app.routes.api.resolve_location", lambda value: value)
    monkeypatch.setattr("app.routes.api.get_candidate_routes", fake_routes)
    monkeypatch.setattr("app.routes.api.explore_pois_along_route", lambda *a, **k: [park, seafood])
    monkeypatch.setattr("app.routes.api.judge_pois", lambda pool: None)

    response = client.post(
        "/api/route/recommend",
        json={"origin": "120.1300,30.2590", "destination": "120.1400,30.2550", "mode": "+15"},
    )

    assert response.status_code == 200
    assert any(p["name"] == "老王海鲜烧烤" for p in response.json()["pois"])
