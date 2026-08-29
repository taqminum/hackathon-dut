import os
import requests

DEFAULT_NARRATIVE = "这条路线上有几个值得停留的小地方，适合慢慢走。"
DALIAN_SCENARIO_NARRATIVES = {
    "121.6068,38.9180->121.5854,38.9325": {
        "+5": "海边路线更长，但能顺路看一家安静的小店。",
        "+15": "从大工沿海边走，你会先遇到一间社区咖啡，再顺着海景走到星海。",
        "roam": "把最短路线先放一边，试试先往海边靠，再慢慢往星海走。",
    },
    "121.6753,38.9307->121.6746,38.8784": {
        "+5": "从东港音乐喷泉广场出发，沿海岸线向南走到老虎滩。",
        "+15": "这段路会把东港海面和老虎滩一带串起来，更适合慢慢走。",
        "roam": "从东港音乐喷泉广场到老虎滩海洋公园，路线重点放在海边视野和沿途停留感。",
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
    polyline = route_data.get("polyline", "")
    coordinates = [point for point in str(polyline).split(";") if point]

    if len(coordinates) < 2:
        return None

    origin = _normalize(coord=coordinates[0])
    destination = _normalize(coord=coordinates[-1])
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
