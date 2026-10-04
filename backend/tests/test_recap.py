import datetime as dt
from types import SimpleNamespace

from app.services.recap import (
    build_recap,
    choose_recap,
    effective_recap,
    needs_recap,
)
from scripts.generate_recaps import chunk_text


def _ch(summary="", recap_text=None, story_so_far=None, recap_source="extractive"):
    return SimpleNamespace(
        summary=summary,
        recap_text=recap_text,
        story_so_far=story_so_far,
        recap_source=recap_source,
    )


# --- source precedence: manual > llm > extractive ---


def test_manual_beats_llm():
    ch = _ch(summary="hand written", recap_text="llm written", recap_source="manual")
    assert effective_recap(ch) == "hand written"


def test_llm_beats_extractive():
    ch = _ch(summary="first sentence extract", recap_text="llm written", recap_source="llm")
    assert effective_recap(ch) == "llm written"


def test_falls_back_to_extractive():
    ch = _ch(summary="first sentence extract")
    assert effective_recap(ch) == "first sentence extract"


def test_empty_chapter_recap():
    assert effective_recap(_ch()) == ""


# --- recap selection ---


def test_build_recap_uses_last_three_chapters():
    recap = build_recap(["a", "b", "c", "d", "e"], current_chapter_index=4)
    assert recap == "Previously... b c d"


def test_no_recap_for_first_chapter():
    assert build_recap(["a", "b"], current_chapter_index=0) == ""


def test_long_gap_prefers_story_so_far():
    chapters = [_ch(summary="one"), _ch(summary="two"), _ch(summary="three", story_so_far="the gist")]
    recap = choose_recap(chapters, 2, hours_since_last_read=200, long_gap_hours=168)
    assert recap == "Previously... the gist"


def test_short_gap_uses_recent_chapters():
    chapters = [_ch(summary="one"), _ch(summary="two"), _ch(summary="three", story_so_far="the gist")]
    recap = choose_recap(chapters, 2, hours_since_last_read=30, long_gap_hours=168)
    assert recap == "Previously... one two"


def test_long_gap_without_story_falls_back():
    chapters = [_ch(summary="one"), _ch(summary="two")]
    recap = choose_recap(chapters, 1, hours_since_last_read=500, long_gap_hours=168)
    assert recap == "Previously... one"


def test_needs_recap_threshold():
    now = dt.datetime(2026, 1, 2, 12, 0)
    assert needs_recap(now - dt.timedelta(hours=25), now, 24) is True
    assert needs_recap(now - dt.timedelta(hours=2), now, 24) is False
    assert needs_recap(None, now, 24) is False


# --- map-reduce chunking for the Groq script ---


def test_chunk_text_keeps_short_chapter_whole():
    text = "para one.\n\npara two."
    assert chunk_text(text, chunk_words=100) == [text]


def test_chunk_text_splits_on_paragraph_boundaries():
    para = " ".join(["word"] * 60)
    chunks = chunk_text("\n\n".join([para] * 4), chunk_words=100)
    assert len(chunks) == 4
    # never splits mid-paragraph
    assert all(c == para for c in chunks)


def test_chunk_text_packs_paragraphs_up_to_limit():
    para = " ".join(["word"] * 30)
    chunks = chunk_text("\n\n".join([para] * 4), chunk_words=100)
    assert len(chunks) == 2
    assert chunks[0].count("\n\n") == 2  # three paragraphs = 90 words


def test_chunk_text_empty():
    assert chunk_text("") == []
