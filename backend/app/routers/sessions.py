import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import (
    Book,
    ComprehensionCheckpoint,
    MicroSession,
    ReadingSession,
    User,
    UserBookProgress,
)
from app.schemas import (
    CheckpointOut,
    NextSessionOut,
    MicroSessionOut,
    SessionComplete,
    SessionOut,
    SessionStart,
    StreakOut,
)
from app.services.streak import apply_completed_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/start", response_model=SessionOut)
def start_session(
    payload: SessionStart, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    micro_session = db.get(MicroSession, payload.micro_session_id)
    if not micro_session or micro_session.chapter.book_id != payload.book_id:
        raise HTTPException(status_code=404, detail="Micro-session not found for this book")

    session = ReadingSession(
        user_id=user.id,
        book_id=payload.book_id,
        chapter_id=micro_session.chapter_id,
        micro_session_id=micro_session.id,
        started_at=dt.datetime.utcnow(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _find_next_micro_session(db: Session, current: MicroSession) -> MicroSession | None:
    chapter = current.chapter
    siblings = sorted(chapter.micro_sessions, key=lambda m: m.index)
    pos = next((i for i, m in enumerate(siblings) if m.id == current.id), None)
    if pos is not None and pos + 1 < len(siblings):
        return siblings[pos + 1]

    book = db.get(Book, chapter.book_id)
    chapters = sorted(book.chapters, key=lambda c: c.index)
    cpos = next((i for i, c in enumerate(chapters) if c.id == chapter.id), None)
    if cpos is None:
        return None
    for next_chapter in chapters[cpos + 1 :]:
        if next_chapter.micro_sessions:
            return sorted(next_chapter.micro_sessions, key=lambda m: m.index)[0]
    return None


@router.post("/complete", response_model=NextSessionOut)
def complete_session(
    payload: SessionComplete, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    session = db.get(ReadingSession, payload.session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.completed:
        raise HTTPException(status_code=400, detail="Session already completed")

    current_micro = db.get(MicroSession, session.micro_session_id)

    now = dt.datetime.utcnow()
    session.ended_at = now
    session.completed = True
    session.words_read = current_micro.word_count if current_micro else 0

    today = now.date()
    if user.last_read_date != today:
        new_current, new_longest, new_last = apply_completed_session(
            user.current_streak, user.longest_streak, user.last_read_date, today
        )
        user.current_streak = new_current
        user.longest_streak = new_longest
        user.last_read_date = new_last

    progress = (
        db.query(UserBookProgress)
        .filter(UserBookProgress.user_id == user.id, UserBookProgress.book_id == session.book_id)
        .first()
    )

    next_micro = _find_next_micro_session(db, current_micro) if current_micro else None
    if progress:
        progress.current_chapter_id = next_micro.chapter_id if next_micro else progress.current_chapter_id
        progress.current_micro_session_id = next_micro.id if next_micro else None
        progress.last_read_at = now

    db.commit()

    checkpoint_due = None
    if next_micro and next_micro.index == 0:
        checkpoint = (
            db.query(ComprehensionCheckpoint)
            .filter(
                ComprehensionCheckpoint.book_id == session.book_id,
                ComprehensionCheckpoint.chapter_index_trigger == next_micro.chapter.index,
            )
            .first()
        )
        if checkpoint:
            checkpoint_due = CheckpointOut.model_validate(checkpoint)

    return NextSessionOut(
        finished_book=next_micro is None,
        next_micro_session=MicroSessionOut.model_validate(next_micro) if next_micro else None,
        checkpoint_due=checkpoint_due,
        streak=StreakOut(
            current_streak=user.current_streak,
            longest_streak=user.longest_streak,
            last_read_date=user.last_read_date,
        ),
    )
