from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Book, MicroSession, ReadingEvent, User, UserBookProgress
from app.schemas import PaceOut
from app.services.pace import DEFAULT_WPM, minutes_for, summarize

router = APIRouter(prefix="/pace", tags=["pace"])

SAMPLE_LIMIT = 40


@router.get("/me", response_model=PaceOut)
def my_pace(book_id: int | None = None, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """Reading pace from logged session_end events, plus how long the current
    book has left at that pace."""
    rows = (
        db.query(ReadingEvent.event_metadata)
        .filter(ReadingEvent.user_id == user.id, ReadingEvent.event_type == "session_end")
        .order_by(ReadingEvent.id.desc())
        .limit(SAMPLE_LIMIT)
        .all()
    )
    samples = [((m or {}).get("word_count"), (m or {}).get("active_ms")) for (m,) in rows]
    pace = summarize(samples)

    effective_wpm = pace["wpm_average"] or DEFAULT_WPM
    words_left = None
    if book_id is not None:
        book = db.get(Book, book_id)
        if book:
            words_left = _words_remaining(db, user, book)

    return PaceOut(
        **pace,
        words_left=words_left,
        minutes_left_book=minutes_for(words_left, effective_wpm) if words_left else None,
    )


def _words_remaining(db: Session, user: User, book: Book) -> int:
    progress = (
        db.query(UserBookProgress)
        .filter(UserBookProgress.user_id == user.id, UserBookProgress.book_id == book.id)
        .first()
    )
    if not progress or not progress.current_micro_session_id:
        return book.total_word_count

    current = db.get(MicroSession, progress.current_micro_session_id)
    if not current:
        return book.total_word_count

    read = sum(
        ms.word_count
        for c in book.chapters
        for ms in c.micro_sessions
        if (c.index, ms.index) < (current.chapter.index, current.index)
    )
    return max(0, book.total_word_count - read)
