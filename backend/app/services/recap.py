"""Rule-based "Previously..." recap engine (MVP: no LLM calls).

Builds a short recap from pre-written per-chapter summaries, deterministically
selecting the last few chapters leading up to the reader's current position.
"""

import datetime as dt

MAX_RECAP_CHAPTERS = 3


def needs_recap(last_read_at: dt.datetime | None, now: dt.datetime, gap_hours: int) -> bool:
    if last_read_at is None:
        return False
    return (now - last_read_at) >= dt.timedelta(hours=gap_hours)


def build_recap(chapter_summaries: list[str], current_chapter_index: int) -> str:
    """chapter_summaries is ordered by chapter index (0-based), summary may be
    empty string if none was authored for that chapter."""
    prior = [s for s in chapter_summaries[:current_chapter_index] if s]
    if not prior:
        return ""
    selected = prior[-MAX_RECAP_CHAPTERS:]
    return "Previously... " + " ".join(selected)
