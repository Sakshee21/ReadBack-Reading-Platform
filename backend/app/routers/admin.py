import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import ReadingEvent, User

router = APIRouter(prefix="/admin", tags=["admin"])

EVENT_COLUMNS = [
    "id",
    "user_id",
    "user_email",
    "book_id",
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
