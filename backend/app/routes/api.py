from fastapi import APIRouter, Body, HTTPException

from app.services.detour_calculator import calculate_detour
from app.services.narrative import generate_narrative
from app.services.poi_explorer import explore_pois_along_route
from app.services.route_engine import get_candidate_routes
from app.services.scorer import SerendipityScorer


router = APIRouter()
scorer = SerendipityScorer()


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

    if not origin or not destination:
        raise HTTPException(status_code=400, detail="缺少起点或终点")

    try:
        baseline_routes = get_candidate_routes(origin, destination, mode)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail=f"路径规划失败：{exc}") from exc

    if not baseline_routes:
        raise HTTPException(status_code=404, detail="未找到可行路线")

    baseline = baseline_routes[0]
    baseline_minutes = round(baseline["duration"] / 60)

    try:
        pois = explore_pois_along_route(origin, destination, ["餐饮", "景点", "购物"], radius=300)
    except Exception:
        pois = []

    candidates = []
    for poi in pois:
        poi_lat_lng = str(poi.get("location", "")).replace(" ", "")
        if not poi_lat_lng:
            continue

        try:
            poi_routes = get_candidate_routes(origin, destination, mode, waypoint=poi_lat_lng)
        except Exception:
            poi_routes = []

        if not poi_routes:
            continue

        candidate_route = poi_routes[0]
        detour_seconds = calculate_detour(baseline["duration"], candidate_route["duration"])
        detour_minutes = round(detour_seconds / 60)

        rating = poi.get("rating", 0)
        if isinstance(rating, str):
            try:
                rating = float(rating)
            except ValueError:
                rating = 0.0

        score = scorer.score(
            detour_minutes=detour_minutes,
            matched_tags=[poi.get("type", "")],
            poi_quality=float(rating) / 5.0,
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
        }

    narrative = generate_narrative(chosen["route"], mode)
    return {
        "baseline_minutes": baseline_minutes,
        "detour_minutes": chosen["detour_minutes"],
        "score": round(chosen["score"], 2),
        "pois": [chosen["poi"]],
        "narrative": narrative,
        "route": chosen["route"],
    }


def _choose_candidate(candidates: list[dict], mode: str) -> dict | None:
    if not candidates:
        return None

    if mode == "+5":
        return min(candidates, key=lambda item: item["detour_minutes"])

    return max(candidates, key=lambda item: item["score"])
