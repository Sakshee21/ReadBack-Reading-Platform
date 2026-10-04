"""Generate spoiler-safe chapter recaps with Groq, cached at seed time.

The running app NEVER calls an LLM - this script fills Chapter.recap_text and
Chapter.story_so_far once, and the API serves the cached text.

Long chapters are summarised map-reduce style (summarise each chunk, then
combine) so a single request stays inside free-tier per-request and per-minute
token limits. Progress is committed after every chapter, so an interrupted or
rate-limited run can simply be re-run: it skips chapters that already have a
recap unless --force is passed.

Usage:
    python -m scripts.generate_recaps                 # all books, skip done
    python -m scripts.generate_recaps --book 11       # one book (gutenberg id)
    python -m scripts.generate_recaps --force         # regenerate everything
    python -m scripts.generate_recaps --dry-run       # no API calls, show plan
"""

import argparse
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Book, Chapter  # noqa: E402
from app.services.recap import effective_recap  # noqa: E402

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

CHUNK_WORDS = 1800
MAX_RETRIES = 6
REVIEW_PATH = Path(__file__).resolve().parents[1] / "recaps_review.md"

SPOILER_RULES = (
    "Only describe what actually happens in the text provided. "
    "Do not invent details, do not add interpretation or literary analysis, and do not "
    "use any outside knowledge of this book. Never mention events that happen later."
)


