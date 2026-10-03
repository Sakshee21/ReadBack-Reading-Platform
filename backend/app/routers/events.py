from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import ReadingEvent, User
from app.schemas import EventIn

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", status_code=201)
def log_events(
    payload: EventIn | list[EventIn] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Accept a single event or a batch. user_id and created_at are set
    server-side so the client can never spoof them."""
    events = payload if isinstance(payload, list) else [payload]
    for e in events:
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
    db.commit()
    return {"logged": len(events)}
