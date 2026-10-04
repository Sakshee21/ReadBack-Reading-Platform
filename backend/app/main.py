from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import admin, auth, books, checkpoints, events, sessions, streaks

app = FastAPI(title="ReadBack API", version="0.1.0")

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(books.router)
app.include_router(sessions.router)
app.include_router(checkpoints.router)
app.include_router(streaks.router)
app.include_router(events.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
