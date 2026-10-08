"""Put the database into a known-good state for a live demo.

Re-runnable: run it before each rehearsal and again right before the real thing.

What it does:
  --clean        remove throwaway test accounts and all their rows, so the CSV
                 export shows only real activity
  (always)       reset the demo account to a state where every feature can be
                 shown in one pass:
                   - streak = 2, last read yesterday
                       -> library shows the "streak at risk" nudge
                       -> completing one session hits 3 = milestone celebration
                   - session_size_level = 1 (short sessions, quick to demo)
                   - quiz attempts cleared, so checkpoints fire again
                   - Alice positioned one session before its quiz, with the
                     last-read timestamp backdated so the recap banner appears

Usage:
    python -m scripts.demo_setup --email you@example.com --clean
    python -m scripts.demo_setup --email you@example.com          # keep test data
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Book,
    CheckpointAttempt,
    ComprehensionCheckpoint,
    ReadingEvent,
    ReadingSession,
    User,
    UserBookProgress,
)
from app.services.progression import ordered_micro_sessions  # noqa: E402

# Accounts created by automated verification runs.
TEST_PREFIXES = (
    "smoke_", "prog_", "recap_", "viz_", "viz2_", "viz3_", "quiz_", "pace_",
    "nudge_", "final_", "q_", "uievents_", "live_", "demo_",
)

ALICE_GUTENBERG_ID = 11


def clean_test_accounts(db) -> int:
    users = [u for u in db.query(User).all() if u.email.startswith(TEST_PREFIXES)]
    ids = [u.id for u in users]
    if not ids:
        print("  no test accounts to remove")
        return 0

    # children first - these tables all reference users.id
    for model in (ReadingEvent, CheckpointAttempt, ReadingSession, UserBookProgress):
        db.query(model).filter(model.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    print(f"  removed {len(ids)} test accounts and their rows")
    return len(ids)


def reset_demo_user(db, email: str) -> None:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        print(f"No account '{email}'. Register it in the app first.", file=sys.stderr)
        sys.exit(1)

    today = dt.datetime.utcnow().date()

    # Streak of 2 finished yesterday: the library nudge fires now, and the next
    # completed session takes it to 3 - a milestone celebration.
    user.current_streak = 2
    user.longest_streak = max(user.longest_streak, 5)
    user.last_read_date = today - dt.timedelta(days=1)
    user.session_size_level = 1

    # Let every quiz fire again.
    removed = db.query(CheckpointAttempt).filter(CheckpointAttempt.user_id == user.id).delete(
        synchronize_session=False
    )

    # Park Alice one session before its comprehension checkpoint, and backdate
    # the read so the "Previously..." recap shows on arrival.
    alice = db.query(Book).filter(Book.gutenberg_id == ALICE_GUTENBERG_ID).first()
    quiz_target = None
    if alice:
        checkpoint = db.query(ComprehensionCheckpoint).filter_by(book_id=alice.id).first()
        ordered = ordered_micro_sessions(alice)
        if checkpoint:
            for i, ms in enumerate(ordered):
                if ms.chapter.index == checkpoint.chapter_index_trigger and ms.index == 0:
                    quiz_target = i  # 0-based: the session *before* the quiz
                    break
        if quiz_target:
            before = ordered[quiz_target - 1]
            progress = (
                db.query(UserBookProgress)
                .filter_by(user_id=user.id, book_id=alice.id)
                .first()
            )
            if not progress:
                progress = UserBookProgress(user_id=user.id, book_id=alice.id)
                db.add(progress)
            progress.current_chapter_id = before.chapter_id
            progress.current_micro_session_id = before.id
            progress.last_read_at = dt.datetime.utcnow() - dt.timedelta(hours=30)

    db.commit()

    print(f"  {email}: streak=2 (last read yesterday), session_size_level=1")
    print(f"  cleared {removed} quiz attempt(s)")
    if quiz_target:
        print(f"  Alice parked at Session_{quiz_target} - press Continue to trigger the quiz")


def main():
    parser = argparse.ArgumentParser(description="Reset the database for a demo.")
    parser.add_argument("--email", required=True, help="the account you'll demo with")
    parser.add_argument("--clean", action="store_true", help="also delete throwaway test accounts")
    parser.add_argument("--wipe-events", action="store_true",
                        help="delete ALL reading_events, including the demo account's")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("Demo setup")
        if args.clean:
            clean_test_accounts(db)
        if args.wipe_events:
            n = db.query(ReadingEvent).delete(synchronize_session=False)
            db.commit()
            print(f"  wiped {n} reading_events")
        reset_demo_user(db, args.email)

        print("\nReady. Start the servers, then follow DEMO.md.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
