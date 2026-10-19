"""Theme tags that ship with the seeded books.

The tags are generated once (scripts/tag_themes.py), exported to a JSON file in
the repo, and imported when the books are seeded, so every fresh install has
them without calling a model. Chunks are matched by book (Gutenberg id),
chapter and session number - database ids differ between installs - plus a hash
of the passage text, so a tag is never attached to a passage that has changed.

Tags are permanent: importing never overwrites a chunk that already has tags.
"""

import hashlib
import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Book, Chapter, MicroSession, MicroSessionTagging, MicroSessionTheme
from app.services.themes import THEMES

FORMAT = 1
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "theme_tags.json"


def chunk_hash(text: str) -> str:
    """Whitespace-insensitive fingerprint of a passage."""
    return hashlib.sha256(" ".join(text.split()).encode("utf8")).hexdigest()[:16]


def _shared_books(db: Session):
    return (
        db.query(Book)
        .filter(
            Book.owner_user_id.is_(None),
            Book.is_user_uploaded.is_(False),
            Book.gutenberg_id.isnot(None),
            Book.status == "ready",
        )
        .order_by(Book.gutenberg_id)
    )


def export_tags(db: Session) -> dict:
    """Every finished tagging of the shared books, with all scores kept."""
    books = []
    for book in _shared_books(db):
        chunks = []
        for chapter in sorted(book.chapters, key=lambda c: c.index):
            for ms in sorted(chapter.micro_sessions, key=lambda m: m.index):
                tagging = db.get(MicroSessionTagging, ms.id)
                if tagging is None or tagging.status != "done":
                    continue
                rows = (
                    db.query(MicroSessionTheme)
                    .filter(MicroSessionTheme.micro_session_id == ms.id, MicroSessionTheme.source == "llm")
                    .all()
                )
                rows.sort(key=lambda r: (-r.score, r.theme))
                chunks.append(
                    {
                        "chapter": chapter.index,
                        "session": ms.index,
                        "hash": chunk_hash(ms.text),
                        "model": tagging.model,
                        "prompt_version": tagging.prompt_version,
                        "theme_list_version": tagging.theme_list_version,
                        "themes": [{"theme": r.theme, "score": r.score} for r in rows],
                    }
                )
        if chunks:
            books.append({"gutenberg_id": book.gutenberg_id, "title": book.title, "chunks": chunks})
    return {"format": FORMAT, "books": books}


def dumps(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def _valid(themes_list) -> bool:
    return isinstance(themes_list, list) and all(
        isinstance(t, dict)
        and t.get("theme") in THEMES
        and isinstance(t.get("score"), int)
        and not isinstance(t.get("score"), bool)
        and 1 <= t["score"] <= 5
        for t in themes_list
    )


def import_tags(db: Session, data: dict) -> dict:
    """Load shipped tags. Chunks that already have finished tags are left exactly
    as they are. Returns counts of what happened."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError(f"unsupported theme tag file format: {data.get('format') if isinstance(data, dict) else None!r}")
    summary = {"imported": 0, "skipped_existing": 0, "mismatched": 0, "invalid": 0, "missing_books": 0}
    for entry in data.get("books", []):
        book = _shared_books(db).filter(Book.gutenberg_id == entry.get("gutenberg_id")).first()
        if book is None:
            summary["missing_books"] += 1
            continue
        by_position = {
            (chapter.index, ms.index): ms for chapter in book.chapters for ms in chapter.micro_sessions
        }
        for item in entry.get("chunks", []):
            ms = by_position.get((item.get("chapter"), item.get("session")))
            if ms is None or item.get("hash") != chunk_hash(ms.text):
                summary["mismatched"] += 1
                continue
            existing = db.get(MicroSessionTagging, ms.id)
            if existing is not None and existing.status == "done":
                summary["skipped_existing"] += 1
                continue
            if not _valid(item.get("themes")):
                summary["invalid"] += 1
                continue
            db.query(MicroSessionTheme).filter(
                MicroSessionTheme.micro_session_id == ms.id, MicroSessionTheme.source == "llm"
            ).delete(synchronize_session=False)
            for t in item["themes"]:
                db.add(
                    MicroSessionTheme(
                        micro_session_id=ms.id,
                        theme=t["theme"],
                        score=t["score"],
                        source="llm",
                        model=item.get("model", ""),
                        prompt_version=item.get("prompt_version", 1),
                        theme_list_version=item.get("theme_list_version", 1),
                    )
                )
            tagging = existing or MicroSessionTagging(micro_session_id=ms.id)
            tagging.status = "done"
            tagging.model = item.get("model", "")
            tagging.prompt_version = item.get("prompt_version", 1)
            tagging.theme_list_version = item.get("theme_list_version", 1)
            tagging.error = None
            tagging.claimed_at = None
            db.add(tagging)
            summary["imported"] += 1
        db.commit()
    return summary


def import_file(db: Session, path: Path = DEFAULT_PATH) -> dict | None:
    """Import the shipped file if it exists; None when there is no file."""
    if not Path(path).exists():
        return None
    return import_tags(db, json.loads(Path(path).read_text(encoding="utf8")))
