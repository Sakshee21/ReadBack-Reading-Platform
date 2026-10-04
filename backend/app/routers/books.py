import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import (
    Book,
    Chapter,
    CheckpointAttempt,
    ComprehensionCheckpoint,
    MicroSession,
    ReadingSession,
    User,
    UserBookProgress,
)
from app.schemas import (
    BookOut,
    CheckpointOut,
    ChapterOut,
    JumpRequest,
    MicroSessionListItemOut,
    MicroSessionOut,
    ProgressOut,
    ReaderPositionOut,
)
from app.services.checkpoint import is_quiz_due
from app.services.progression import build_block, ordered_micro_sessions, size_level_for
from app.services.recap import choose_recap, needs_recap

router = APIRouter(prefix="/books", tags=["books"])


def _book_out(book: Book) -> BookOut:
    return BookOut(
        id=book.id,
        gutenberg_id=book.gutenberg_id,
        title=book.title,
        author=book.author,
        total_word_count=book.total_word_count,
        chapter_count=len(book.chapters),
    )


@router.get("", response_model=list[BookOut])
def list_books(db: Session = Depends(get_db)):
    books = db.query(Book).order_by(Book.title).all()
    return [_book_out(b) for b in books]


@router.get("/{book_id}", response_model=list[ChapterOut])
def get_book_chapters(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return [
        ChapterOut(
            id=c.id,
            index=c.index,
            title=c.title,
            word_count=c.word_count,
            micro_session_count=len(c.micro_sessions),
        )
        for c in book.chapters
    ]


def _get_or_create_progress(db: Session, user: User, book: Book) -> UserBookProgress:
    progress = (
        db.query(UserBookProgress)
        .filter(UserBookProgress.user_id == user.id, UserBookProgress.book_id == book.id)
        .first()
    )
    if progress:
        return progress

    first_chapter = book.chapters[0] if book.chapters else None
    first_micro = first_chapter.micro_sessions[0] if first_chapter and first_chapter.micro_sessions else None
    progress = UserBookProgress(
        user_id=user.id,
        book_id=book.id,
        current_chapter_id=first_chapter.id if first_chapter else None,
        current_micro_session_id=first_micro.id if first_micro else None,
        last_read_at=None,
    )
    db.add(progress)
    db.commit()
    db.refresh(progress)
    return progress


def _checkpoint_due(db: Session, user: User, book: Book, chapter: Chapter, micro_session: MicroSession):
    if micro_session.index != 0:
        return None
    if not is_quiz_due(chapter.index, settings.quiz_every_n_chapters):
        return None
    checkpoint = (
        db.query(ComprehensionCheckpoint)
        .filter(
            ComprehensionCheckpoint.book_id == book.id,
            ComprehensionCheckpoint.chapter_index_trigger == chapter.index,
        )
        .first()
    )
    if not checkpoint:
        return None

    already_attempted = (
        db.query(CheckpointAttempt)
        .filter(CheckpointAttempt.user_id == user.id, CheckpointAttempt.checkpoint_id == checkpoint.id)
        .first()
    )
    if already_attempted:
        return None
    return checkpoint


def _completed_session_count(db: Session, user: User) -> int:
    return (
        db.query(ReadingSession)
        .filter(ReadingSession.user_id == user.id, ReadingSession.completed.is_(True))
        .count()
    )


def _build_reader_position(
    db: Session, user: User, book: Book, progress: UserBookProgress, micro_session: MicroSession
) -> ReaderPositionOut:
    chapter = micro_session.chapter

    # Merge the current micro-session with the next few into one served block,
    # sized by how many sessions the reader has completed (progressive length).
    size = size_level_for(_completed_session_count(db, user))
    if user.session_size_level != size:
        user.session_size_level = size
        db.commit()
    block, _ = build_block(ordered_micro_sessions(book), micro_session.id, size)
    if not block:
        block = [micro_session]

    # The block shows one visualization checkpoint: use the artwork from the
    # first micro-session in it that actually has one.
    illustrated = next((ms for ms in block if ms.visualization_image), None)
    merged = MicroSessionOut(
        id=block[0].id,
        index=block[0].index,
        text="\n\n".join(ms.text for ms in block),
        word_count=sum(ms.word_count for ms in block),
        is_cliffhanger_break=block[-1].is_cliffhanger_break,
        has_visualization_prompt=any(ms.has_visualization_prompt for ms in block),
        visualization_image=illustrated.visualization_image if illustrated else None,
        visualization_alt=illustrated.visualization_alt if illustrated else None,
        visualization_attribution=illustrated.visualization_attribution if illustrated else None,
    )

    recap = None
    now = dt.datetime.utcnow()
    if needs_recap(progress.last_read_at, now, settings.recap_gap_hours):
        hours_since = (now - progress.last_read_at).total_seconds() / 3600
        chapters = sorted(book.chapters, key=lambda c: c.index)
        recap = choose_recap(chapters, chapter.index, hours_since, settings.recap_long_gap_hours) or None

    checkpoint = _checkpoint_due(db, user, book, chapter, micro_session)

    words_read_so_far = sum(
        ms.word_count
        for c in book.chapters
        for ms in c.micro_sessions
        if (c.index, ms.index) < (chapter.index, micro_session.index)
    )
    progress_pct = round(100 * words_read_so_far / book.total_word_count, 2) if book.total_word_count else 0.0

    return ReaderPositionOut(
        book=_book_out(book),
        micro_session=merged,
        chapter_id=chapter.id,
        chapter_index=chapter.index,
        chapter_title=chapter.title,
        is_first_in_book=(chapter.index == 0 and micro_session.index == 0),
        recap=recap,
        checkpoint_due=CheckpointOut.model_validate(checkpoint) if checkpoint else None,
        progress_pct=progress_pct,
    )


@router.get("/{book_id}/reader", response_model=ReaderPositionOut)
def get_reader_position(
    book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not book.chapters:
        raise HTTPException(status_code=422, detail="Book has no content")

    progress = _get_or_create_progress(db, user, book)
    micro_session = db.get(MicroSession, progress.current_micro_session_id)
    if not micro_session:
        raise HTTPException(status_code=422, detail="No reading position available")

    return _build_reader_position(db, user, book, progress, micro_session)


@router.post("/{book_id}/jump", response_model=ReaderPositionOut)
def jump_to_micro_session(
    book_id: int,
    payload: JumpRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    micro_session = db.get(MicroSession, payload.micro_session_id)
    if not micro_session or micro_session.chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="Micro-session not found for this book")

    progress = _get_or_create_progress(db, user, book)
    progress.current_chapter_id = micro_session.chapter_id
    progress.current_micro_session_id = micro_session.id
    db.commit()
    db.refresh(progress)

    return _build_reader_position(db, user, book, progress, micro_session)


@router.get("/{book_id}/micro-sessions", response_model=list[MicroSessionListItemOut])
def list_micro_sessions(
    book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    progress = (
        db.query(UserBookProgress)
        .filter(UserBookProgress.user_id == user.id, UserBookProgress.book_id == book.id)
        .first()
    )
    current_ms_id = progress.current_micro_session_id if progress else None

    completed_ids = {
        row.micro_session_id
        for row in db.query(ReadingSession.micro_session_id)
        .filter(
            ReadingSession.user_id == user.id,
            ReadingSession.book_id == book.id,
            ReadingSession.completed.is_(True),
        )
        .distinct()
    }

    # With merged blocks only the block's first micro-session gets its own
    # ReadingSession row, so also treat everything before the current position
    # as completed to keep the drawer accurate.
    ordered = ordered_micro_sessions(book)
    order_of = {ms.id: i for i, ms in enumerate(ordered)}
    current_order = order_of.get(current_ms_id)

    items = []
    for session_number, ms in enumerate(ordered, start=1):
        completed = ms.id in completed_ids or (
            current_order is not None and order_of[ms.id] < current_order
        )
        items.append(
            MicroSessionListItemOut(
                id=ms.id,
                session_number=session_number,
                chapter_index=ms.chapter.index,
                chapter_title=ms.chapter.title,
                preview=" ".join(ms.text.split()[:4]),
                completed=completed,
                is_current=ms.id == current_ms_id,
            )
        )
    return items


@router.get("/{book_id}/progress", response_model=ProgressOut)
def get_progress(book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    progress = (
        db.query(UserBookProgress)
        .filter(UserBookProgress.user_id == user.id, UserBookProgress.book_id == book.id)
        .first()
    )
    if not progress or not progress.current_micro_session_id:
        return ProgressOut(book_id=book.id, words_read=0, total_words=book.total_word_count, progress_pct=0.0)

    current = db.get(MicroSession, progress.current_micro_session_id)
    words_read = sum(
        ms.word_count
        for c in book.chapters
        for ms in c.micro_sessions
        if (c.index, ms.index) < (current.chapter.index, current.index)
    )
    pct = round(100 * words_read / book.total_word_count, 2) if book.total_word_count else 0.0
    return ProgressOut(book_id=book.id, words_read=words_read, total_words=book.total_word_count, progress_pct=pct)
