"""Download public-domain books used to exercise chapter detection.

These books are NOT seed content - they only exist so tests can check the
segmentation heuristics against real-world chapter conventions. The text is
cached under tests/fixtures/books/ and gitignored (we don't commit books in
bulk); tests that need it skip when the cache is absent.

Usage:
    python -m scripts.fetch_test_books
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "books"

# Deliberately varied chapter conventions, so detection is tested against more
# than just "CHAPTER I".
TEST_BOOKS = {
    345: "Dracula (CHAPTER I, roman)",
    2701: "Moby Dick (CHAPTER 1. Title, arabic)",
    1260: "Jane Eyre (CHAPTER I, roman)",
    1661: "The Adventures of Sherlock Holmes (ADVENTURE I., no 'chapter' keyword)",
    5200: "Metamorphosis (bare roman numerals I, II, III)",
    98: "A Tale of Two Cities (Books plus 'I. The Period')",
}

TEXT_URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"


def fetch(gutenberg_id: int) -> Path:
    path = FIXTURE_DIR / f"{gutenberg_id}.txt"
    if path.exists():
        print(f"  {gutenberg_id}: cached")
        return path
    resp = httpx.get(TEXT_URL.format(id=gutenberg_id), timeout=120, follow_redirects=True)
    resp.raise_for_status()
    text = resp.content.decode("utf-8", errors="replace").replace("\r\n", "\n")
    path.write_text(text, encoding="utf-8")
    print(f"  {gutenberg_id}: downloaded ({len(text.split()):,} words)")
    return path


def main():
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Caching test books in {FIXTURE_DIR}")
    for gutenberg_id, label in TEST_BOOKS.items():
        try:
            fetch(gutenberg_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  {gutenberg_id}: FAILED ({exc}) - {label}")
    print("Done.")


if __name__ == "__main__":
    main()
