"""Content pipeline: pull a book from Project Gutenberg (via Gutendex for
metadata, raw Gutenberg text for content), strip boilerplate, segment into
chapters and micro-sessions, and persist it.

Usage:
    python -m scripts.import_book <gutenberg_id>
"""

import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Book, Chapter, MicroSession  # noqa: E402
from app.services.segmentation import (  # noqa: E402
    split_into_chapters,
    split_into_micro_sessions,
    strip_boilerplate,
    word_count,
)
from app.services.summarize import naive_summary  # noqa: E402

GUTENDEX_URL = "https://gutendex.com/books/{id}/"
HEADING_LINE_RE = re.compile(r"^\s*(CHAPTER|Chapter|Letter)\b[^\n]*\n?")


def fetch_metadata(gutenberg_id: int) -> dict:
    resp = httpx.get(GUTENDEX_URL.format(id=gutenberg_id), timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def fetch_text(metadata: dict) -> str:
    formats = metadata.get("formats", {})
    text_url = next(
        (url for mime, url in formats.items() if mime.startswith("text/plain") and "zip" not in mime),
        None,
    )
    if not text_url:
        raise RuntimeError(f"No plain-text format available for book {metadata.get('id')}")
    resp = httpx.get(text_url, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    # Gutenberg plain-text files are UTF-8; httpx's guessed encoding (from
    # headers/chardet) is sometimes wrong and mangles smart quotes/em-dashes,
    # so decode explicitly rather than trusting resp.text.
    return resp.content.decode("utf-8").replace("\r\n", "\n")


def _fallback_summary(chapter_text: str) -> str:
    body = HEADING_LINE_RE.sub("", chapter_text, count=1)
    return naive_summary(body)


def import_book(
    gutenberg_id: int,
    chapter_summaries: dict[int, str] | None = None,
    title_override: str | None = None,
    author_override: str | None = None,
) -> int:
    chapter_summaries = chapter_summaries or {}
    db = SessionLocal()
    try:
        existing = db.query(Book).filter(Book.gutenberg_id == gutenberg_id).first()
        if existing:
            print(f"Book {gutenberg_id} ({existing.title}) already imported, skipping.")
            return existing.id

        metadata = fetch_metadata(gutenberg_id)
        raw_text = fetch_text(metadata)
        clean_text = strip_boilerplate(raw_text)
        chapters_data = split_into_chapters(clean_text)

        title = title_override or metadata.get("title", f"Gutenberg #{gutenberg_id}")
        authors = metadata.get("authors") or []
        author = author_override or (authors[0]["name"] if authors else "Unknown")

        book = Book(
            gutenberg_id=gutenberg_id,
            title=title,
            author=author,
            full_text=clean_text,
            total_word_count=word_count(clean_text),
        )
        db.add(book)
        db.flush()

        for idx, chapter_data in enumerate(chapters_data):
            summary = chapter_summaries.get(idx) or _fallback_summary(chapter_data["text"])
            chapter = Chapter(
                book_id=book.id,
                index=idx,
                title=chapter_data["title"],
                text=chapter_data["text"],
                word_count=word_count(chapter_data["text"]),
                summary=summary,
            )
            db.add(chapter)
            db.flush()

            micro_sessions = split_into_micro_sessions(
                chapter_data["text"],
                min_words=settings.micro_session_min_words,
                max_words=settings.micro_session_max_words,
            )
            for ms_data in micro_sessions:
                db.add(
                    MicroSession(
                        chapter_id=chapter.id,
                        index=ms_data["index"],
                        text=ms_data["text"],
                        word_count=ms_data["word_count"],
                        is_cliffhanger_break=ms_data["is_cliffhanger_break"],
                        has_visualization_prompt=ms_data["has_visualization_prompt"],
                    )
                )

        db.commit()
        print(f"Imported '{title}' by {author} ({len(chapters_data)} chapters)")
        return book.id
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.import_book <gutenberg_id>")
        sys.exit(1)
    import_book(int(sys.argv[1]))
