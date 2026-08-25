from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from app.routes import api
import os
from starlette.middleware.base import BaseHTTPMiddleware


class FrontendFallbackMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if response.status_code != 404:
            return response

        path = request.url.path
        if path.startswith("/api") or path == "/health":
            return response

        if os.path.isdir(frontend_dist):
            index_path = os.path.join(frontend_dist, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
        return response

app = FastAPI(title="Serendipity Navigation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(FrontendFallbackMiddleware)

app.include_router(api.router, prefix="/api")

frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "webapp", "dist")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
async def serve_index():
    index_path = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "frontend not built"}


@app.get("/{full_path:path}")
async def serve_frontend(request, full_path: str):
    file_path = os.path.join(frontend_dist, full_path) if full_path else os.path.join(frontend_dist, "index.html")
    if full_path and os.path.isfile(file_path):
        return FileResponse(file_path)

    index_path = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "frontend not built"}


@app.get("/health")
def health():
    return {"status": "ok"}
