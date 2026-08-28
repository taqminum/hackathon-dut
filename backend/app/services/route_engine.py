import os
from math import asin, cos, radians, sin, sqrt

import requests

WALKING_URL = "https://restapi.amap.com/v3/direction/walking"

DALIAN_SCENARIOS = {
    "121.6068,38.9180->121.5854,38.9325": {
        "base_distance": 2100,
        "base_duration": 1260,
        "extra_distance": {None: 0, "+5": 240, "+15": 520, "roam": 780},
        "extra_duration": {None: 0, "+5": 140, "+15": 300, "roam": 460},
        "polyline": [
            "121.6068,38.9180",
            "121.6014,38.9222",
            "121.5958,38.9265",
            "121.5914,38.9292",
            "121.5854,38.9325",
        ],
    },
    "121.6281,38.9329->121.6542,38.9337": {
        "base_distance": 2800,
        "base_duration": 1560,
        "extra_distance": {None: 0, "+5": 260, "+15": 620, "roam": 980},
        "extra_duration": {None: 0, "+5": 160, "+15": 360, "roam": 580},
        "polyline": [
            "121.6281,38.9329",
            "121.6352,38.9333",
            "121.6426,38.9335",
            "121.6489,38.9336",
            "121.6542,38.9337",
        ],
    },
    "121.5899,38.9148->121.6075,38.9094": {
        "base_distance": 2300,
        "base_duration": 1380,
        "extra_distance": {None: 0, "+5": 220, "+15": 460, "roam": 720},
        "extra_duration": {None: 0, "+5": 130, "+15": 280, "roam": 420},
        "polyline": [
            "121.5899,38.9148",
            "121.5951,38.9132",
            "121.6004,38.9116",
            "121.6042,38.9104",
            "121.6075,38.9094",
        ],
    },
}


def get_candidate_routes(origin: str, destination: str, mode: str, waypoint: str | None = None) -> list[dict]:
    params = {
        "origin": origin,
        "destination": destination,
        "strategy": 0,
    }

    if waypoint:
        params["waypoint"] = waypoint

    has_key = bool(os.getenv("AMAP_KEY"))
    if has_key:
        params["key"] = os.getenv("AMAP_KEY")

    if has_key:
        try:
            response = requests.get(WALKING_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            route_data = data.get("route") if isinstance(data, dict) else None
            paths = route_data.get("paths", []) if isinstance(route_data, dict) else []
            if isinstance(paths, list):
                routes = []
                for path in paths:
                    if not isinstance(path, dict):
                        continue
                    try:
                        distance = int(path.get("distance", 0))
                        duration = int(path.get("duration", 0))
                    except (TypeError, ValueError):
                        continue
                    if distance <= 0 or duration <= 0:
                        continue
                    routes.append(
                        {
                            "distance": distance,
                            "duration": duration,
                            "steps": path.get("steps", []),
                            "polyline": path.get("polyline", ""),
                        }
                    )
                if routes:
                    return routes
        except (requests.RequestException, TypeError, ValueError, AttributeError):
            pass

    return [_build_fallback_route(origin, destination, mode, waypoint)]


def _build_fallback_route(origin: str, destination: str, mode: str, waypoint: str | None) -> dict:
    scenario = _select_dalian_scenario(origin, destination)
    start = _parse_lng_lat(origin)
    end = _parse_lng_lat(destination)
    mid = _parse_lng_lat(waypoint) if waypoint else None

    if scenario:
        base_distance = scenario["base_distance"]
        base_duration = scenario["base_duration"]
    else:
        direct_distance = _haversine_meters(start, end)
        if direct_distance > 50_000:
            raise ValueError("fallback route is too long")

        route_distance = direct_distance
        if mid:
            route_distance = _haversine_meters(start, mid) + _haversine_meters(mid, end)
        base_distance = max(1, round(route_distance * 1.3))
        base_duration = max(1, round(base_distance / 1.35))

    if waypoint and scenario:
        effective_mode = mode or "+15"
        extra_distance = (scenario or {}).get("extra_distance") or {}
        extra_duration = (scenario or {}).get("extra_duration") or {}
        base_distance += extra_distance.get(effective_mode, 220)
        base_duration += extra_duration.get(effective_mode, 120)

    points = [start]
    if mid:
        points.append(mid)
    points.append(end)

    if scenario:
        scenario_points = list(scenario["polyline"])
        if mid:
            waypoint_index = 2
            if waypoint_index <= len(scenario_points):
                scenario_points.insert(waypoint_index, [mid[0], mid[1]])

        polyline = ";".join(f"{float(lng):.4f},{float(lat):.4f}" for lng, lat in scenario_points)
    else:
        polyline = ";".join(f"{lng:.4f},{lat:.4f}" for lng, lat in points)

    return {
        "origin": origin,
        "destination": destination,
        "demo_mode": scenario is not None,
        "distance": base_distance,
        "duration": base_duration,
        "steps": [
            {
                "instruction": "按推荐路线行走",
                "road": origin,
                "distance": str(base_distance),
                "duration": str(base_duration),
            }
        ],
        "polyline": polyline,
    }


def _parse_lng_lat(coord: str | None) -> tuple[float, float]:
    if not coord:
        return 116.407526, 39.90403
    lng, lat = str(coord).split(",", 1)
    return float(lng), float(lat)


def _haversine_meters(start: tuple[float, float], end: tuple[float, float]) -> float:
    start_lng, start_lat = map(radians, start)
    end_lng, end_lat = map(radians, end)
    delta_lng = end_lng - start_lng
    delta_lat = end_lat - start_lat
    value = sin(delta_lat / 2) ** 2 + cos(start_lat) * cos(end_lat) * sin(delta_lng / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(value))


def _try_parse_coord(coord: str | None) -> str | None:
    if not coord:
        return None
    try:
        lng, lat = str(coord).split(",", 1)
        return f"{float(lng):.4f},{float(lat):.4f}"
    except ValueError:
        return None


def _select_dalian_scenario(origin: str, destination: str) -> dict | None:
    direct_key = f"{_normalize(origin)}->{_normalize(destination)}"
    reverse_key = f"{_normalize(destination)}->{_normalize(origin)}"

    selected = DALIAN_SCENARIOS.get(direct_key)
    reversed_route = False
    if not selected:
        selected = DALIAN_SCENARIOS.get(reverse_key)
        reversed_route = selected is not None

    if not selected:
        return None

    normalized = selected.copy()
    normalized["polyline"] = [
        list(map(float, point.split(","))) for point in selected["polyline"]
    ]
    if reversed_route:
        normalized["polyline"].reverse()
    return normalized


def _normalize(coord: str | None) -> str:
    if not coord:
        return ""
    lng, lat = str(coord).split(",", 1)
    return f"{float(lng):.4f},{float(lat):.4f}"
