"""Re-run conversion on books that were uploaded before the paragraph
normaliser and front-matter detection existed.

Only touches books with source_type='upload'. Seeded books and other users'
data are never modified.

Re-conversion rebuilds chapters and micro-sessions from the stored text, so
session boundaries change and any saved position would point at a row that no
longer exists. Progress for a re-converted book is therefore reset, and the
script says so for each book rather than losing your place silently.

Usage:
    python -m scripts.reconvert_uploads --list
    python -m scripts.reconvert_uploads --all --yes
    python -m scripts.reconvert_uploads --book-id 42 --yes
    python -m scripts.reconvert_uploads --email someone@example.com --yes
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Book,
    Chapter,
    MicroSession,
    ReadingEvent,
    ReadingSession,
    User,
    UserBookProgress,
)
from app.services.ingest import persist_book_content, plan_chapters  # noqa: E402
from app.services.normalize import normalize_uploaded_text  # noqa: E402
from app.services.segmentation import word_count  # noqa: E402


def uploads(db, book_id=None, email=None):
    query = db.query(Book).filter(Book.source_type == "upload")
    if book_id:
        query = query.filter(Book.id == book_id)
    if email:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"No account '{email}'.", file=sys.stderr)
            sys.exit(1)
        query = query.filter(Book.owner_user_id == user.id)
    return query.order_by(Book.id).all()


def reconvert(db, book: Book) -> str:
    if not (book.full_text or "").strip():
        return "SKIPPED - no stored text; please re-upload this file"

    chapter_ids = [c.id for c in book.chapters]
    micro_ids = [ms.id for c in book.chapters for ms in c.micro_sessions]

    # Rows that point at the old chapters/micro-sessions must go first.
    if micro_ids or chapter_ids:
        db.query(ReadingEvent).filter(ReadingEvent.book_id == book.id).delete(
            synchronize_session=False
        )
        db.query(ReadingSession).filter(ReadingSession.book_id == book.id).delete(
            synchronize_session=False
        )
        progress_reset = (
            db.query(UserBookProgress)
            .filter(UserBookProgress.book_id == book.id)
            .delete(synchronize_session=False)
        )
        if micro_ids:
            db.query(MicroSession).filter(MicroSession.id.in_(micro_ids)).delete(
                synchronize_session=False
            )
        if chapter_ids:
            db.query(Chapter).filter(Chapter.id.in_(chapter_ids)).delete(
                synchronize_session=False
            )
    else:
        progress_reset = 0
    db.flush()

    # The stored text came out of the old extractor, so run it through the
    # normaliser again - that is the whole point of re-converting.
    text = normalize_uploaded_text(book.full_text, source="txt")
    if word_count(text) < 50:
        db.rollback()
        return "SKIPPED - stored text is too short after normalising; please re-upload"

    book.full_text = text
    chapters, sessions, story_words = persist_book_content(db, book, plan_chapters(text))
    book.total_word_count = story_words
    book.status = "ready"
    book.failure_reason = None
    db.commit()

    note = f"{chapters} chapters, {sessions} sessions, {story_words:,} story words"
    if progress_reset:
        note += "  [reading position reset]"
    return note


def main():
    parser = argparse.ArgumentParser(description="Re-convert user-uploaded books.")
    parser.add_argument("--book-id", type=int, help="one book")
    parser.add_argument("--email", help="all uploads owned by this account")
    parser.add_argument("--all", action="store_true", help="every uploaded book")
    parser.add_argument("--list", action="store_true", help="show what would be done")
    parser.add_argument("--yes", action="store_true", help="actually make changes")
    args = parser.parse_args()

    if not (args.book_id or args.email or args.all or args.list):
        parser.error("choose --list, --all, --book-id or --email")

    db = SessionLocal()
    try:
        books = uploads(db, args.book_id, args.email)
        if not books:
            print("No uploaded books found.")
            return

        if args.list or not args.yes:
            print(f"{len(books)} uploaded book(s):")
            for book in books:
                owner = db.get(User, book.owner_user_id)
                print(
                    f"  [{book.id}] {book.title[:40]:42s} {len(book.chapters):3d} chapters  "
                    f"owner={owner.email if owner else '?'}"
                )
            if not args.yes:
                print("\nRe-run with --yes to re-convert. Reading positions will be reset.")
            return

        print(f"Re-converting {len(books)} book(s). Reading positions will be reset.\n")
        for book in books:
            print(f"  [{book.id}] {book.title[:40]:42s} ", end="", flush=True)
            try:
                print(reconvert(db, book))
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                print(f"FAILED - {exc}")
        print("\nDone.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
