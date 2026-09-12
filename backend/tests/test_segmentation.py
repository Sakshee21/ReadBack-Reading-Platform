from app.services.segmentation import (
    split_into_chapters,
    split_into_micro_sessions,
    strip_boilerplate,
    word_count,
)

GUTENBERG_WRAPPER = """Some preamble line.
*** START OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***
{body}
*** END OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***
Some license text after.
"""


def make_paragraph(word: str, n: int) -> str:
    return " ".join([word] * n)


def test_strip_boilerplate_removes_header_and_footer():
    body = "This is the real book content."
    raw = GUTENBERG_WRAPPER.format(body=body)
    cleaned = strip_boilerplate(raw)
    assert cleaned == body
    assert "PROJECT GUTENBERG" not in cleaned
    assert "preamble" not in cleaned


def test_strip_boilerplate_is_noop_without_markers():
    text = "Just plain text with no Gutenberg markers."
    assert strip_boilerplate(text) == text


def test_split_into_chapters_finds_headings_and_titles():
    text = (
        "CHAPTER I. The Beginning\n\n"
        + make_paragraph("alpha", 30)
        + "\n\n"
        + "CHAPTER II. The Middle\n\n"
        + make_paragraph("beta", 30)
    )
    chapters = split_into_chapters(text)
    assert len(chapters) == 2
    assert chapters[0]["title"] == "The Beginning"
    assert chapters[1]["title"] == "The Middle"
    assert "alpha" in chapters[0]["text"]
    assert "beta" in chapters[1]["text"]


def test_split_into_chapters_falls_back_to_single_chapter_without_headings():
    text = make_paragraph("word", 200)
    chapters = split_into_chapters(text)
    assert len(chapters) == 1
    assert chapters[0]["title"] == ""
    assert chapters[0]["text"] == text.strip()


def test_split_into_chapters_keeps_substantial_lead_in_as_own_chapter():
    lead_in = make_paragraph("intro", 60)
    text = lead_in + "\n\nCHAPTER I.\n\n" + make_paragraph("body", 30)
    chapters = split_into_chapters(text)
    assert len(chapters) == 2
    assert "intro" in chapters[0]["text"]


def test_split_into_chapters_drops_short_lead_in():
    lead_in = "Tiny prelude."
    text = lead_in + "\n\nCHAPTER I.\n\n" + make_paragraph("body", 30)
    chapters = split_into_chapters(text)
    assert len(chapters) == 1
    assert "Tiny prelude" not in chapters[0]["text"]


def test_split_into_chapters_skips_table_of_contents_listing():
    toc = "\n".join(f"CHAPTER {i}" for i in range(1, 4))
    text = (
        toc
        + "\n\nCHAPTER 1\n\n"
        + make_paragraph("alpha", 80)
        + "\n\nCHAPTER 2\n\n"
        + make_paragraph("beta", 80)
        + "\n\nCHAPTER 3\n\n"
        + make_paragraph("gamma", 80)
    )
    chapters = split_into_chapters(text)
    assert len(chapters) == 3
    assert "alpha" in chapters[0]["text"] and "CHAPTER 2" not in chapters[0]["text"]
    assert "beta" in chapters[1]["text"]
    assert "gamma" in chapters[2]["text"]


def test_split_into_chapters_keeps_real_narrative_between_toc_and_first_chapter():
    toc = "\n".join(f"CHAPTER {i}" for i in range(1, 3))
    framing_letter = "\n".join(
        "dearest reader this is a real letter with quite a few words per line" for _ in range(10)
    )
    text = (
        toc
        + "\n\n"
        + framing_letter
        + "\n\nCHAPTER 1\n\n"
        + make_paragraph("alpha", 80)
        + "\n\nCHAPTER 2\n\n"
        + make_paragraph("beta", 80)
    )
    chapters = split_into_chapters(text)
    assert len(chapters) == 3
    assert "dearest" in chapters[0]["text"]
    assert chapters[0]["title"] == ""


def test_split_into_chapters_drops_illustrations_list_between_toc_and_first_chapter():
    toc = "\n".join(f"CHAPTER {i}" for i in range(1, 3))
    illustrations = "\n\n".join(f"Illustration caption {i}" for i in range(1, 15))
    text = (
        toc
        + "\n\n"
        + illustrations
        + "\n\nCHAPTER 1\n\n"
        + make_paragraph("alpha", 80)
        + "\n\nCHAPTER 2\n\n"
        + make_paragraph("beta", 80)
    )
    chapters = split_into_chapters(text)
    assert len(chapters) == 2
    assert chapters[0]["title"] != ""


def test_split_into_micro_sessions_empty_text_returns_no_sessions():
    assert split_into_micro_sessions("") == []


def test_split_into_micro_sessions_respects_word_bounds():
    paragraphs = [make_paragraph("w", 150) for _ in range(8)]
    text = "\n\n".join(paragraphs)
    sessions = split_into_micro_sessions(text, min_words=400, max_words=600)

    assert len(sessions) > 1
    for session in sessions[:-1]:
        assert 400 <= session["word_count"] <= 600 + 150


def test_split_into_micro_sessions_never_splits_mid_paragraph():
    paragraphs = [make_paragraph("w", 150) for _ in range(8)]
    text = "\n\n".join(paragraphs)
    sessions = split_into_micro_sessions(text, min_words=400, max_words=600)

    rejoined = "\n\n".join(s["text"] for s in sessions)
    original_paragraphs = {p.strip() for p in text.split("\n\n")}
    rejoined_paragraphs = {p.strip() for p in rejoined.split("\n\n")}
    assert original_paragraphs == rejoined_paragraphs


def test_split_into_micro_sessions_last_session_is_always_cliffhanger():
    paragraphs = [make_paragraph("w", 150) for _ in range(5)]
    text = "\n\n".join(paragraphs)
    sessions = split_into_micro_sessions(text, min_words=400, max_words=600)
    assert sessions[-1]["is_cliffhanger_break"] is True


def test_split_into_micro_sessions_flags_scene_shift_as_cliffhanger():
    para_a = make_paragraph("w", 450)
    para_b = make_paragraph("x", 450)
    text = para_a + "\n\n***\n\n" + para_b
    sessions = split_into_micro_sessions(text, min_words=400, max_words=600)

    assert len(sessions) == 2
    assert sessions[0]["is_cliffhanger_break"] is True


def test_split_into_micro_sessions_force_splits_extremely_long_paragraph():
    huge_paragraph = make_paragraph("w", 2000)
    sessions = split_into_micro_sessions(huge_paragraph, min_words=400, max_words=600)
    assert len(sessions) > 1


def test_split_into_micro_sessions_indexes_are_sequential():
    paragraphs = [make_paragraph("w", 150) for _ in range(8)]
    text = "\n\n".join(paragraphs)
    sessions = split_into_micro_sessions(text, min_words=400, max_words=600)
    assert [s["index"] for s in sessions] == list(range(len(sessions)))


def test_word_count():
    assert word_count("one two three") == 3
    assert word_count("") == 0
