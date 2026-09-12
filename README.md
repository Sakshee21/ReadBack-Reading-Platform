# ReadBack

A habit-scaffolding reading app that applies binge-watching mechanics (autoplay-style
continuation, micro-sessions, cliffhanger pacing) to public-domain literature. See
`Report/ReadBack_Project_Proposal_v2.docx` for the theoretical background. This is the
Phase 2 MVP: content pipeline, reading loop, RSVP focus mode, visualization checkpoints,
recap engine, comprehension checkpoints, and streak/progress gamification. No survey
tooling and no social/accountability layer (out of scope for MVP).

## Stack

- **Backend:** FastAPI (Python) + SQLAlchemy + Alembic, PostgreSQL
- **Frontend:** React (Vite), plain CSS
- **Content:** Project Gutenberg, via Gutendex metadata + raw Gutenberg plain-text

## Prerequisites

- Docker Desktop (for PostgreSQL)
- Python 3.11+
- Node.js 18+

## 1. Start the database

```bash
docker compose up -d db
```

This starts Postgres and maps it to **host port 5433** (not the default 5432) because
many dev machines already run a native PostgreSQL service on 5432 - mapping to the
default silently connects to the wrong server instead of the container. If 5433 is
also free on your machine you don't need to change anything; if it collides too, edit
the port mapping in `docker-compose.yml` and `backend/.env`'s `DATABASE_URL` together.

## 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m scripts.seed_books    # see SEED.md
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

Run tests:

```bash
python -m pytest tests/ -q
```

## 3. Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

App: http://localhost:5173

## Project layout

```
backend/
  app/
    models.py          SQLAlchemy models
    schemas.py          Pydantic request/response models
    routers/            auth, books, sessions, checkpoints, streaks
    services/
      segmentation.py   Gutenberg boilerplate stripping, chapter + micro-session splitting
      streak.py         daily streak increment/reset logic
      recap.py          rule-based "Previously..." recap builder
      checkpoint.py      comprehension-quiz scoring
      summarize.py       naive fallback chapter summaries
  alembic/               migrations
  scripts/
    import_book.py       pulls one book from Gutenberg and persists it
    seed_books.py         seeds 5 books + hand-authored summaries/checkpoints
  tests/                 streak + segmentation unit tests

frontend/
  src/
    pages/               Login, Register, Library, Reader
    components/          RSVPMode, AutoplayCountdown, RecapBanner,
                          VisualizationPrompt, CheckpointQuiz, StreakDisplay
    api.js                fetch wrapper + JWT storage
    AuthContext.jsx        auth state
```

## Notes / known simplifications

- Chapter titles and comprehension-checkpoint questions were hand-verified for all 5
  seed books; chapters without a hand-authored recap summary fall back to a
  deterministic first-sentence extraction (`services/summarize.py`) rather than an
  LLM call, per the MVP scope.
- The content pipeline's chapter/Table-of-Contents detection is heuristic (see
  `services/segmentation.py` docstrings) - it was validated against all 5 seed books
  but a newly imported Gutenberg book with an unusual layout may need a quick manual
  spot-check of its chapter count.
- Visualization checkpoints show a placeholder "artwork" panel - no image generation.
