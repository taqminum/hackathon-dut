import os
import re

import requests

from app.services.dalian import scenario_key

DEFAULT_NARRATIVE = "这条路线上有几个值得停留的小地方，适合慢慢走。"
# key 与 route_engine.DALIAN_SCENARIOS / poi_explorer.DALIAN_POI_SCENARIOS 共用
# dalian.scenario_key：三张表一起改，不会只改一张导致叙事悄悄退回默认文案。
DALIAN_SCENARIO_NARRATIVES = {
    scenario_key("dut", "xinghai"): {
        "+5": "沿软件园走，顺路能拐进一家咖啡馆，几分钟的代价换一段慢下来的时间。",
        "+15": "从大工出发先过软件园，路边有咖啡可以带一杯，再一路向南走到星海广场。",
        "roam": "把最短路线放一边：先沿软件园慢慢走，再顺着海的方向靠近星海。",
    },
    scenario_key("donggang", "laohutan"): {
        "+5": "沿着东港海岸往南，绕进炮台山遗址看一眼，视野比主路开阔。",
        "+15": "从东港沿海岸往南，多走一段绕进炮台山遗址，视野更开阔，最后走到老虎滩的海边。",
        "roam": "这条更像漫游：商务区、炮台山遗址、东方水城的书店和海风会依次出现。",
    },
    scenario_key("xianlu", "fujiazhuang"): {
        "+5": "只多走几分钟，中途会拐进一家海边咖啡馆。",
        "+15": "西安路往南穿过星海广场再折向跨海大桥方向，中段可以停在观景点看海，终点是傅家庄的海边。",
        "roam": "先在城区绕一段，再顺着海岸走向银沙滩公园，快慢自己切换。",
    },
}


