import os
import requests

DEFAULT_NARRATIVE = "这条路线上有几个值得停留的小地方，适合慢慢走。"
DALIAN_SCENARIO_NARRATIVES = {
    "121.6068,38.9180->121.5854,38.9325": {
        "+5": "海边路线更长，但能顺路看一家安静的小店。",
        "+15": "从大工沿海边走，你会先遇到一间社区咖啡，再顺着海景走到星海。",
        "roam": "把最短路线先放一边，试试先往海边靠，再慢慢往星海走。",
    },
    "121.6281,38.9329->121.6542,38.9337": {
        "+5": "稍微绕一点到东港岸边，视野会比主路好。",
        "+15": "先看东港水面，再看老虎滩方向，整段路更像在海边散步。",
        "roam": "这条推荐更像漫游：码头、海面和老街区会穿插出现。",
    },
    "121.5899,38.9148->121.6075,38.9094": {
        "+5": "只多走几分钟，但可能遇到更适合停留的小店。",
        "+15": "西安路到傅家庄之间，有一小段更适合慢慢逛。",
        "roam": "先慢后远，适合在城区与海岸之间随意切换。",
    },
}


def generate_narrative(route_data: dict, mode: str) -> str:
    base_url = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")

    if not base_url or not model:
        return _dalian_narrative(route_data, mode) or DEFAULT_NARRATIVE

    payload = {
        "model": model,
        "prompt": f"请根据路线数据生成一段探索叙事：{route_data}，模式：{mode}",
        "stream": False,
    }

    try:
        response = requests.post(base_url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "choices" in data and data["choices"]:
            message = data["choices"][0].get("message", {})
            if isinstance(message, dict):
                content = message.get("content")
                if content:
                    return content

        if "response" in data:
            return data["response"]
    except (TimeoutError, requests.RequestException):
        pass

    return _dalian_narrative(route_data, mode) or DEFAULT_NARRATIVE


def _dalian_narrative(route_data: dict, mode: str) -> str | None:
    origin = _normalize(coord=route_data.get("steps", [{}])[0].get("road", ""))
    destination = _normalize(coord=route_data.get("steps", [{}])[-1].get("road", ""))
    if not origin or not destination:
        return None

    route_key = f"{origin}->{destination}"
    reverse_key = f"{destination}->{origin}"

    selected = DALIAN_SCENARIO_NARRATIVES.get(route_key) or DALIAN_SCENARIO_NARRATIVES.get(reverse_key)

    if not selected:
        return None

    selected_mode = mode if mode in selected else "+5"
    return selected.get(selected_mode)


def _normalize(coord: str | None) -> str:
    if not coord:
        return ""
    lng, lat = str(coord).split(",", 1)
    return f"{float(lng):.4f},{float(lat):.4f}"
