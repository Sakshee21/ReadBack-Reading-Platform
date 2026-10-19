"""Tag the reading chunks of seeded books with themes, cached in the database.

The running app never calls the model for seeded books - this script does, once,
and the API serves the stored tags. Saved after every chunk, so an interrupted
or rate-limited run can simply be run again: it skips every chunk that already has
tags. A chunk's tags are permanent, whatever model or prompt made them, so this
script never re-tags or overwrites. Uploaded books are never touched here (they
are tagged on demand, and only with the owner's consent).

Configure OP_API_KEY and OP_MODEL in backend/.env.

Usage:
    python -m scripts.tag_themes --dry-run          # counts and a token estimate, no calls
    python -m scripts.tag_themes                    # all seeded books, skip done
    python -m scripts.tag_themes --book 2           # one book (database id)
    python -m scripts.tag_themes --limit 3          # try the first 3 untagged chunks
"""

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Book, MicroSession, MicroSessionTagging  # noqa: E402
from app.services import themes  # noqa: E402
from app.services.theme_worker import CLAIM_TTL  # noqa: E402
from app.services.progression import ordered_micro_sessions  # noqa: E402
from app.services.themes import ThemeProviderError, make_client  # noqa: E402

TOKENS_PER_CHUNK = 1400  # measured in the smoke test
MAX_CONSECUTIVE_FAILURES = 5  # a bad key, no credit or a dead model: stop instead of marking every chunk failed


def select_chunks(db, book_id: int | None) -> list[MicroSession]:
    """Story chunks of ready seeded books, in reading order."""
    query = db.query(Book).filter(Book.owner_user_id.is_(None), Book.is_user_uploaded.is_(False), Book.status == "ready").order_by(Book.id)
    if book_id is not None:
        query = query.filter(Book.id == book_id)
    chunks: list[MicroSession] = []
    for book in query:
        chunks.extend(ordered_micro_sessions(book))
    return chunks


def _live_claim(row: MicroSessionTagging | None, now: dt.datetime) -> bool:
    return bool(row and row.status == "pending" and row.claimed_at and now - row.claimed_at < CLAIM_TTL)


def main(argv=None, *, provider=None, sleep=time.sleep) -> dict:
    parser = argparse.ArgumentParser(description="Tag seeded books' chunks with themes.")
    parser.add_argument("--book", type=int, help="limit to one book by database id")
    parser.add_argument("--limit", type=int, help="stop after tagging this many chunks")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds to wait between calls")
    parser.add_argument("--dry-run", action="store_true", help="show what would be done, no model calls")
    args = parser.parse_args(argv)

    summary = {"tagged": 0, "failed": 0, "skipped": 0, "would_tag": 0}
    client = None
    if not args.dry_run:
        try:
            client = make_client()
        except ThemeProviderError as err:
            print(f"{err}. Set it in backend/.env and re-run, or use --dry-run.", file=sys.stderr)
            return {"error": str(err)}

    db = SessionLocal()
    try:
        chunks = select_chunks(db, args.book)
        now = dt.datetime.utcnow()
        todo: list[MicroSession] = []
        for chunk in chunks:
            row = db.get(MicroSessionTagging, chunk.id)
            if _live_claim(row, now) or not themes.needs_tagging(db, chunk.id):
                summary["skipped"] += 1
            else:
                todo.append(chunk)
        if args.limit is not None:
            todo = todo[: args.limit]

        if args.dry_run:
            summary["would_tag"] = len(todo)
            print(
                f"{len(chunks)} chunks in scope, {summary['skipped']} already tagged, "
                f"{len(todo)} to tag (about {len(todo) * TOKENS_PER_CHUNK:,} tokens, "
                f"model {settings.llm_model or '(model not set)'}). No calls made."
            )
            return summary

        print(f"Tagging {len(todo)} chunks with {settings.llm_provider}:{settings.llm_model} ...", flush=True)
        streak = 0
        try:
            for n, chunk in enumerate(todo, 1):
                status = themes.tag_chunk(db, chunk, client=client, provider=provider)
                summary["tagged" if status == "done" else "failed"] += 1
                streak = 0 if status == "done" else streak + 1
                title = chunk.chapter.book.title
                print(f"  [{title}] {n}/{len(todo)} (chunk {chunk.id}: {status})", flush=True)
                if streak >= MAX_CONSECUTIVE_FAILURES:
                    summary["aborted"] = True
                    print(f"Stopping: {streak} chunks in a row failed. Check the key, credit and model, then re-run.")
                    break
                if n < len(todo):
                    sleep(args.delay)
        except Exception as err:  # noqa: BLE001 - report what was done, then stop
            db.rollback()
            summary["error"] = type(err).__name__
            print(f"Stopped by an unexpected error ({type(err).__name__}). Re-run to resume.", file=sys.stderr)
        print(f"Done. tagged={summary['tagged']} failed={summary['failed']} skipped={summary['skipped']}")
        return summary
    finally:
        db.close()
        if client is not None:
            client.close()


if __name__ == "__main__":
    result = main()
    sys.exit(1 if "error" in result else 0)
