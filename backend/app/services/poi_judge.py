"""AI 判断沿途候选 POI 是否值得作为「突发亮点」推荐。

现状是沿线搜索会把一批小餐馆、普通商业门店混进候选，即使类别规则
（api._discovery_kind）已经挡掉餐饮大类，小馆子仍可能从兜底/模糊分类
漏进来。这里用 LLM 对候选做一次语义取舍：有意义的景点、公园、展馆、
书店等保留，普通小餐馆、连锁咖啡、便利店等剔除。

任何失败都静默降级：LLM 未配置、超时、响应不可解析时返回 None，
调用方沿用原来的类别规则。AI 把关不能把主推荐接口拖垮。
"""

import hashlib
import json
import os
import threading
import time

import requests

from app.services.narrative import extract_content

POI_JUDGE_TIMEOUT_SECONDS = 5.0
_CACHE_TTL_SECONDS = 600.0
_FAILURE_BACKOFF_SECONDS = 30.0

_cache: dict[str, tuple[float, dict[int, dict]]] = {}
_cache_lock = threading.Lock()
_last_failure_ts = 0.0
_failure_lock = threading.Lock()


def judge_pois(pois: list[dict]) -> dict[int, dict] | None:
    """让 LLM 判断每个候选是否值得推荐，key 是输入列表的下标。

    返回值形如 {index: {"worth": bool, "reason": str}}；任何失败都返回
    None，由调用方决定保持原候选不变。下标映射保证同名 POI 也能对上号。
    """
    global _last_failure_ts
    if not pois:
        return None

    base_url = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")
    api_key = os.getenv("LLM_API_KEY")
    if not base_url or not model:
        return None

    with _failure_lock:
        too_recent = time.monotonic() - _last_failure_ts < _FAILURE_BACKOFF_SECONDS
    if too_recent:
        return None

    cache_key = _cache_key(base_url, model, pois)
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

    try:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        response = requests.post(
            base_url,
            json={"model": model, "prompt": _build_prompt(pois), "stream": False},
            headers=headers,
            timeout=POI_JUDGE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        content = extract_content(response.json())
        verdicts = _parse_verdicts(content, len(pois))
    except Exception:
        with _failure_lock:
            _last_failure_ts = time.monotonic()
        return None

    if verdicts is None:
        with _failure_lock:
            _last_failure_ts = time.monotonic()
        return None

    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), verdicts)
    return verdicts


def split_pois_by_verdict(
    pois: list[dict], verdicts: dict[int, dict] | None
) -> tuple[list[dict], list[dict]]:
    """按 AI 判断分成 (值得保留, 应剔除)。

    verdicts 为 None，或某个 POI 缺失判断时都按「保留」处理 —— 只有模型
    明确说「不值得」的才会被剔除，避免把漏判的景点误杀。
    """
    if not verdicts:
        return list(pois), []

    kept: list[dict] = []
    rejected: list[dict] = []
    for index, poi in enumerate(pois):
        verdict = verdicts.get(index)
        if verdict is not None and not verdict.get("worth"):
            rejected.append(poi)
        else:
            kept.append(poi)
    return kept, rejected


def _build_prompt(pois: list[dict]) -> str:
    lines = []
    for index, poi in enumerate(pois):
        parts = [f"名称：{poi.get('name')}"]
        if poi.get("type"):
            parts.append(f"类别：{poi.get('type')}")
        if poi.get("rating"):
            parts.append(f"评分：{poi.get('rating')}")
        if poi.get("address"):
            parts.append(f"地址：{poi.get('address')}")
        lines.append(f"{index}. " + "；".join(parts))
    candidate_text = "\n".join(lines)
    return (
        "你是大连城市漫步路线的策划。下面是从一条步行路线沿途找到的候选地点。"
        "请判断每个地点是否值得作为「中途突发亮点」推荐给行人绕路去看。\n"
        "判断标准：\n"
        "- 值得：有意义的景点、公园、广场、博物馆、历史遗址、文化场馆、"
        "书店、特色地标、观景点、海滩、纪念地等。\n"
        "- 不值得：普通小餐馆、快餐店、连锁咖啡、奶茶店、便利店、烟酒店、"
        "普通商业门店等，除非它们是著名地标。\n"
        "只输出一个 JSON 数组，不要输出任何其他内容。格式："
        '[{"index": 0, "worth": true, "reason": "一句话理由"}]。\n'
        f"候选地点：\n{candidate_text}"
    )


def _parse_verdicts(content, count: int) -> dict[int, dict] | None:
    if not isinstance(content, str) or not content.strip():
        return None
    text = _strip_code_fence(content)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return None
    if not isinstance(data, list):
        return None

    verdicts: dict[int, dict] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if not (0 <= index < count):
            continue
        reason = item.get("reason")
        verdicts[index] = {
            "worth": bool(item.get("worth")),
            "reason": reason if isinstance(reason, str) else "",
        }
    return verdicts


def _strip_code_fence(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)


def _cache_key(base_url: str, model: str, pois: list[dict]) -> str:
    digest = hashlib.sha1()
    for poi in pois:
        digest.update(
            f"{poi.get('name')}|{poi.get('type')}|{poi.get('location')}|{poi.get('rating')}".encode("utf-8")
        )
    return f"{base_url}|{model}|{digest.hexdigest()}"