def generate_narrative(
    route_data: dict,
    mode: str,
    pois: list | None = None,
    origin: str | None = None,
    destination: str | None = None,
    allow_demo_narrative: bool = True,
) -> str:
    """这条路线的一句话叙事。

    优先级：LLM -> 手写的演示文案 -> 用真实 POI 填的模板 -> 通用兜底句。
    模板那一层是关键：拿到了真实店名却还说「有几个值得停留的小地方」，
    等于把这个产品最有说服力的部分丢掉了。

    `origin` / `destination` 传的是**用户请求的**坐标。命中手写文案要靠它们，
    不能只靠折线首尾点：高德会把起点吸附到最近的路上，实测东港那条返回的首点
    是 121.6786,38.9286，而地标 key 是 121.6785,38.9287 —— 4 位小数差一个单位
    （约 11 米）就匹配不上，手写文案会静默退回模板。
    """
    base_url = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")
    api_key = os.getenv("LLM_API_KEY")

    if not base_url or not model:
        return _fallback_narrative(route_data, mode, pois, origin, destination, allow_demo_narrative)

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _build_prompt(route_data, mode, pois)}],
        "stream": False,
    }

    try:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        response = requests.post(base_url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        content = extract_content(response.json())
        if content:
            return _clean_llm_narrative(content)
    # 响应是合法 JSON 但结构不对时，取字段会抛 AttributeError / TypeError /
    # KeyError / IndexError。叙事是锦上添花，绝不能因为它让主接口 500，
    # 所以这里连结构异常一起吃掉，落到兜底文案。
    except (TimeoutError, requests.RequestException, AttributeError, TypeError, KeyError, IndexError, ValueError):
        pass

    return _fallback_narrative(route_data, mode, pois, origin, destination, allow_demo_narrative)


def _fallback_narrative(
    route_data: dict,
    mode: str,
    pois: list | None,
    origin: str | None = None,
    destination: str | None = None,
    allow_demo_narrative: bool = True,
) -> str:
    # 手写文案只属于离线演示数据；真实高德路线必须以实际返回的地点生成文案。
    return (
        (_dalian_narrative(route_data, mode, origin, destination) if allow_demo_narrative else None)
        or _template_narrative(pois, mode)
        or DEFAULT_NARRATIVE
    )


# 一屏内读完的短文案。模型偶尔无视 prompt 输出一整篇攻略，这里是最后一道闸。
MAX_NARRATIVE_CHARS = 160

# 同一模式的三种中文说法，prompt 里用自然语言而不是 +5 这种内部代号。
MODE_LABELS = {"+5": "只愿意稍微绕路", "+15": "愿意多绕一段", "roam": "不赶时间随便走走"}


def _build_prompt(route_data: dict, mode: str, pois: list | None) -> str:
    """组 LLM prompt：只传精简的真实信息，并明确要短、口语化、不编造。

    之前把整段 route JSON 丢给模型，它照抄出又长又空泛的营销文；这里换成
    距离/时长/模式/亮点名，让模型只能在这些事实上做文章。
    """
    names = [name for name, _ in _poi_highlights(pois)]
    facts = []
    distance = route_data.get("distance")
    duration = route_data.get("duration")
    if isinstance(distance, (int, float)) and distance > 0:
        facts.append(f"全程约{distance / 1000:.1f}公里")
    if isinstance(duration, (int, float)) and duration > 0:
        facts.append(f"步行约{round(duration / 60)}分钟")
    facts.append(MODE_LABELS.get(mode, mode))
    if names:
        facts.append("沿途亮点：" + "、".join(names))

    return (
        "用一到两句口语化的中文给这条步行路线写推荐语，语气像本地朋友随口介绍，"
        "不要写成广告或旅游攻略。"
        f"路线信息：{'，'.join(facts)}。"
        "只能提到上面出现的真实地点，禁止编造店名、人群、噪音、营业时间或价格；"
        "不要标题、列表、emoji，也不要“好的”“以下”这类开场白。直接输出正文。"
    )


def _clean_llm_narrative(text: str) -> str:
    """对 LLM 输出做最后一道轻清理，不重写内容。

    去掉开头寒暄（「好的，以下…」）、markdown 列表符号，并把文案压进
    MAX_NARRATIVE_CHARS 内（在句号处截断），防止模型无视 prompt 输出长文。
    """
    text = text.strip()
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"^(好的[，,：:\s]*|以下是|以下为|以下)[，,：:\s]*", "", text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("-", "*", ">", "#")):
            stripped = stripped.lstrip("-*>#").strip()
        elif re.match(r"^\d+[\.、]", stripped):
            stripped = re.sub(r"^\d+[\.、]", "", stripped).strip()
        if stripped:
            lines.append(stripped)
    # 「为您推荐的路线：」这类冒号结尾的前导句整行丢掉，不是内容。
    if len(lines) > 1 and lines[0].rstrip().endswith(("：", ":")):
        lines = lines[1:]
    cleaned = " ".join(lines)
    if len(cleaned) <= MAX_NARRATIVE_CHARS:
        return cleaned
    cut = cleaned[:MAX_NARRATIVE_CHARS]
    boundary = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"))
    return cut[: boundary + 1] if boundary > 0 else cut


def extract_content(data) -> str | None:
    """从 LLM 响应里取正文。兼容 OpenAI 风格的 choices 和 Ollama 风格的 response。

    每一层都要判类型：实测 `choices` 可能是字符串、元素可能是 null，
    直接 `data["choices"][0].get(...)` 会抛异常。
    """
    if not isinstance(data, dict):
        return None

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content
            # 有些实现把正文直接放在 choices[0].text
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text

    response_text = data.get("response")
    if isinstance(response_text, str) and response_text.strip():
        return response_text

    return None


def _dalian_narrative(
    route_data: dict,
    mode: str,
    origin: str | None = None,
    destination: str | None = None,
) -> str | None:
    start, end = _match_endpoints(route_data, origin, destination)
    if not start or not end:
        return None

    route_key = f"{start}->{end}"
    reverse_key = f"{end}->{start}"

    selected = DALIAN_SCENARIO_NARRATIVES.get(route_key) or DALIAN_SCENARIO_NARRATIVES.get(reverse_key)

    if not selected:
        return None

    selected_mode = mode if mode in selected else "+5"
    return selected.get(selected_mode)


