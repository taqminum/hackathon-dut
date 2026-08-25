from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routes import api

app = FastAPI(title="Serendipity Navigation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router, prefix="/api")

frontend_dist = __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "..", "webapp", "dist")
if __import__("os").path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


@app.get("/health")
def health():
    return {"status": "ok"}
