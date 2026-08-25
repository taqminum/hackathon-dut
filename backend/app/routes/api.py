from fastapi import APIRouter

router = APIRouter()


@router.post("/route/recommend")
def recommend_route():
    return {"routes": []}
