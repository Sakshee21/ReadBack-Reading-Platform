"""Paragraph normalisation and front/back matter detection."""

import pytest

from app.services.frontmatter import (
    BACK_MATTER,
    FRONT_MATTER,
    STORY,
    classify_sections,
    should_skip_epub_item,
)
from app.services.normalize import (
    looks_like_verse_or_list,
    normalize_paragraphs,
    normalize_uploaded_text,
    strip_gutenberg_boilerplate,
    strip_pdf_furniture,
)
from app.services.segmentation import split_into_micro_sessions

# --------------------------------------------------------------------------
# the reported bug
# --------------------------------------------------------------------------


def test_hard_wrapped_sentence_becomes_one_paragraph():
    """Regression for the orphan-word bug: a sentence broken across wrapped
    lines must come back as one continuous paragraph."""
    raw = (
        "He had successfully avoided meeting his landlady on the staircase. His\n"
        "garret was under the roof of a high, five-storied house and was more like\n"
        "a cupboard than a room."
    )
    out = normalize_paragraphs(raw)
    assert "\n" not in out
    assert "staircase. His garret was under the roof" in out


def test_indented_continuation_style_is_split_into_paragraphs():
    """Some editions never use blank lines: continuation lines are indented and
    each new paragraph starts flush left. Without handling that, a whole
    chapter collapses into one paragraph and its heading is swallowed."""
    raw = (
        "CHAPTER I\n"
        "On an exceptionally hot evening early in July a young man came out of the\n"
        "      garret in which he lodged in S. Place and walked slowly, as though in\n"
        "      hesitation, towards K. bridge.\n"
        "He had successfully avoided meeting his landlady on the staircase. His\n"
        "      garret was under the roof of a high, five-storied house.\n"
    )
    paragraphs = normalize_paragraphs(raw).split("\n\n")

    assert paragraphs[0] == "CHAPTER I", paragraphs[0]
    assert paragraphs[1].startswith("On an exceptionally hot evening")
    assert "garret in which he lodged" in paragraphs[1]
    assert paragraphs[2].startswith("He had successfully avoided")
    assert "staircase. His garret was under the roof" in paragraphs[2]


def test_paragraphs_split_mid_sentence_are_rejoined():
    """An EPUB extractor that puts every inline <i>/<a> on its own line turns
    one sentence into five paragraphs. Repair it."""
    damaged = "\n\n".join(
        [
            "Why am I going there now? Am I capable of",
            "that",
            "? Is",
            "that",
            "serious? It is not serious at all.",
            "The heat in the street was terrible.",
        ]
    )
    paragraphs = normalize_paragraphs(damaged).split("\n\n")
    assert paragraphs[0] == (
        "Why am I going there now? Am I capable of that? Is that serious? "
        "It is not serious at all."
    )
    # the genuinely separate paragraph stays separate
    assert paragraphs[1] == "The heat in the street was terrible."


def test_split_inline_link_is_rejoined():
    damaged = "online at\n\nwww.gutenberg.org\n\n. If you are not located in the United States."
    assert normalize_paragraphs(damaged) == (
        "online at www.gutenberg.org. If you are not located in the United States."
    )


def test_normal_paragraph_breaks_are_not_merged():
    """Both halves of the rule must hold, so ordinary prose is untouched."""
    text = "He closed the door behind him.\n\nThe street outside was empty."
    assert normalize_paragraphs(text).count("\n\n") == 1


def test_a_heading_never_absorbs_the_next_paragraph():
    text = "CHAPTER I\n\nthe morning came late that day."
    assert normalize_paragraphs(text).split("\n\n")[0] == "CHAPTER I"


def test_space_before_punctuation_is_closed_up():
    assert normalize_uploaded_text("capable of that ? Is that serious .", source="epub") == (
        "capable of that? Is that serious."
    )


def test_heading_is_never_glued_to_the_following_paragraph():
    raw = "CHAPTER IV\nThe morning came and he rose early to walk by the river."
    assert normalize_paragraphs(raw).split("\n\n")[0] == "CHAPTER IV"


def test_first_line_indent_style_is_left_alone():
    """The opposite convention - every paragraph's first line indented - must
    not be chopped up."""
    raw = "    The first paragraph begins here\nand continues on this line."
    assert normalize_paragraphs(raw) == "The first paragraph begins here and continues on this line."


def test_blank_lines_separate_paragraphs():
    raw = "First line of one.\nSecond line of one.\n\nStart of two.\nEnd of two."
    out = normalize_paragraphs(raw)
    assert out.split("\n\n") == [
        "First line of one. Second line of one.",
        "Start of two. End of two.",
    ]


def test_leading_indentation_is_removed():
    raw = "    Indented first line\n    continues here."
    assert normalize_paragraphs(raw) == "Indented first line continues here."


def test_repeated_spaces_collapse():
    assert normalize_paragraphs("one    two\nthree     four") == "one two three four"


