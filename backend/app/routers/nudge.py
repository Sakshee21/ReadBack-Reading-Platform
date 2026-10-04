import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Book, User, UserBookProgress
from app.schemas import NudgeOut
from app.services.nudge import AWAY, STREAK_AT_RISK, choose_nudge
from app.services.streak import streak_after_gap

router = APIRouter(prefix="/nudge", tags=["nudge"])


@router.get("/me", response_model=NudgeOut)
def my_nudge(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today = dt.datetime.utcnow().date()
    live_streak = streak_after_gap(user.current_streak, user.last_read_date, today)
    kind = choose_nudge(user.last_read_date, live_streak, today, settings.nudge_away_days)
    if kind is None:
        return NudgeOut(kind=None, message=None, book_id=None, book_title=None, days_away=0)

    days_away = (today - user.last_read_date).days
    resume = (
        db.query(UserBookProgress)
        .filter(UserBookProgress.user_id == user.id, UserBookProgress.last_read_at.isnot(None))
        .order_by(UserBookProgress.last_read_at.desc())
        .first()
    )
    book = db.get(Book, resume.book_id) if resume else None

    if kind == AWAY:
        where = f'"{book.title}"' if book else "your book"
        message = f"It's been {days_away} days since you opened {where}. Pick up where you left off?"
    else:
        message = (
            f"Your {live_streak}-day streak is still alive - "
            "a couple of minutes today keeps it going."
        )

    return NudgeOut(
        kind=kind,
        message=message,
        book_id=book.id if book else None,
        book_title=book.title if book else None,
        days_away=days_away,
    )
