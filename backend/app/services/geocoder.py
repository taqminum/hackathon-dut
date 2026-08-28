import math

import requests


GEOCODING_URL = "https://nominatim.openstreetmap.org/search"


def resolve_location(location: str | None) -> str:
    value = str(location or "").strip()
    if not value:
        raise ValueError("location is empty")

    if "," in value:
        try:
            lng, lat = value.split(",", 1)
            return _format_coord(lng, lat)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid coordinates") from exc

    try:
        response = requests.get(
            GEOCODING_URL,
            params={"q": value, "format": "json", "limit": 1},
            headers={"User-Agent": "hackathon-dut/1.0"},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or not data:
            raise ValueError("empty geocode result")
        return _format_coord(data[0]["lon"], data[0]["lat"])
    except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
        raise ValueError(f"geocode failed: {value}") from exc


def normalize_coordinate(location: str | None) -> str:
    value = str(location or "").strip()
    if "," not in value:
        raise ValueError("invalid coordinates")
    try:
        lng, lat = value.split(",", 1)
        return _format_coord(lng, lat)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid coordinates") from exc


def _format_coord(lng, lat) -> str:
    longitude = float(lng)
    latitude = float(lat)
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise ValueError("invalid coordinates")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("invalid coordinates")
    return f"{longitude:.4f},{latitude:.4f}"