def test_crlf_and_nbsp_are_normalised():
    raw = "Line one of it.\r\nLine two of it.\r\n\r\nA second paragraph."
    out = normalize_paragraphs(raw)
    assert "\r" not in out and " " not in out
    assert out.split("\n\n") == ["Line one of it. Line two of it.", "A second paragraph."]


def test_unpunctuated_fragment_is_treated_as_a_split_paragraph():
    """Documents the trade-off: a paragraph ending with no punctuation,
    followed by one starting lowercase, is read as one broken sentence. That is
    what repairs mangled extraction, and real prose is punctuated."""
    assert normalize_paragraphs("he reached for the\n\nhandle of the door.") == (
        "he reached for the handle of the door."
    )


# --------------------------------------------------------------------------
# hyphenation: conservative
# --------------------------------------------------------------------------


def test_wrapped_hyphen_is_rejoined():
    raw = "the landlady pro-\nvided him with dinners"
    assert normalize_paragraphs(raw) == "the landlady provided him with dinners"


def test_real_hyphen_is_kept_when_next_line_is_capitalised():
    raw = "a five-storied house in St.-\nPetersburg stood there"
    out = normalize_paragraphs(raw)
    assert "St.- Petersburg" in out or "St.-Petersburg" in out
    assert "five-storied" in out


def test_em_dash_run_is_not_treated_as_hyphenation():
    raw = "he paused--\nand said nothing"
    assert normalize_paragraphs(raw) == "he paused-- and said nothing"


# --------------------------------------------------------------------------
# verse and lists survive
# --------------------------------------------------------------------------


def test_verse_keeps_its_line_breaks():
    poem = (
        "Tyger Tyger, burning bright,\n"
        "In the forests of the night;\n"
        "What immortal hand or eye,\n"
        "Could frame thy fearful symmetry?"
    )
    out = normalize_paragraphs(poem)
    assert out.count("\n") == 3


def test_numbered_list_keeps_its_line_breaks():
    listing = "1. First item\n2. Second item\n3. Third item\n4. Fourth item"
    assert normalize_paragraphs(listing).count("\n") == 3


def test_prose_is_not_mistaken_for_verse():
    long_lines = [
        "This is an ordinary paragraph of prose that has been hard wrapped at",
        "roughly seventy characters per line, as Project Gutenberg does, and it",
        "should be joined back together into one flowing block of readable text,",
        "not preserved as though it were poetry with meaningful line breaks.",
    ]
    assert not looks_like_verse_or_list(long_lines)
    assert "\n" not in normalize_paragraphs("\n".join(long_lines))


def test_two_short_lines_are_not_verse():
    assert not looks_like_verse_or_list(["Short one.", "Short two."])


# --------------------------------------------------------------------------
# Gutenberg boilerplate
# --------------------------------------------------------------------------


def test_boilerplate_outside_the_markers_is_removed():
    raw = (
        "The Project Gutenberg eBook of Something\n"
        "Produced by A Volunteer\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK SOMETHING ***\n"
        "Real story text here.\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK SOMETHING ***\n"
        "Licence terms follow and should vanish."
    )
    out = strip_gutenberg_boilerplate(raw)
    assert out.strip() == "Real story text here."


def test_marker_variants_are_tolerated():
    raw = "junk\n*** START OF THIS PROJECT GUTENBERG EBOOK X ***\nstory\n*** END OF THIS PROJECT GUTENBERG EBOOK X ***\nmore junk"
    assert strip_gutenberg_boilerplate(raw).strip() == "story"


def test_text_without_markers_is_untouched():
    raw = "Just a normal book with no Gutenberg markers at all."
    assert strip_gutenberg_boilerplate(raw) == raw


# --------------------------------------------------------------------------
# PDF furniture
# --------------------------------------------------------------------------


def test_running_headers_and_page_numbers_are_stripped():
    pages = [
        f"A SAMPLE NOVEL\nBody text for page {n} goes here and runs on.\n{n}"
        for n in range(1, 6)
    ]
    out = strip_pdf_furniture(pages)
    assert "A SAMPLE NOVEL" not in out
    for n in range(1, 6):
        assert f"\n{n}\n" not in f"\n{out}\n"
        assert f"Body text for page {n}" in out


def test_furniture_stripping_keeps_text_that_only_appears_once():
    pages = ["HEADER\nunique line one\n1", "HEADER\nunique line two\n2", "HEADER\nunique line three\n3"]
    out = strip_pdf_furniture(pages)
    assert "unique line one" in out and "unique line three" in out
    assert "HEADER" not in out


def test_long_repeated_line_is_not_stripped_as_furniture():
    """A real sentence repeated at a page edge must survive - only short
    header-like lines are candidates."""
    sentence = "This is a long line of genuine prose that happens to repeat " * 2
    pages = [f"{sentence}\nbody {n}" for n in range(1, 5)]
    assert sentence.strip()[:40] in strip_pdf_furniture(pages)


