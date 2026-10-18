import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import book_for_user, get_current_user
from app.models import (
    Book,
    Chapter,
    CheckpointAttempt,
    ComprehensionCheckpoint,
    MicroSession,
    ReadingEvent,
    ReadingSession,
    User,
    UserBookProgress,
)
from app.schemas import (
    BookOut,
    BookStatusOut,
    CheckpointOut,
    ChapterOut,
    JumpRequest,
    MicroSessionListItemOut,
    MicroSessionOut,
    MicroSessionPart,
    ProgressOut,
    ReaderPositionOut,
)
from app.services.checkpoint import is_quiz_due
from app.services.extract import ExtractionError, extract, safe_filename
from app.services.ingest import persist_book_content, plan_chapters
from app.services.progression import (
    build_block,
    ordered_micro_sessions,
    size_level_for,
    story_chapters,
)
from app.services.recap import choose_recap, needs_recap
from app.services.segmentation import word_count

router = APIRouter(prefix="/books", tags=["books"])


def _book_out(book: Book) -> BookOut:
    return BookOut(
        id=book.id,
        gutenberg_id=book.gutenberg_id,
        title=book.title,
        author=book.author,
        total_word_count=book.total_word_count,
        chapter_count=len(book.chapters),
        theme=book.theme or "parchment",
        is_user_uploaded=book.is_user_uploaded,
        source_type=book.source_type,
        status=book.status,
        failure_reason=book.failure_reason,
    )


@router.get("", response_model=list[BookOut])
def list_books(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Shared seeded books plus this user's own uploads - never anyone else's."""
    books = (
        db.query(Book)
        .filter(or_(Book.owner_user_id.is_(None), Book.owner_user_id == user.id))
        .order_by(Book.title)
        .all()
    )
    return [_book_out(b) for b in books]


@router.get("/{book_id}", response_model=list[ChapterOut])
def get_book_chapters(
    book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    book = book_for_user(db, book_id, user)
    return [
        ChapterOut(
            id=c.id,
            index=c.index,
            title=c.title,
            word_count=c.word_count,
            micro_session_count=len(c.micro_sessions),
        )
        for c in story_chapters(book)
    ]


def _get_or_create_progress(db: Session, user: User, book: Book) -> UserBookProgress:
    progress = (
        db.query(UserBookProgress)
        .filter(UserBookProgress.user_id == user.id, UserBookProgress.book_id == book.id)
        .first()
    )
    if progress:
        return progress

    # Start at the first *story* chapter, so an uploaded book doesn't open on
    # its title page or contents list.
    story = story_chapters(book)
    first_chapter = story[0] if story else None
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

    merged = MicroSessionOut(
        id=block[0].id,
        index=block[0].index,
        text="\n\n".join(ms.text for ms in block),
        word_count=sum(ms.word_count for ms in block),
        is_cliffhanger_break=block[-1].is_cliffhanger_break,
        has_visualization_prompt=any(ms.has_visualization_prompt for ms in block),
        parts=[MicroSessionPart(id=ms.id, text=ms.text) for ms in block],
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
        for c in story_chapters(book)
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
    book_id: int,
    ms: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The reader's saved position. With ``ms`` it is a read-only peek at that
    passage (used by "Go to passage" in the notes page): the saved position is
    left alone until the reader actually finishes a session there."""
    book = book_for_user(db, book_id, user)
    if not book.chapters:
        raise HTTPException(status_code=422, detail="Book has no content")

    progress = _get_or_create_progress(db, user, book)
    if ms is not None:
        peeked = db.get(MicroSession, ms)
        if not peeked or peeked.chapter.book_id != book.id:
            raise HTTPException(status_code=404, detail="Micro-session not found for this book")
        return _build_reader_position(db, user, book, progress, peeked)
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
    book = book_for_user(db, book_id, user)

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
    book = book_for_user(db, book_id, user)

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
    book = book_for_user(db, book_id, user)

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
        for c in story_chapters(book)
        for ms in c.micro_sessions
        if (c.index, ms.index) < (current.chapter.index, current.index)
    )
    pct = round(100 * words_read / book.total_word_count, 2) if book.total_word_count else 0.0
    return ProgressOut(book_id=book.id, words_read=words_read, total_words=book.total_word_count, progress_pct=pct)


# --------------------------------------------------------------------------
# User uploads
#
# Uploaded books are private to the uploader and flagged so they can be kept
# out of pilot analysis. Conversion happens in a background task because
# segmenting a full novel takes a few seconds; the client polls /status.
# --------------------------------------------------------------------------


