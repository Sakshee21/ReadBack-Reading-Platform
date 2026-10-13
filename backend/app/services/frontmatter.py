"""Tell story sections apart from front and back matter.

A Gutenberg or Standard Ebooks file opens with a title page, a contents list, a
transcriber's note and often a long editorial introduction, then ends with
appendices and a colophon. None of that is the book, and turning it into
micro-sessions gives the reader several minutes of licence text before the
story starts.

The rules are deliberately conservative: nothing is deleted, sections are only
*labelled*, and when a real chapter heading exists we trust position over
keywords. Anything we aren't sure about stays `story`.
"""

import re

STORY = "story"
FRONT_MATTER = "front_matter"
BACK_MATTER = "back_matter"

FRONT_KEYWORDS = (
    "contents", "table of contents", "preface", "introduction", "foreword",
    "dedication", "copyright", "license", "licence", "transcriber",
    "illustrations", "list of illustrations", "title page", "titlepage",
    "half-title", "frontispiece", "acknowledg", "editor's note", "editors note",
    "translator", "a note on", "note on the text", "imprint", "cover",
)

BACK_KEYWORDS = (
    "appendix", "appendices", "colophon", "uncopyright", "index", "glossary",
    "bibliography", "afterword", "about the author", "endnotes", "footnotes",
    "notes", "errata", "advertisement", "transcriber",
)

# "CHAPTER I", "Chapter 1", "PART ONE", "BOOK TWO" - a real story division.
REAL_CHAPTER = re.compile(
    r"^\s*(chapter|part|book|canto|stave|act)\b\s*[ivxlcdm\d]", re.IGNORECASE
)

# A section short enough that it can't be a chapter.
SHORT_SECTION_WORDS = 150


def _effective_title(section: dict) -> str:
    """The section's heading, falling back to its first line.

    The chapter detector sometimes replaces a bare "CHAPTER I" with a
    descriptive title recovered from the table of contents, and a lead-in
    section has no title at all - but its first line is usually the heading
    ("PREFACE", "INTRODUCTION"), so look there too.
    """
    title = (section.get("title") or "").strip()
    if title:
        return title
    for line in (section.get("text") or "").split("\n"):
        line = line.strip()
        if line:
            return line if len(line) <= 80 else ""
    return ""


def _matches(title: str, keywords) -> bool:
    low = (title or "").strip().lower()
    if not low:
        return False
    return any(k in low for k in keywords)


def _is_listing(text: str) -> bool:
    """A contents page is many short lines; prose is long wrapped ones."""
    lines = [line.strip() for line in (text or "").split("\n") if line.strip()]
    if len(lines) < 6:
        return False
    avg = sum(len(line.split()) for line in lines) / len(lines)
    return avg < 6


def _first_real_chapter(sections: list[dict]) -> int | None:
    for i, section in enumerate(sections):
        if REAL_CHAPTER.match(_effective_title(section)):
            return i
    return None


def _last_real_chapter(sections: list[dict]) -> int | None:
    last = None
    for i, section in enumerate(sections):
        if REAL_CHAPTER.match(_effective_title(section)):
            last = i
    return last


def classify_sections(sections: list[dict]) -> list[dict]:
    """Annotate each section with ``section_kind``.

    Returns the same list of dicts with the key added; the caller decides what
    to do with non-story sections (we store them, but keep them out of the
    reading flow).
    """
    if not sections:
        return sections

    first_chapter = _first_real_chapter(sections)
    last_chapter = _last_real_chapter(sections)

    for i, section in enumerate(sections):
        title = _effective_title(section)
        text = section.get("text") or ""
        words = len(text.split())
        kind = STORY

        if first_chapter is not None and i < first_chapter:
            # Everything ahead of the first real chapter heading is front
            # matter. This is the strongest signal we have and it's why we
            # prefer it over keyword guessing.
            kind = FRONT_MATTER
        elif _matches(title, FRONT_KEYWORDS) and (
            first_chapter is None or i <= (first_chapter or 0)
        ):
            kind = FRONT_MATTER
        elif last_chapter is not None and i > last_chapter and _matches(title, BACK_KEYWORDS):
            kind = BACK_MATTER
        elif _matches(title, BACK_KEYWORDS) and words < SHORT_SECTION_WORDS:
            kind = BACK_MATTER
        elif _matches(title, FRONT_KEYWORDS) and words < SHORT_SECTION_WORDS:
            kind = FRONT_MATTER
        elif _is_listing(text) and words < SHORT_SECTION_WORDS * 4:
            # a contents or illustrations list that never got a heading
            kind = FRONT_MATTER if last_chapter is None or i < last_chapter else BACK_MATTER

        section["section_kind"] = kind

    # Never label everything as non-story: if the rules somehow excluded the
    # whole book, fall back to treating it all as story rather than shipping a
    # book with nothing to read.
    if all(s["section_kind"] != STORY for s in sections):
        for section in sections:
            section["section_kind"] = STORY

    return sections


# ---------------------------------------------------------------------------
# EPUB spine filtering
# ---------------------------------------------------------------------------

SKIP_HREF = re.compile(
    r"(cover|nav\b|toc|contents|titlepage|title-page|halftitle|copyright|colophon"
    r"|imprint|licen[cs]e|uncopyright|dedication|frontmatter|back-?matter)",
    re.IGNORECASE,
)

SKIP_EPUB_TYPE = {
    "cover", "toc", "titlepage", "copyright-page", "colophon", "imprint",
    "dedication", "acknowledgements", "frontmatter", "backmatter", "landmarks",
}


def should_skip_epub_item(href: str, epub_types: set[str] | None = None) -> bool:
    """Whether an EPUB spine item is navigation/boilerplate rather than text."""
    if epub_types and (epub_types & SKIP_EPUB_TYPE):
        return True
    return bool(SKIP_HREF.search(href or ""))