def _match_endpoints(
    route_data: dict,
    origin: str | None,
    destination: str | None,
) -> tuple[str, str]:
    """拿来匹配手写文案的起终点，4 位小数。

    优先用调用方给的请求坐标；没给时退回路线自带的 origin/destination
    （兜底路线有这两个字段），最后才用折线首尾点。
    """
    candidates = (
        (origin, destination),
        (route_data.get("origin"), route_data.get("destination")),
    )
    for start, end in candidates:
        normalized_start, normalized_end = _normalize(start), _normalize(end)
        if normalized_start and normalized_end:
            return normalized_start, normalized_end

    coordinates = [point for point in str(route_data.get("polyline", "")).split(";") if point]
    if len(coordinates) < 2:
        return "", ""
    return _normalize(coordinates[0]), _normalize(coordinates[-1])


def _normalize(coord: str | None) -> str:
    if not coord:
        return ""
    try:
        lng, lat = str(coord).split(",", 1)
        return f"{float(lng):.4f},{float(lat):.4f}"
    except (TypeError, ValueError):
        return ""


# 按模式给的句式。真实店名和类别填进去，比通用兜底句具体得多。
#
# 每个模式给单个和多个两种句式：api.py 只把**被选中的那一个** POI 交给叙事
# （`pois=[chosen["poi"]]`），所以真实数据下永远只有一个名字。「依次经过 A、B」
# 这种复数句式在线上根本不可达，拿一个名字去填会读成「会依次经过某家店」。
#
# 为什么不把沿线所有 POI 都传进来凑复数：那些点并不在最终路线上，说「顺路会
# 经过」就是假的 —— 卖「偶遇」的产品不能在这句话上注水。
MODE_TEMPLATES = {
    "+5": {
        "one": "只多花几分钟，顺路就能拐去{highlight}，值得看一眼。",
        "many": "只多花几分钟，顺路会经过{highlight}，值得拐进去看一眼。",
    },
    "+15": {
        "one": "这条路会带你去{highlight}，多走一段换来的东西比时间值钱。",
        "many": "这条路上会依次经过{highlight}，多走一段换来的东西比时间值钱。",
    },
    "roam": {
        "one": "把最短路线放一边：慢慢走去{highlight}，快慢自己决定。",
        "many": "把最短路线放一边：慢慢走过{highlight}，快慢自己决定。",
    },
}

# 高德 type 串（`餐饮服务;咖啡厅;咖啡厅`）太技术，转成人话再进文案。
TYPE_LABELS = (
    ("咖啡", "咖啡馆"),
    ("海鲜", "海鲜馆子"),
    ("烧烤", "烧烤店"),
    ("面包", "面包店"),
    ("甜品", "甜品店"),
    ("茶", "茶饮店"),
    ("快餐", "小馆"),
    ("中餐", "馆子"),
    ("外国餐", "餐厅"),
    ("餐饮", "吃饭的地方"),
    ("公园", "公园"),
    ("广场", "广场"),
    ("风景", "景点"),
    ("博物", "博物馆"),
    ("书店", "书店"),
    ("购物", "店"),
)


def _template_narrative(pois: list | None, mode: str) -> str | None:
    """用真实 POI 填模板。没有可用 POI 时返回 None，交给通用兜底句。"""
    highlights = _poi_highlights(pois)
    if not highlights:
        return None

    phrases = [f"{name}（{label}）" if label else name for name, label in highlights]
    templates = MODE_TEMPLATES.get(mode) or MODE_TEMPLATES["+5"]
    template = templates["one"] if len(phrases) == 1 else templates["many"]
    return template.format(highlight="、".join(phrases))


def _poi_highlights(pois: list | None, limit: int = 2) -> list[tuple[str, str]]:
    """取前若干个可用 POI 的 (店名, 人话类别)。脏数据一律跳过。"""
    highlights: list[tuple[str, str]] = []
    seen: set[str] = set()

    for poi in pois or []:
        if not isinstance(poi, dict):
            continue
        name = poi.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        if name in seen:
            continue
        seen.add(name)
        highlights.append((name, _type_label(poi.get("type"))))
        if len(highlights) >= limit:
            break

    return highlights


def _type_label(poi_type) -> str:
    if not isinstance(poi_type, str):
        return ""
    for keyword, label in TYPE_LABELS:
        if keyword in poi_type:
            return label
    return ""
