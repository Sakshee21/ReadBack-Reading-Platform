"""Attach curated, public-domain artwork to visualization checkpoints.

There is NO image generation here and none at request time: every pilot user
sees exactly the same images. A JSON manifest maps each flagged micro-session
to an image (remote URL or a local file the team dropped in), and this script
fetches, validates and records it.

A session is identified by (book_gutenberg_id, chapter_index, micro_session_index)
so the manifest survives a re-import.

Usage:
    python -m scripts.visualization_images --init          # write/refresh manifest
    python -m scripts.visualization_images --autofill 74   # fill from Gutenberg illustrations
    python -m scripts.visualization_images --apply         # download, validate, store
    python -m scripts.visualization_images --apply --force # re-download existing files
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import Book, MicroSession  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = BACKEND_DIR / "data" / "visualization_manifest.json"
IMAGE_DIR = BACKEND_DIR / "static" / "visualizations"

MIN_BYTES = 1024
MAX_BYTES = 8 * 1024 * 1024

# Magic bytes -> extension. Used to confirm a download really is an image.
MAGIC = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"GIF87a": ".gif",
    b"GIF89a": ".gif",
}

README = (
    "Curated public-domain artwork for visualization checkpoints. "
    "Fill source_url (or local_file, relative to backend/), alt and attribution, "
    "then set status to 'verified' and run: python -m scripts.visualization_images --apply. "
    "Entries with status 'TODO' are skipped. Never put a URL here you have not opened yourself."
)


def detect_image_type(data: bytes) -> str | None:
    for magic, ext in MAGIC.items():
        if data.startswith(magic):
            return ext
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return None


def entry_key(e: dict) -> tuple:
    return (e["book_gutenberg_id"], e["chapter_index"], e["micro_session_index"])


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"_readme": README, "entries": []}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest["_readme"] = README
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def flagged_sessions(db):
    """Every micro-session flagged for a visualization prompt, in book order."""
    rows = []
    for book in db.query(Book).order_by(Book.id).all():
        for chapter in sorted(book.chapters, key=lambda c: c.index):
            for ms in sorted(chapter.micro_sessions, key=lambda m: m.index):
                if ms.has_visualization_prompt:
                    rows.append((book, chapter, ms))
    return rows


def cmd_init(db) -> None:
    """Create a manifest entry for every flagged session, keeping any entries
    the team has already filled in."""
    manifest = load_manifest()
    existing = {entry_key(e): e for e in manifest["entries"]}

    entries = []
    added = 0
    for book, chapter, ms in flagged_sessions(db):
        key = (book.gutenberg_id, chapter.index, ms.index)
        if key in existing:
            entries.append(existing[key])
            continue
        added += 1
        entries.append(
            {
                "book_gutenberg_id": book.gutenberg_id,
                "book_title": book.title,
                "chapter_index": chapter.index,
                "micro_session_index": ms.index,
                # a hint so whoever curates knows what scene this is
                "excerpt": " ".join(ms.text.split()[:25]),
                "source_url": "",
                "local_file": "",
                "alt": "",
                "attribution": "",
                "license": "",
                "status": "TODO",
            }
        )

    manifest["entries"] = entries
    save_manifest(manifest)
    todo = sum(1 for e in entries if e["status"] != "verified")
    print(f"Manifest: {len(entries)} flagged sessions ({added} new), {todo} still TODO")
    print(f"  {MANIFEST_PATH}")


GUTENBERG_HTML = "https://www.gutenberg.org/cache/epub/{id}/pg{id}-images.html"
CHAPTER_IMAGE_RE = re.compile(r'src="(images/(\d{2})-[^"]+\.(?:jpg|jpeg|png))"', re.IGNORECASE)


def cmd_autofill(db, gutenberg_id: int) -> None:
    """Fill entries for one book from its Project Gutenberg illustrated edition.

    Only works for editions whose illustrations are named ``NN-xxx.jpg`` where
    NN is the chapter number - we map chapter N to chapter_index N-1. Anything
    we can't match confidently is left TODO rather than guessed.
    """
    url = GUTENBERG_HTML.format(id=gutenberg_id)
    print(f"Fetching {url}")
    resp = httpx.get(url, timeout=60, follow_redirects=True)
    resp.raise_for_status()

    by_chapter: dict[int, list[str]] = {}
    for rel, chap in CHAPTER_IMAGE_RE.findall(resp.text):
        by_chapter.setdefault(int(chap), []).append(
            f"https://www.gutenberg.org/cache/epub/{gutenberg_id}/{rel}"
        )
    if not by_chapter:
        print("No chapter-numbered illustrations found; leaving entries TODO.")
        return

    book = db.query(Book).filter(Book.gutenberg_id == gutenberg_id).first()
    if not book:
        print(f"Book {gutenberg_id} not in the database.")
        return

    manifest = load_manifest()
    used: set[str] = {e["source_url"] for e in manifest["entries"] if e.get("source_url")}
    filled = 0
    for entry in manifest["entries"]:
        if entry["book_gutenberg_id"] != gutenberg_id or entry["status"] == "verified":
            continue
        candidates = by_chapter.get(entry["chapter_index"] + 1, [])
        pick = next((u for u in candidates if u not in used), None)
        if not pick:
            continue
        used.add(pick)
        entry["source_url"] = pick
        entry["alt"] = (
            f"Original illustration from {book.title}, chapter {entry['chapter_index'] + 1}"
        )
        entry["attribution"] = f"Illustration from the Project Gutenberg edition of {book.title}"
        entry["license"] = "Public domain"
        # Auto-matched by chapter, not eyeballed - a human still confirms the
        # picture suits this particular scene.
        entry["status"] = "needs_review"
        filled += 1

    save_manifest(manifest)
    print(f"Auto-filled {filled} entries for book {gutenberg_id} (status 'needs_review').")
    print("Review them, then set status to 'verified' to apply.")


def _fetch(entry: dict) -> bytes:
    if entry.get("local_file"):
        src = (BACKEND_DIR / entry["local_file"]).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"local_file not found: {src}")
        return src.read_bytes()
    resp = httpx.get(entry["source_url"], timeout=60, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def cmd_apply(db, force: bool) -> None:
    manifest = load_manifest()
    entries = {entry_key(e): e for e in manifest["entries"]}
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    applied = skipped = failed = 0
    for book, chapter, ms in flagged_sessions(db):
        entry = entries.get((book.gutenberg_id, chapter.index, ms.index))
        if not entry or entry.get("status") != "verified":
            skipped += 1
            continue
        if not entry.get("source_url") and not entry.get("local_file"):
            skipped += 1
            continue
        if ms.visualization_image and not force:
            skipped += 1
            continue

        stem = f"{book.gutenberg_id}-c{chapter.index:03d}-s{ms.index:02d}"
        try:
            data = _fetch(entry)
            ext = detect_image_type(data)
            if ext is None:
                raise ValueError("not a recognised image (jpeg/png/gif/webp)")
            if not (MIN_BYTES <= len(data) <= MAX_BYTES):
                raise ValueError(f"unreasonable size: {len(data)} bytes")

            path = IMAGE_DIR / f"{stem}{ext}"
            path.write_bytes(data)
            ms.visualization_image = f"visualizations/{path.name}"
            ms.visualization_alt = entry.get("alt") or None
            ms.visualization_attribution = entry.get("attribution") or None
            db.commit()
            applied += 1
            print(f"  ok   {stem}{ext}  ({len(data) // 1024}KB)")
        except Exception as exc:  # noqa: BLE001 - report and continue
            failed += 1
            print(f"  FAIL {stem}: {exc}")

    print(f"\nApplied {applied}, skipped {skipped} (not verified / already done), failed {failed}.")
    if applied:
        print(f"Images in {IMAGE_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Curated visualization artwork pipeline.")
    parser.add_argument("--init", action="store_true", help="write/refresh the manifest skeleton")
    parser.add_argument("--autofill", type=int, metavar="GUTENBERG_ID",
                        help="fill one book's entries from its Gutenberg illustrated edition")
    parser.add_argument("--apply", action="store_true", help="download, validate and store verified images")
    parser.add_argument("--force", action="store_true", help="re-download images already attached")
    args = parser.parse_args()

    if not (args.init or args.autofill or args.apply):
        parser.error("choose one of --init, --autofill or --apply")

    db = SessionLocal()
    try:
        if args.init:
            cmd_init(db)
        if args.autofill:
            cmd_autofill(db, args.autofill)
        if args.apply:
            cmd_apply(db, args.force)
    finally:
        db.close()


if __name__ == "__main__":
    main()
