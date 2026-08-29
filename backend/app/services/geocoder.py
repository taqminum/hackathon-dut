import difflib
import math
import os
import re

import requests


GEOCODING_URL = "https://nominatim.openstreetmap.org/search"
PLACE_SEARCH_URL = "https://restapi.amap.com/v3/place/text"


class AmbiguousLocationError(ValueError):
    def __init__(self, location: str, candidates: list[dict]):
        super().__init__(f"ambiguous location: {location}")
        self.location = location
        self.candidates = candidates


def resolve_location(location: str | None, preferred_types: list[str] | None = None) -> str:
    value = str(location or "").strip()
    if not value:
        raise ValueError("location is empty")

    if "," in value:
        try:
            lng, lat = value.split(",", 1)
            return _format_coord(lng, lat)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid coordinates") from exc

    candidates = search_places(value, preferred_types=preferred_types or [])
    if not candidates:
        raise ValueError(f"geocode failed: {value}")

    preference = _scenario_preference(value)
    if preference:
        return preference

    if _needs_confirmation(candidates):
        raise AmbiguousLocationError(value, candidates)
    return candidates[0]["location"]


def search_places(
    keyword: str,
    city: str = "大连",
    limit: int = 6,
    preferred_types: list[str] | None = None,
) -> list[dict]:
    value = str(keyword or "").strip()
    if not value:
        return []

    preferred_types = preferred_types or []

    key = os.getenv("AMAP_KEY")
    if key:
        try:
            response = requests.get(
                PLACE_SEARCH_URL,
                params={
                    "key": key,
                    "keywords": value,
                    "city": city,
                    "offset": max(1, min(int(limit), 20)),
                    "page": 1,
                    "extensions": "base",
                },
                timeout=8,
            )
            response.raise_for_status()
            data = response.json()
            pois = data.get("pois", []) if isinstance(data, dict) else []
            ranked = _rank_candidates(value, pois, preferred_types)
            if ranked:
                return ranked[: max(1, min(int(limit), 20))]
        except Exception:
            pass

    return _nominatim_candidates(value, city, limit)


def normalize_coordinate(location: str | None) -> str:
    value = str(location or "").strip()
    if "," not in value:
        raise ValueError("invalid coordinates")
    try:
        lng, lat = value.split(",", 1)
        return _format_coord(lng, lat)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid coordinates") from exc


def _nominatim_candidates(keyword: str, city: str, limit: int) -> list[dict]:
    try:
        response = requests.get(
            GEOCODING_URL,
            params={"q": keyword, "format": "json", "limit": max(1, min(int(limit), 6))},
            headers={"User-Agent": "hackathon-dut/1.0"},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        candidates = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict) or "lon" not in item or "lat" not in item:
                continue
            candidates.append(
                {
                    "name": item.get("display_name", keyword).split(",", 1)[0],
                    "address": item.get("display_name", ""),
                    "location": _format_coord(item["lon"], item["lat"]),
                    "type": item.get("type", ""),
                    "coordinate_system": "wgs84",
                    "confidence": 0.5,
                }
            )
        return candidates
    except (KeyError, TypeError, ValueError, requests.RequestException):
        return []


def _rank_candidates(keyword: str, pois: list, preferred_types: list[str]) -> list[dict]:
    ranked = []
    for poi in pois:
        if not isinstance(poi, dict) or not poi.get("location"):
            continue
        try:
            location = normalize_coordinate(poi["location"])
        except ValueError:
            continue

        name = str(poi.get("name") or "").strip()
        address = str(poi.get("address") or poi.get("district") or "").strip()
        poi_type = str(poi.get("type") or "").strip()
        score = _candidate_score(keyword, name, address, poi_type, preferred_types)
        ranked.append(
            {
                "name": name or keyword,
                "address": address,
                "location": location,
                "type": poi_type,
                "coordinate_system": "gcj02",
                "confidence": round(score, 3),
            }
        )
    return sorted(ranked, key=lambda item: (-item["confidence"], item["name"]))


def _candidate_score(
    keyword: str,
    name: str,
    address: str,
    poi_type: str,
    preferred_types: list[str],
) -> float:
    query = _compact(keyword)
    candidate = _compact(name)
    score = 0.35
    if candidate == query:
        score += 0.32
    elif query and query in candidate:
        score += 0.24
    if any(_type_matches(poi_type, value) for value in preferred_types):
        score += 0.25
    if any(token in poi_type for token in ("地名地址信息", "交通设施服务")):
        score -= 0.12
    if address and "大连" in address:
        score += 0.04
    if len(name) > len(keyword):
        score += min(0.12, (len(name) - len(keyword)) * 0.015)
    return max(0.0, min(0.99, score))


def _type_matches(poi_type: str, preferred: str) -> bool:
    if preferred == "景点":
        return any(token in poi_type for token in ("风景名胜", "公园广场"))
    return preferred in poi_type


def _needs_confirmation(candidates: list[dict]) -> bool:
    if len(candidates) < 2:
        return False
    top = candidates[0].get("confidence", 0)
    second = candidates[1].get("confidence", 0)
    if top < 0.78 or top - second < 0.08:
        return True
    return bool(_looks_like_same_place(candidates[0], candidates[1]))


_SCENARIO_POI_NAMES = {
    "东港": "东港音乐喷泉广场",
    "老虎滩": "老虎滩海洋公园",
}


def _scenario_preference(value: str) -> str | None:
    compact_value = _compact(value)
    if compact_value in _SCENARIO_POI_NAMES:
        preference = _SCENARIO_POI_NAMES[compact_value]
        candidates = search_places(preference, limit=2, preferred_types=["景点"])
        if candidates:
            return candidates[0]["location"]
    return None


def _looks_like_same_place(alpha: dict, beta: dict) -> bool:
    alpha_name = _compact(alpha.get("name", ""))
    beta_name = _compact(beta.get("name", ""))
    if not alpha_name or not beta_name:
        return False
    if alpha_name == beta_name:
        return True

    base_query = _compact(_SCENARIO_POI_NAMES.get(alpha_name, alpha_name))
    if base_query and alpha_name in base_query and beta_name in base_query:
        return True
    if alpha_name in beta_name or beta_name in alpha_name:
        return True

    similarity = difflib.SequenceMatcher(None, alpha_name, beta_name).ratio()
    return similarity >= 0.72


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _format_coord(lng, lat) -> str:
    longitude = float(lng)
    latitude = float(lat)
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise ValueError("invalid coordinates")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("invalid coordinates")
    return f"{longitude:.4f},{latitude:.4f}"
