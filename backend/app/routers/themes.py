import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import book_for_user, get_current_user
from app.models import (
    Chapter,
    MicroSession,
    MicroSessionTagging,
    MicroSessionTheme,
    User,
)
from app.routers.highlights import _session_numbers
from app.services import theme_worker
from app.services import themes as theme_service
from app.services.progression import build_block, ordered_micro_sessions
from app.services.themes import MIN_SHOWN_SCORE, THEMES

router = APIRouter(tags=["themes"])

PREVIEW_CHARS = 160


class ConsentIn(BaseModel):
    granted: bool


def _shown(db: Session, ids: set[int]):
    """Theme rows a reader may see: reached chunks, score high enough."""
    if not ids:
        return []
    return (
        db.query(MicroSessionTheme)
        .filter(
            MicroSessionTheme.micro_session_id.in_(ids),
            MicroSessionTheme.score >= MIN_SHOWN_SCORE,
            MicroSessionTheme.theme.in_(list(THEMES)),  # a retired id must never break a page
        )
        .all()
    )


@router.get("/books/{book_id}/themes")
def list_themes(
    book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    book = book_for_user(db, book_id, user)
    reached = theme_service.reached_micro_session_ids(db, user, book)

    chunks_by_theme: dict[str, set[int]] = {}
    for row in _shown(db, reached):
        chunks_by_theme.setdefault(row.theme, set()).add(row.micro_session_id)
    listing = [
        {"theme": t, "label": THEMES[t], "count": len(chunks)}
        for t, chunks in chunks_by_theme.items()
    ]
    order = list(THEMES)
    listing.sort(key=lambda item: (-item["count"], order.index(item["theme"])))

    tagging = {"tagged": 0, "pending": 0, "failed": 0}
    if reached:
        for (status,) in db.query(MicroSessionTagging.status).filter(
            MicroSessionTagging.micro_session_id.in_(reached)
        ):
            key = {"done": "tagged", "pending": "pending", "failed": "failed"}.get(status)
            if key:
                tagging[key] += 1
    return {"themes": listing, "tagging": tagging}


@router.get("/books/{book_id}/theme-map")
def theme_map(
    book_id: int,
    reveal: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Where each theme sits across the book, one cell per tagged chunk.

    By default only chunks the reader has reached have cells. ``reveal=all``
    is the reader's explicit choice to see the whole book (it can spoil the
    story); it works for any book the caller may open, and for an upload only
    its owner can open it. Chapters and the total always describe the whole
    book, which the progress bar already shows."""
    if reveal is not None and reveal != "all":
        raise HTTPException(status_code=422, detail="reveal must be 'all' or omitted.")
    book = book_for_user(db, book_id, user)
    ordered = ordered_micro_sessions(book)
    position = {ms.id: i for i, ms in enumerate(ordered)}

    chapters: list[dict] = []
    for i, ms in enumerate(ordered):
        chapter = ms.chapter
        if chapters and chapters[-1]["index"] == chapter.index:
            chapters[-1]["end"] = i
        else:
            chapters.append({"index": chapter.index, "title": chapter.title, "start": i, "end": i})

    visible = set(position) if reveal == "all" else theme_service.reached_micro_session_ids(db, user, book)
    by_theme: dict[str, list[dict]] = {}
    for row in _shown(db, visible):
        by_theme.setdefault(row.theme, []).append(
            {"pos": position[row.micro_session_id], "micro_session_id": row.micro_session_id, "score": row.score}
        )
    order = list(THEMES)
    listing = [
        {"theme": t, "label": THEMES[t], "count": len(cells), "cells": sorted(cells, key=lambda c: c["pos"])}
        for t, cells in by_theme.items()
    ]
    listing.sort(key=lambda item: (-item["count"], order.index(item["theme"])))
    return {"reveal": reveal == "all", "total": len(ordered), "chapters": chapters, "themes": listing}


@router.get("/books/{book_id}/themes/{theme}")
def theme_passages(
    book_id: int,
    theme: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = book_for_user(db, book_id, user)
    if theme not in THEMES:
        raise HTTPException(status_code=422, detail="Unknown theme.")
    reached = theme_service.reached_micro_session_ids(db, user, book)
    rows = _shown(db, reached)

    by_chunk: dict[int, list[MicroSessionTheme]] = {}
    for row in rows:
        by_chunk.setdefault(row.micro_session_id, []).append(row)
    wanted = [cid for cid, rs in by_chunk.items() if any(r.theme == theme for r in rs)]
    if not wanted:
        return []

    numbers = _session_numbers(db, book)
    found = (
        db.query(MicroSession, Chapter)
        .join(Chapter, MicroSession.chapter_id == Chapter.id)
        .filter(MicroSession.id.in_(wanted))
        .order_by(Chapter.index, MicroSession.index)
        .all()
    )
    order = list(THEMES)
    out = []
    for ms, chapter in found:
        mine = sorted(by_chunk[ms.id], key=lambda r: (-r.score, order.index(r.theme)))
        out.append(
            {
                "micro_session_id": ms.id,
                "chapter_index": chapter.index,
                "chapter_title": chapter.title,
                "session_number": numbers.get(ms.id),
                "preview": " ".join(ms.text.split())[:PREVIEW_CHARS],
                "score": next(r.score for r in mine if r.theme == theme),
                "themes": [{"theme": r.theme, "label": THEMES[r.theme], "score": r.score} for r in mine],
            }
        )
    return out


@router.get("/books/{book_id}/passage-themes")
def passage_themes(
    book_id: int,
    ms: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Tags for the passage the reader is on (the whole block when chunks are
    merged), best first. Chunks the reader has not reached are never included."""
    book = book_for_user(db, book_id, user)
    chunk = db.get(MicroSession, ms)
    chapter = db.get(Chapter, chunk.chapter_id) if chunk else None
    if chunk is None or chapter is None or chapter.book_id != book.id:
        raise HTTPException(status_code=422, detail="That passage is not in this book.")

    reached = theme_service.reached_micro_session_ids(db, user, book)
    block, _ = build_block(ordered_micro_sessions(book), chunk.id, max(1, user.session_size_level or 1))
    ids = {m.id for m in block} & reached

    best: dict[str, int] = {}
    for row in _shown(db, ids):
        best[row.theme] = max(best.get(row.theme, 0), row.score)
    order = list(THEMES)
    listing = [
        {"theme": t, "label": THEMES[t], "score": score}
        for t, score in sorted(best.items(), key=lambda kv: (-kv[1], order.index(kv[0])))
    ]

    preparing = False
    if theme_service.tagging_enabled(db, user, book) and ids:
        done = {
            row[0]
            for row in db.query(MicroSessionTagging.micro_session_id).filter(
                MicroSessionTagging.micro_session_id.in_(ids), MicroSessionTagging.status.in_(("done", "failed"))
            )
        }
        preparing = bool(ids - done)
    return {"themes": listing, "preparing": preparing}


@router.patch("/books/{book_id}/theme-consent")
def set_theme_consent(
    book_id: int,
    payload: ConsentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = book_for_user(db, book_id, user)
    if not book.is_user_uploaded or book.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only your own uploads can be tagged.")
    _apply_consent(db, book, payload.granted)
    db.commit()
    return {"theme_tagging_consent": book.theme_tagging_consent}


def _apply_consent(db: Session, book, granted: bool) -> None:
    if granted:
        book.theme_tagging_consent = True
        book.theme_tagging_consent_at = dt.datetime.utcnow()
        return
    book.theme_tagging_consent = False
    book.theme_tagging_consent_at = None
    ids = [
        row[0]
        for row in db.query(MicroSession.id)
        .join(Chapter, MicroSession.chapter_id == Chapter.id)
        .filter(Chapter.book_id == book.id)
    ]
    if ids:
        db.query(MicroSessionTheme).filter(MicroSessionTheme.micro_session_id.in_(ids)).delete(
            synchronize_session=False
        )
        db.query(MicroSessionTagging).filter(MicroSessionTagging.micro_session_id.in_(ids)).delete(
            synchronize_session=False
        )


class PrefetchIn(BaseModel):
    micro_session_id: int


@router.post("/books/{book_id}/themes/prefetch", status_code=202)
def prefetch_themes(
    book_id: int,
    payload: PrefetchIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Start tagging the chunk the reader is on and the next few, in the
    background. Returns at once. Only for the owner of a consented upload;
    seeded books are tagged in one batch so this is a no-op for them."""
    book = book_for_user(db, book_id, user)
    if book.is_user_uploaded and (book.owner_user_id != user.id or not book.theme_tagging_consent):
        raise HTTPException(status_code=403, detail="Theme tagging is not enabled for this book.")
    if not theme_service.tagging_enabled(db, user, book):
        return {"queued": 0}  # seeded books ship with their tags
    if not (settings.theme_tagging_on_demand and settings.llm_api_key and settings.llm_model):
        return {"queued": 0}

    ms = db.get(MicroSession, payload.micro_session_id)
    chapter = db.get(Chapter, ms.chapter_id) if ms else None
    if ms is None or chapter is None or chapter.book_id != book.id:
        raise HTTPException(status_code=422, detail="That passage is not in this book.")

    stamp = dt.datetime.utcnow()
    claimed = theme_worker.claim(db, theme_worker.plan_prefetch(db, book, ms.id), stamp=stamp)
    if claimed:
        background.add_task(theme_worker.run_prefetch, book.id, claimed, stamp=stamp)
    return {"queued": len(claimed)}
