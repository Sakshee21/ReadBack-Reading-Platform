import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Book, Chapter, MicroSession, MicroSessionTheme, ReadingEvent, User
from app.services.themes import MIN_SHOWN_SCORE

router = APIRouter(prefix="/admin", tags=["admin"])

EVENT_COLUMNS = [
    "id",
    "user_id",
    "user_email",
    "book_id",
    # Uploaded books are private and must be excluded from pilot analysis -
    # filter on these two columns rather than trying to recognise titles.
    "is_user_uploaded",
    "source_type",
    "chapter_id",
    "micro_session_id",
    "event_type",
    "metadata",
    "created_at",
]


@router.get("/export/events.csv")
def export_events_csv(token: str = Query(...), db: Session = Depends(get_db)):
    """Token-protected CSV dump of all reading events for pulling pilot data
    into a spreadsheet. Pass ``?token=<ADMIN_TOKEN>``."""
    if token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    emails = dict(db.query(User.id, User.email).all())
    book_meta = {
        bid: (uploaded, source)
        for bid, uploaded, source in db.query(Book.id, Book.is_user_uploaded, Book.source_type).all()
    }

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EVENT_COLUMNS)
    for ev in db.query(ReadingEvent).order_by(ReadingEvent.id).all():
        writer.writerow(
            [
                ev.id,
                ev.user_id,
                emails.get(ev.user_id, ""),
                ev.book_id if ev.book_id is not None else "",
                book_meta.get(ev.book_id, (False, ""))[0] if ev.book_id is not None else "",
                book_meta.get(ev.book_id, (False, ""))[1] if ev.book_id is not None else "",
                ev.chapter_id if ev.chapter_id is not None else "",
                ev.micro_session_id if ev.micro_session_id is not None else "",
                ev.event_type,
                json.dumps(ev.event_metadata) if ev.event_metadata is not None else "",
                ev.created_at.isoformat() if ev.created_at else "",
            ]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=events.csv"},
    )


THEME_COLUMNS = [
    "book_id",
    "book_title",
    "chapter_index",
    "micro_session_id",
    "theme",
    "score",
    "source",
    "model",
    "prompt_version",
    "theme_list_version",
]


@router.get("/export/themes.csv")
def export_themes_csv(token: str = Query(...), db: Session = Depends(get_db)):
    """Token-protected CSV of theme tags for the shared (seeded) books, one row
    per chunk and theme, scores of 3 or more only. Joins to the events export on
    micro_session_id. Uploaded books are private and never included."""
    if token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    rows = (
        db.query(Book, Chapter, MicroSessionTheme)
        .join(Chapter, Chapter.book_id == Book.id)
        .join(MicroSession, MicroSession.chapter_id == Chapter.id)
        .join(MicroSessionTheme, MicroSessionTheme.micro_session_id == MicroSession.id)
        .filter(Book.owner_user_id.is_(None), Book.is_user_uploaded.is_(False), MicroSessionTheme.score >= MIN_SHOWN_SCORE)
        .order_by(Book.id, Chapter.index, MicroSession.index, MicroSessionTheme.theme)
        .all()
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(THEME_COLUMNS)
    for book, chapter, tag in rows:
        writer.writerow(
            [
                book.id, book.title, chapter.index, tag.micro_session_id, tag.theme, tag.score,
                tag.source, tag.model, tag.prompt_version, tag.theme_list_version,
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=themes.csv"},
    )