async def _read_capped(upload: UploadFile, limit: int) -> bytes:
    """Read the upload, refusing anything over the limit without buffering it all."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"That file is larger than {limit // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _convert_upload(book_id: int, filename: str, data: bytes) -> None:
    """Background conversion. Never raises - failures are recorded on the row."""
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if book is None:
            return
        try:
            text, source_chapters, _fmt = extract(filename, data)
            words = word_count(text)
            if words < settings.upload_min_words:
                raise ExtractionError(
                    f"That file only has {words} words - too short to segment into "
                    "reading sessions.",
                    "too_short",
                )
            if words > settings.upload_max_words:
                raise ExtractionError(
                    f"That book is {words:,} words, over the {settings.upload_max_words:,} "
                    "word limit.",
                    "too_long",
                )

            chapters = plan_chapters(text, source_chapters)
            book.full_text = text
            _, sessions, story_words = persist_book_content(db, book, chapters)
            if sessions == 0:
                raise ExtractionError(
                    "No story content was found - the file looks like front matter only.",
                    "no_story_content",
                )
            # Progress and pace are measured against the story, not the title
            # page and licence.
            book.total_word_count = story_words
            book.status = "ready"
            book.failure_reason = None
            db.commit()
        except ExtractionError as exc:
            db.rollback()
            book = db.get(Book, book_id)
            if book:
                book.status = "failed"
                book.failure_reason = exc.message
                db.commit()
        except Exception:  # noqa: BLE001 - never leave a book stuck "processing"
            db.rollback()
            book = db.get(Book, book_id)
            if book:
                book.status = "failed"
                book.failure_reason = "Conversion failed unexpectedly."
                db.commit()
    finally:
        db.close()


@router.post("/upload", response_model=BookStatusOut, status_code=202)
async def upload_book(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    owned = (
        db.query(Book)
        .filter(Book.owner_user_id == user.id, Book.status != "failed")
        .count()
    )
    if owned >= settings.uploads_per_user:
        raise HTTPException(
            status_code=409,
            detail=f"You can upload up to {settings.uploads_per_user} books. "
            "Delete one to make room.",
        )

    name = safe_filename(file.filename or "upload")
    data = await _read_capped(file, settings.upload_max_bytes)
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")

    # Fail fast on format problems so the user gets an error now rather than a
    # failed row thirty seconds later.
    try:
        from app.services.extract import sniff_format

        sniff_format(name, data)
    except ExtractionError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    fallback_title = name.rsplit(".", 1)[0].replace("_", " ").strip() or "Untitled"
    book = Book(
        gutenberg_id=None,
        title=(title or fallback_title)[:500],
        author=(author or "Unknown")[:255],
        full_text="",
        total_word_count=0,
        owner_user_id=user.id,
        is_user_uploaded=True,
        source_type="upload",
        status="processing",
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    background.add_task(_convert_upload, book.id, name, data)

    return BookStatusOut(id=book.id, status=book.status, title=book.title)


@router.get("/{book_id}/status", response_model=BookStatusOut)
def upload_status(
    book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    book = book_for_user(db, book_id, user)
    return BookStatusOut(
        id=book.id,
        status=book.status,
        failure_reason=book.failure_reason,
        title=book.title,
        chapter_count=len(book.chapters),
        micro_session_count=sum(len(c.micro_sessions) for c in book.chapters),
        total_word_count=book.total_word_count,
    )


@router.delete("/{book_id}", status_code=204)
def delete_uploaded_book(
    book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Delete an uploaded book and everything hanging off it. Seeded books are
    shared content and can never be deleted through the API."""
    book = book_for_user(db, book_id, user)
    if not book.is_user_uploaded or book.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only your own uploads can be deleted.")

    chapter_ids = [c.id for c in book.chapters]
    micro_ids = [ms.id for c in book.chapters for ms in c.micro_sessions]

    # Children that hold foreign keys into this book must go first; chapters and
    # micro-sessions themselves cascade from the Book relationship.
    event_filter = [ReadingEvent.book_id == book.id]
    if chapter_ids:
        event_filter.append(ReadingEvent.chapter_id.in_(chapter_ids))
    if micro_ids:
        event_filter.append(ReadingEvent.micro_session_id.in_(micro_ids))
    db.query(ReadingEvent).filter(or_(*event_filter)).delete(synchronize_session=False)

    db.query(ReadingSession).filter(ReadingSession.book_id == book.id).delete(
        synchronize_session=False
    )
    db.query(UserBookProgress).filter(UserBookProgress.book_id == book.id).delete(
        synchronize_session=False
    )
    checkpoint_ids = [
        c.id
        for c in db.query(ComprehensionCheckpoint)
        .filter(ComprehensionCheckpoint.book_id == book.id)
        .all()
    ]
    if checkpoint_ids:
        db.query(CheckpointAttempt).filter(
            CheckpointAttempt.checkpoint_id.in_(checkpoint_ids)
        ).delete(synchronize_session=False)
        db.query(ComprehensionCheckpoint).filter(
            ComprehensionCheckpoint.book_id == book.id
        ).delete(synchronize_session=False)

    db.delete(book)
    db.commit()
    return None
