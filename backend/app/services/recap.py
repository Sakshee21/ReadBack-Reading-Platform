""""Previously..." recap engine.

All recap text is generated offline and cached on the Chapter row - this module
never calls an LLM. Precedence for a chapter's recap is:

    manual (hand-authored) > llm (scripts/generate_recaps.py) > extractive

After a long absence the stitched per-chapter ``story_so_far`` is preferred over
the last-few-chapters recap, since the reader needs more context to re-enter.
"""

import datetime as dt

MAX_RECAP_CHAPTERS = 3


def needs_recap(last_read_at: dt.datetime | None, now: dt.datetime, gap_hours: int) -> bool:
    if last_read_at is None:
        return False
    return (now - last_read_at) >= dt.timedelta(hours=gap_hours)


def effective_recap(chapter) -> str:
    """The best available recap for one chapter, by source precedence."""
    if getattr(chapter, "recap_source", "") == "manual" and chapter.summary:
        return chapter.summary
    return (getattr(chapter, "recap_text", None) or chapter.summary or "").strip()


def build_recap(chapter_summaries: list[str], current_chapter_index: int) -> str:
    """chapter_summaries is ordered by chapter index (0-based), summary may be
    empty string if none was authored for that chapter."""
    prior = [s for s in chapter_summaries[:current_chapter_index] if s]
    if not prior:
        return ""
    selected = prior[-MAX_RECAP_CHAPTERS:]
    return "Previously... " + " ".join(selected)


def choose_recap(chapters: list, current_chapter_index: int, hours_since_last_read: float,
                 long_gap_hours: int) -> str:
    """Pick between the stitched "story so far" (long absence) and the recap of
    the last few chapters. ``chapters`` is ordered by chapter index."""
    if 0 <= current_chapter_index < len(chapters):
        current = chapters[current_chapter_index]
        story = (getattr(current, "story_so_far", None) or "").strip()
        if story and hours_since_last_read >= long_gap_hours:
            return "Previously... " + story
    return build_recap([effective_recap(c) for c in chapters], current_chapter_index)
