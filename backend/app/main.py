from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, books, checkpoints, sessions, streaks

app = FastAPI(title="ReadBack API", version="0.1.0")

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


@app.get("/health")
def health():
    return {"status": "ok"}