# --------------------------------------------------------------------------
# front / back matter
# --------------------------------------------------------------------------


def _section(title, text="word " * 400):
    return {"title": title, "text": text}


def test_everything_before_the_first_real_chapter_is_front_matter():
    sections = classify_sections(
        [
            _section("Title Page"),
            _section("Contents"),
            _section("Preface"),
            _section("CHAPTER I"),
            _section("CHAPTER II"),
        ]
    )
    kinds = [s["section_kind"] for s in sections]
    assert kinds == [FRONT_MATTER, FRONT_MATTER, FRONT_MATTER, STORY, STORY]


def test_back_matter_after_the_last_chapter_is_labelled():
    sections = classify_sections(
        [_section("CHAPTER I"), _section("CHAPTER II"), _section("Appendix"), _section("Colophon")]
    )
    assert [s["section_kind"] for s in sections] == [STORY, STORY, BACK_MATTER, BACK_MATTER]


def test_contents_listing_without_a_heading_is_detected():
    listing = "\n".join(f"Chapter {i}. A Short Title" for i in range(1, 12))
    sections = classify_sections([{"title": "", "text": listing}, _section("CHAPTER I")])
    assert sections[0]["section_kind"] == FRONT_MATTER


def test_a_book_with_no_headings_stays_all_story():
    sections = classify_sections([_section(""), _section(""), _section("")])
    assert all(s["section_kind"] == STORY for s in sections)


def test_classification_never_excludes_the_whole_book():
    """If every rule fired, we'd ship a book with nothing to read."""
    sections = classify_sections([_section("Preface", "short"), _section("Contents", "short")])
    assert any(s["section_kind"] == STORY for s in sections)


def test_epub_boilerplate_items_are_skipped():
    for href in ("cover.xhtml", "toc.xhtml", "titlepage.xhtml", "colophon.xhtml",
                 "copyright.xhtml", "OEBPS/nav.xhtml"):
        assert should_skip_epub_item(href), href
    for href in ("chapter-1.xhtml", "part2/ch10.xhtml", "text/body3.xhtml"):
        assert not should_skip_epub_item(href), href


def test_epub_type_wins_over_the_filename():
    assert should_skip_epub_item("body-01.xhtml", {"titlepage"})
    assert not should_skip_epub_item("body-01.xhtml", {"bodymatter"})


# --------------------------------------------------------------------------
# conservative flags for uploads
# --------------------------------------------------------------------------


def _para(word, n):
    return " ".join([word] * n)


def test_conservative_cliffhangers_only_fire_on_a_hook():
    calm = "\n\n".join(_para("word", 450) + "." for _ in range(4))
    sessions = split_into_micro_sessions(calm, conservative_cliffhangers=True)
    assert sessions[-1]["is_cliffhanger_break"] is True  # chapter end always counts
    assert all(not s["is_cliffhanger_break"] for s in sessions[:-1])


def test_conservative_cliffhanger_fires_on_a_question():
    text = "\n\n".join([_para("word", 450) + " what could it mean?", _para("other", 450) + "."])
    sessions = split_into_micro_sessions(text, conservative_cliffhangers=True)
    assert sessions[0]["is_cliffhanger_break"] is True


def test_visualization_prompts_can_be_disabled():
    text = "\n\n".join(_para("word", 450) for _ in range(6))
    off = split_into_micro_sessions(text, visualization_prompts=False)
    assert all(not s["has_visualization_prompt"] for s in off)


def test_default_segmentation_is_unchanged_for_seeded_books():
    """The seeded pipeline must behave exactly as before these options existed."""
    text = "\n\n".join(_para("word", 450) for _ in range(6))
    default = split_into_micro_sessions(text)
    explicit = split_into_micro_sessions(
        text, conservative_cliffhangers=False, visualization_prompts=True, visualization_every=3
    )
    assert [s["is_cliffhanger_break"] for s in default] == [
        s["is_cliffhanger_break"] for s in explicit
    ]
    assert any(s["has_visualization_prompt"] for s in default)


# --------------------------------------------------------------------------
# micro-sessions never split mid-sentence
# --------------------------------------------------------------------------


def test_micro_sessions_start_at_a_paragraph_boundary():
    paragraphs = [f"Paragraph {i}. " + _para("word", 200) + "." for i in range(12)]
    text = "\n\n".join(paragraphs)
    sessions = split_into_micro_sessions(text)
    starts = {s["text"].split(".")[0] + "." for s in sessions}
    assert all(start.startswith("Paragraph") for start in starts), starts


def test_epub_source_text_is_not_rewrapped():
    """EPUB paragraphs already come from <p>; normalising must leave them."""
    raw = "First real paragraph.\n\nSecond real paragraph."
    assert normalize_uploaded_text(raw, source="epub") == raw
