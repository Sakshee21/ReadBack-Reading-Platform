"""Write a random sample of chunks for two human coders to label with themes.

The LLM's tags are deliberately not in the file, so the coders stay independent.
Each coder fills theme_1..theme_3 (ids from the closed list, at most 3, blank if
no clear theme). Afterwards run scripts/theme_agreement.py.

Usage:
    python -m scripts.theme_sample --out theme_sample.csv --n 60
    (give each coder their own copy of the file)
"""

import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import Book  # noqa: E402
from app.services import themes  # noqa: E402
from app.services.progression import ordered_micro_sessions  # noqa: E402

COLUMNS = ["micro_session_id", "book", "text", "theme_1", "theme_2", "theme_3"]


def sample_chunks(db, n: int = 60, seed: int = 7, book_ids: list[int] | None = None) -> list[dict]:
    """A seeded sample spread evenly over seeded books (never uploads)."""
    query = db.query(Book).filter(Book.owner_user_id.is_(None), Book.is_user_uploaded.is_(False), Book.status == "ready").order_by(Book.id)
    if book_ids is not None:
        query = query.filter(Book.id.in_(book_ids))
    books = query.all()
    if not books:
        return []
    rng = random.Random(seed)
    per_book = [n // len(books) + (1 if i < n % len(books) else 0) for i in range(len(books))]
    rows: list[dict] = []
    for book, quota in zip(books, per_book):
        chunks = ordered_micro_sessions(book)
        for chunk in sorted(rng.sample(chunks, min(quota, len(chunks))), key=lambda c: c.id):
            rows.append({"micro_session_id": chunk.id, "book": book.title, "book_id": book.id, "text": chunk.text})
    return rows


def write_sample_csv(rows: list[dict], path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([row["micro_session_id"], row["book"], row["text"], "", "", ""])


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Write a coder sample of chunks.")
    parser.add_argument("--n", type=int, default=60)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="theme_sample.csv")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        rows = sample_chunks(db, args.n, args.seed)
    finally:
        db.close()
    write_sample_csv(rows, args.out)
    print(f"Wrote {len(rows)} chunks to {args.out}. Theme ids: {', '.join(themes.THEMES)}")


if __name__ == "__main__":
    main()
