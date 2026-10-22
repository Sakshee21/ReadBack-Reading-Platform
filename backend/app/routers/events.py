import logging

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import RESEARCH, get_current_user
from app.models import Book, ReadingEvent, User
from app.schemas import EventIn

log = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


def _research_book_ids(db: Session, book_ids: set[int]) -> set[int]:
    """Which of these ids are research documents."""
    real = {bid for bid in book_ids if bid is not None}
    if not real:
        return set()
    rows = db.query(Book.id).filter(Book.id.in_(real), Book.source_type == RESEARCH).all()
    return {row[0] for row in rows}


@router.post("", status_code=201)
def log_events(
    payload: EventIn | list[EventIn] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Accept a single event or a batch. user_id and created_at are set
    server-side so the client can never spoof them.

    Events against a research document are dropped rather than stored. The
    research reader does not emit them, but the pilot data has to be clean
    whatever a client sends, and a count that silently includes paper-reading
    would make session length and streaks meaningless.
    """
    events = payload if isinstance(payload, list) else [payload]
    research = _research_book_ids(db, {e.book_id for e in events})

    stored = 0
    for e in events:
        if e.book_id in research:
            continue
        db.add(
            ReadingEvent(
                user_id=user.id,
                book_id=e.book_id,
                chapter_id=e.chapter_id,
                micro_session_id=e.micro_session_id,
                event_type=e.event_type,
                event_metadata=e.metadata,
            )
        )
        stored += 1
    db.commit()

    dropped = len(events) - stored
    if dropped:
        # Logged rather than returned: the response shape is part of the
        # client contract, and a drop here means a client is misbehaving,
        # which is something to find in the log rather than to hand back.
        log.warning("dropped %s event(s) aimed at a research document", dropped)
    return {"logged": stored}
