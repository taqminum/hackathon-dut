import math

from fastapi import APIRouter, Body, HTTPException

from app.services.detour_calculator import calculate_detour
from app.services.geocoder import (
    AmbiguousLocationError,
    normalize_coordinate,
    resolve_location,
    search_places,
)
from app.services.narrative import generate_narrative
from app.services.poi_explorer import explore_pois_with_source
from app.services.route_engine import get_candidate_routes
from app.services.scorer import SerendipityScorer


router = APIRouter()
scorer = SerendipityScorer()
MAX_DETOUR_MINUTES = {"+5": 5, "+15": 15}
SUPPORTED_MODES = {"+5", "+15", "roam"}


@router.get("/place/suggest")
def suggest_places(keyword: str, city: str = "大连"):
    preferred_types = ["景点"] if any(token in keyword for token in ("景点", "公园", "广场", "海洋馆")) else []
    return search_places(keyword, city=city, limit=6, preferred_types=preferred_types)


class RecommendRequest:
    origin: str | None = None
    destination: str | None = None
    mode: str = "+5"


@router.post("/route/recommend", response_model=None)
def recommend_route(
    origin: str = Body(..., embed=True),
    destination: str = Body(..., embed=True),
    mode: str = Body("+5", embed=True),
):

    if mode not in SUPPORTED_MODES:
        raise HTTPException(status_code=422, detail="不支持的探索模式")

    if not origin or not destination:
        raise HTTPException(status_code=404, detail="未找到可行路线")

    try:
        place_types = ["景点"] if mode == "roam" else []
        resolved_origin = resolve_location(origin, preferred_types=place_types)
        resolved_destination = resolve_location(destination, preferred_types=place_types)
    except AmbiguousLocationError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "AMBIGUOUS_LOCATION",
                "location": exc.location,
                "candidates": exc.candidates,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未找到可行路线") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail=f"地点解析失败：{exc}") from exc

    if resolved_origin == resolved_destination:
        raise HTTPException(status_code=422, detail="起点和终点不能相同")

    try:
        baseline_routes = get_candidate_routes(resolved_origin, resolved_destination, mode)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未找到可行路线") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail=f"路径规划失败：{exc}") from exc

    if not baseline_routes:
        raise HTTPException(status_code=404, detail="未找到可行路线")

    baseline = baseline_routes[0]
    baseline_minutes = round(baseline["duration"] / 60)

    try:
        poi_types = ["景点"] if mode == "roam" else ["餐饮", "景点", "购物"]
        pois, poi_demo = explore_pois_with_source(
            resolved_origin,
            resolved_destination,
            poi_types,
            radius=300,
        )
    except Exception:
        pois, poi_demo = [], False

    candidates = []
    for poi in pois:
        if not isinstance(poi, dict):
            continue
        try:
            poi_lat_lng = normalize_coordinate(poi.get("location"))
        except ValueError:
            continue

        try:
            poi_routes = get_candidate_routes(
                resolved_origin,
                resolved_destination,
                mode,
                waypoint=poi_lat_lng,
            )
        except Exception:
            poi_routes = []

        if not poi_routes:
            continue

        candidate_route = poi_routes[0]
        detour_seconds = calculate_detour(baseline["duration"], candidate_route["duration"])
        budget = MAX_DETOUR_MINUTES.get(mode)
        if budget is not None and detour_seconds > budget * 60:
            continue
        detour_minutes = round(detour_seconds / 60)

        rating = _normalize_rating(poi.get("rating", 0))

        score = scorer.score(
            detour_minutes=detour_minutes,
            matched_tags=[poi.get("type", "")],
            poi_quality=rating / 5.0,
        )

        candidates.append(
            {
                "poi": poi,
                "route": candidate_route,
                "detour_minutes": detour_minutes,
                "score": score,
            }
        )

    chosen = _choose_candidate(candidates, mode)

    if not chosen:
        narrative = generate_narrative(baseline, mode)
        return {
            "baseline_minutes": baseline_minutes,
            "detour_minutes": 0,
            "score": 0,
            "pois": [],
            "narrative": narrative,
            "route": baseline,
            "poi_demo_mode": poi_demo,
        }

    narrative = generate_narrative(chosen["route"], mode)
    return {
        "baseline_minutes": baseline_minutes,
        "detour_minutes": chosen["detour_minutes"],
        "score": round(chosen["score"], 2),
        "pois": [chosen["poi"]],
        "narrative": narrative,
        "route": chosen["route"],
        "poi_demo_mode": poi_demo,
    }


def _not_implemented(feature: str):
    raise HTTPException(
        status_code=501,
        detail={
            "code": "NOT_IMPLEMENTED",
            "message": f"{feature}接口尚未实现",
        },
    )


@router.post("/trip/save")
def save_trip():
    _not_implemented("收藏路线")


@router.get("/trip/list")
def list_trips():
    _not_implemented("收藏列表")


@router.post("/feedback")
def send_feedback():
    _not_implemented("路线反馈")


@router.get("/poi/{poi_id}")
def poi_detail(poi_id: str):
    _not_implemented("POI 详情")


def _choose_candidate(candidates: list[dict], mode: str) -> dict | None:
    if not candidates:
        return None

    if mode == "+5":
        return min(candidates, key=lambda item: item["detour_minutes"])

    return max(candidates, key=lambda item: item["score"])


def _normalize_rating(value) -> float:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(rating):
        return 0.0
    return min(5.0, max(0.0, rating))