def chunk_text(text: str, chunk_words: int = CHUNK_WORDS) -> list[str]:
    """Split a chapter into word-count chunks on paragraph boundaries so each
    Groq request stays well inside free-tier token limits."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for para in paragraphs:
        words = len(para.split())
        if current and count + words > chunk_words:
            chunks.append("\n\n".join(current))
            current, count = [], 0
        current.append(para)
        count += words
    if current:
        chunks.append("\n\n".join(current))
    return chunks


class GroqError(RuntimeError):
    pass


def groq_chat(client: httpx.Client, prompt: str, *, model: str, api_key: str,
              max_tokens: int = 350, delay: float = 1.0) -> str:
    """One chat completion with exponential backoff on rate limits / transient
    errors. Honours Retry-After when Groq sends it."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You write concise, factual recaps of book chapters. " + SPOILER_RULES},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    backoff = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.post(GROQ_URL, json=payload, headers=headers, timeout=120)
        except httpx.RequestError as exc:
            if attempt == MAX_RETRIES:
                raise GroqError(f"network error after {attempt} attempts: {exc}") from exc
            time.sleep(backoff)
            backoff *= 2
            continue

        if resp.status_code == 200:
            time.sleep(delay)  # be polite between calls
            return resp.json()["choices"][0]["message"]["content"].strip()

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == MAX_RETRIES:
                raise GroqError(f"giving up after {attempt} attempts: {resp.status_code} {resp.text[:200]}")
            wait = float(resp.headers.get("retry-after", backoff))
            print(f"    rate limited ({resp.status_code}), waiting {wait:.0f}s "
                  f"(attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            backoff *= 2
            continue

        raise GroqError(f"{resp.status_code} {resp.text[:300]}")

    raise GroqError("exhausted retries")


def summarize_chapter(client, chapter: Chapter, *, model, api_key, delay) -> str:
    """Map-reduce: summarise each chunk, then fold the chunk summaries into a
    2-3 sentence chapter recap."""
    chunks = chunk_text(chapter.text)
    if not chunks:
        return ""

    if len(chunks) == 1:
        prompt = (
            f"Write a 2-3 sentence recap of this chapter of a novel. {SPOILER_RULES}\n\n"
            f"CHAPTER TEXT:\n{chunks[0]}"
        )
        return groq_chat(client, prompt, model=model, api_key=api_key, delay=delay)

    print(f"    {len(chunks)} chunks")
    partials = []
    for i, chunk in enumerate(chunks, 1):
        prompt = (
            f"Summarise this passage (part {i} of {len(chunks)} of one chapter) in 2 sentences. "
            f"{SPOILER_RULES}\n\nPASSAGE:\n{chunk}"
        )
        partials.append(groq_chat(client, prompt, model=model, api_key=api_key,
                                  max_tokens=200, delay=delay))

    joined = "\n".join(f"- {p}" for p in partials)
    prompt = (
        "These are ordered summaries of consecutive passages from a single chapter. "
        f"Combine them into one 2-3 sentence recap of the whole chapter. {SPOILER_RULES}\n\n"
        f"PASSAGE SUMMARIES:\n{joined}"
    )
    return groq_chat(client, prompt, model=model, api_key=api_key, delay=delay)


def build_story_so_far(client, prior_recaps: list[str], *, model, api_key, delay) -> str:
    """A 'story so far' for long gaps, built from the PREVIOUS chapters' recaps
    rather than the full text (cheap, and inherently spoiler-safe)."""
    if not prior_recaps:
        return ""
    joined = "\n".join(f"- {r}" for r in prior_recaps)
    prompt = (
        "These are recaps of the chapters a reader has already finished, in order. "
        "Write a 2-3 sentence 'story so far' that reminds them where things stand. "
        f"{SPOILER_RULES}\n\nCHAPTER RECAPS:\n{joined}"
    )
    return groq_chat(client, prompt, model=model, api_key=api_key, delay=delay)


def write_review_export(db) -> Path:
    """A reviewable dump so the team can hand-check every generated recap."""
    lines = [
        "# Generated recaps - review sheet",
        "",
        "`recap_source` precedence is manual > llm > extractive.",
        "Check each LLM recap for spoilers, invented details, and outside knowledge.",
        "",
    ]
    for book in db.query(Book).order_by(Book.title).all():
        lines.append(f"## {book.title} - {book.author}")
        lines.append("")
        for ch in sorted(book.chapters, key=lambda c: c.index):
            title = ch.title or f"Chapter {ch.index + 1}"
            lines.append(f"### [{ch.index}] {title}  _(source: {ch.recap_source})_")
            lines.append("")
            lines.append(f"**Recap:** {ch.recap_text or '_(none - using ' + ch.recap_source + ')_'}")
            lines.append("")
            if ch.story_so_far:
                lines.append(f"**Story so far:** {ch.story_so_far}")
                lines.append("")
        lines.append("")
    REVIEW_PATH.write_text("\n".join(lines), encoding="utf-8")
    return REVIEW_PATH


def main():
    parser = argparse.ArgumentParser(description="Generate cached chapter recaps via Groq.")
    parser.add_argument("--book", type=int, help="limit to one book by Gutenberg id")
    parser.add_argument("--force", action="store_true", help="regenerate recaps that already exist")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds to wait between API calls")
    parser.add_argument("--dry-run", action="store_true", help="show what would be generated, no API calls")
    args = parser.parse_args()

    api_key = settings.groq_api_key
    if not api_key and not args.dry_run:
        print(
            "GROQ_API_KEY is not set.\n"
            "Add it to backend/.env (see .env.example) and re-run, or use --dry-run.\n"
            "The app keeps working without it - recaps fall back to extractive summaries.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = SessionLocal()
    try:
        books = db.query(Book).order_by(Book.id)
        if args.book:
            books = books.filter(Book.gutenberg_id == args.book)
        books = books.all()
        if not books:
            print("No books found. Run `python -m scripts.seed_books` first.")
            sys.exit(1)

        client = httpx.Client()
        for book in books:
            print(f"\n{book.title}")
            chapters = sorted(book.chapters, key=lambda c: c.index)
            for ch in chapters:
                label = ch.title or f"Chapter {ch.index + 1}"
                if ch.recap_text and not args.force:
                    print(f"  [{ch.index}] {label}: already done, skipping")
                    continue
                if args.dry_run:
                    print(f"  [{ch.index}] {label}: would generate "
                          f"({len(chunk_text(ch.text))} chunk(s), {ch.word_count} words)")
                    continue

                print(f"  [{ch.index}] {label}: generating")
                try:
                    recap = summarize_chapter(client, ch, model=settings.groq_model,
                                              api_key=api_key, delay=args.delay)
                    prior = [effective_recap(c) for c in chapters if c.index < ch.index]
                    prior = [p for p in prior if p]
                    story = build_story_so_far(client, prior, model=settings.groq_model,
                                               api_key=api_key, delay=args.delay)
                except GroqError as exc:
                    # Never crash halfway - everything before this chapter is
                    # already committed, so re-running resumes here.
                    print(f"\nStopped at chapter {ch.index}: {exc}", file=sys.stderr)
                    print("Progress is saved; re-run the same command to resume.", file=sys.stderr)
                    sys.exit(2)

                ch.recap_text = recap
                ch.story_so_far = story or None
                if ch.recap_source != "manual":
                    ch.recap_source = "llm"
                db.commit()  # save progress after EVERY chapter

        path = write_review_export(db)
        print(f"\nDone. Review the output by hand: {path}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
