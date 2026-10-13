"""Convert extracted text into stored chapters and micro-sessions.

This reuses the existing Gutenberg pipeline wholesale - the same
`split_into_chapters`, `split_into_micro_sessions` and `naive_summary` the seed
script uses - so an uploaded book behaves exactly like a seeded one in the
reader. The only difference is where the text came from.

Uploaded books get extractive recaps (no LLM at upload time, ever) and no
comprehension quizzes or visualization prompts, because those are hand-authored
per book offline.
"""

from app.config import settings
from app.models import Book, Chapter, MicroSession
from app.services.frontmatter import STORY, classify_sections
from app.services.segmentation import (
    split_into_chapters,
    split_into_fixed_sections,
    split_into_micro_sessions,
    word_count,
)
from app.services.summarize import naive_summary


def plan_chapters(full_text: str, source_chapters: list[dict] | None = None) -> list[dict]:
    """Decide the chapter breakdown for a book.

    EPUBs carry their own chapter structure, which beats guessing, so it wins
    when present. Everything else goes through the heuristic detector, which
    already falls back to fixed-size sections for a long book whose headings it
    can't find.
    """
    if source_chapters:
        usable = [c for c in source_chapters if c.get("text", "").strip()]
        if len(usable) > 1:
            return usable

    chapters = split_into_chapters(full_text)
    if len(chapters) <= 1 and word_count(full_text) > settings.micro_session_max_words * 4:
        # One enormous chapter means detection found nothing. Even sections are
        # a better reading experience than a single unbroken block.
        return split_into_fixed_sections(full_text)
    return chapters


def persist_book_content(db, book: Book, chapters_data: list[dict]) -> tuple[int, int, int]:
    """Write chapters and micro-sessions. Returns (chapters, sessions, story_words).

    Front and back matter is stored with its ``section_kind`` so it can be
    inspected, but gets no micro-sessions at all - which is what keeps it out
    of the reading flow, the progress bar and the word count.
    """
    chapters_data = classify_sections(chapters_data)
    session_count = 0
    story_words = 0

    for idx, chapter_data in enumerate(chapters_data):
        text = chapter_data["text"]
        kind = chapter_data.get("section_kind", STORY)
        chapter = Chapter(
            book_id=book.id,
            index=idx,
            title=(chapter_data.get("title") or "")[:500],
            text=text,
            word_count=word_count(text),
            summary=naive_summary(text) if kind == STORY else "",
            recap_source="extractive",
            section_kind=kind,
        )
        db.add(chapter)
        db.flush()

        if kind != STORY:
            continue  # no reading sessions, no story flags

        story_words += word_count(text)
        for ms in split_into_micro_sessions(
            text,
            min_words=settings.micro_session_min_words,
            max_words=settings.micro_session_max_words,
            conservative_cliffhangers=settings.upload_conservative_cliffhangers,
            visualization_prompts=settings.upload_visualization_prompts,
            visualization_every=settings.upload_visualization_every,
            visualization_skip_edges=True,
        ):
            db.add(
                MicroSession(
                    chapter_id=chapter.id,
                    index=ms["index"],
                    text=ms["text"],
                    word_count=ms["word_count"],
                    is_cliffhanger_break=ms["is_cliffhanger_break"],
                    has_visualization_prompt=ms["has_visualization_prompt"],
                )
            )
            session_count += 1

    return len(chapters_data), session_count, story_words
