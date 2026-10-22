"""Turn hard-wrapped source text into real paragraphs.

Project Gutenberg plain text (and most PDF extraction) wraps every line at
~70 characters. Rendered as-is those line breaks survive, so a paragraph shows
up with orphan words stranded on their own lines. This module rejoins wrapped
lines into one paragraph per block, while leaving verse and lists alone.

Used only for uploaded/imported books. The five seeded books keep their stored
text exactly as it was.
"""

import re
from collections import Counter

# Non-breaking space, zero-width junk, BOM.
ODDITIES = {
    " ": " ",
    " ": " ",
    " ": " ",
    "﻿": "",
    "​": "",
    "­": "",  # soft hyphen
}

LIST_MARKER = re.compile(r"^\s*([-*•‣▪–—]|\(?\d{1,3}[.)]|\(?[ivxlcdm]{1,6}[.)])\s+", re.I)

# A heading that must never be glued onto the paragraph after it - doing so
# hides it from chapter detection and turns the opening sentence into a title.
STANDALONE_HEADING = re.compile(
    r"^\s*(?:"
    r"(?:chapter|part|book|canto|stave|act|section)\s+[ivxlcdm\d]+[.\s]*"
    r"|epilogue|prologue|contents|preface|introduction|foreword|dedication"
    r"|appendix|afterword|colophon"
    r")\s*$",
    re.IGNORECASE,
)

# Minimum indent that counts as a continuation marker.
INDENT_WIDTH = 2

# A paragraph that ends mid-sentence, followed by one that opens mid-sentence,
# is almost always one paragraph that got broken apart - typically by an EPUB
# extractor that put every inline <i> or <a> on its own line, or by a PDF
# column break. Both conditions must hold before we rejoin them.
SENTENCE_END = re.compile(r"""[.!?…:][\"'”’)\]]*$""")
CONTINUATION_START = re.compile(r"""^[a-z,;:!?.)\]…\"'”’]""")

# get_text(" ") leaves a space before punctuation that followed an inline tag.
SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?%)\]}»”’])")
SPACE_AFTER_OPEN = re.compile(r"([(\[{«“])\s+")


def tidy_inline_spacing(text: str) -> str:
    """Close up the gaps left where inline markup was unwrapped."""
    text = SPACE_BEFORE_PUNCT.sub(r"\1", text)
    return SPACE_AFTER_OPEN.sub(r"\1", text)

# A page number alone on a line: "12", "- 12 -", "[12]", "xiv".
PAGE_NUMBER = re.compile(r"^\s*[\[\(\-–—]*\s*(\d{1,4}|[ivxlcdm]{1,7})\s*[\]\)\-–—]*\s*$", re.I)

# Verse/list detection: a run of consistently short lines isn't a wrapped
# paragraph. Prose wrapped at 70 chars averages well above this.
VERSE_MAX_LINE = 50
VERSE_AVG_LINE = 45
VERSE_MIN_LINES = 4


def _basic_clean(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    for bad, good in ODDITIES.items():
        text = text.replace(bad, good)
    text = text.replace("\t", " ")
    # trailing whitespace on every line, and runs of blank lines
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text)


def looks_like_verse_or_list(lines: list[str]) -> bool:
    """True when the line breaks are intentional rather than a wrap artefact."""
    stripped = [line.strip() for line in lines if line.strip()]
    if len(stripped) < VERSE_MIN_LINES:
        return False

    marked = sum(1 for line in stripped if LIST_MARKER.match(line))
    if marked >= max(2, len(stripped) * 0.6):
        return True

    lengths = [len(line) for line in stripped]
    return max(lengths) <= VERSE_MAX_LINE and sum(lengths) / len(lengths) <= VERSE_AVG_LINE


def _join_wrapped(lines: list[str]) -> str:
    """Join hard-wrapped lines with a single space.

    A trailing hyphen is only treated as a wrap when it looks like one - a
    lowercase letter before it and a lowercase letter after - so real
    compounds ("self-evident", "well-known") and em-dash runs survive.
    """
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not out:
            out = line
            continue
        if re.search(r"[a-z]-$", out) and re.match(r"^[a-z]", line):
            out = out[:-1] + line
        else:
            out = f"{out} {line}"
    return out


def join_wrapped_lines(lines: list[str]) -> str:
    """Join hard-wrapped lines into one paragraph (see ``_join_wrapped``).

    Public so the research extractor can reuse the end-of-line hyphen rule
    rather than keeping a second copy of it.
    """
    return _join_wrapped(lines)


def merge_split_paragraphs(paragraphs: list[str]) -> list[str]:
    """Rejoin paragraphs broken mid-sentence (see ``_merge_continuations``).

    Public for the research extractor, where the break comes from a page or
    column boundary rather than an EPUB extractor.
    """
    return _merge_continuations(paragraphs)


def _split_on_indent(lines: list[str]) -> list[list[str]]:
    """Split a run of lines that uses indentation instead of blank lines.

    Some editions (the Gutenberg Crime and Punishment among them) run every
    paragraph together, marking continuation lines with leading spaces and
    starting each new paragraph flush left. Without this, the whole chapter
    collapses into one paragraph and its heading gets glued to the first
    sentence.
    """
    indents = [len(line) - len(line.lstrip()) for line in lines]
    flush = [i for i, ind in enumerate(indents) if ind == 0]
    indented = [i for i, ind in enumerate(indents) if ind >= INDENT_WIDTH]

    # Uniform indentation (all flush, or all indented) is just a wrapped block.
    if not flush or not indented:
        return [lines]

    # Which kind of line begins a paragraph is decided by the first line:
    #   flush first    -> continuations are indented, so flush lines start one
    #   indented first -> first-line-indent style, so indented lines start one
    starts = set(flush) if indents[0] == 0 else set(indented)

    groups: list[list[str]] = []
    current: list[str] = []
    for i, line in enumerate(lines):
        if i in starts and current:
            groups.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append(current)
    return groups


def _split_off_headings(lines: list[str]) -> list[list[str]]:
    """Give any standalone heading a paragraph of its own."""
    groups: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if STANDALONE_HEADING.match(line):
            if current:
                groups.append(current)
                current = []
            groups.append([line])
        else:
            current.append(line)
    if current:
        groups.append(current)
    return groups


def normalize_paragraphs(raw: str) -> str:
    """Blank-line-separated blocks in, one paragraph per block out."""
    text = _basic_clean(raw)
    paragraphs: list[str] = []

    for block in re.split(r"\n[ \t]*\n", text):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        if looks_like_verse_or_list(lines):
            # keep the author's line breaks, just trim the indentation
            paragraphs.append("\n".join(line.strip() for line in lines))
            continue

        for run in _split_on_indent(lines):
            for group in _split_off_headings(run):
                if looks_like_verse_or_list(group):
                    paragraphs.append("\n".join(line.strip() for line in group))
                else:
                    paragraphs.append(_join_wrapped(group))

    paragraphs = _merge_continuations(paragraphs)
    joined = "\n\n".join(p for p in paragraphs if p.strip())
    return tidy_inline_spacing(re.sub(r"[ ]{2,}", " ", joined)).strip()


def _merge_continuations(paragraphs: list[str]) -> list[str]:
    """Rejoin paragraphs that were split mid-sentence.

    Repairs text mangled by an extractor that broke on inline markup, e.g.
    "Am I capable of" / "that" / "? Is" / "that" / "serious?" - which is one
    sentence, not five paragraphs. Requires BOTH that the previous paragraph
    ends mid-sentence and that this one opens mid-sentence, so ordinary
    paragraph breaks are left alone.
    """
    merged: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if merged:
            prev = merged[-1]
            # never touch verse/list blocks, and never absorb a heading
            if (
                "\n" not in prev
                and "\n" not in para
                and not STANDALONE_HEADING.match(prev)
                and not SENTENCE_END.search(prev)
                and CONTINUATION_START.match(para)
            ):
                merged[-1] = f"{prev} {para}"
                continue
        merged.append(para)
    return merged


def strip_pdf_furniture(pages: list[str]) -> str:
    """Drop repeated running headers/footers and standalone page numbers.

    A line counts as furniture when it sits at the top or bottom of at least
    half the pages, which is what a running header looks like and what a real
    sentence never does.
    """
    usable = [p for p in pages if p.strip()]
    if not usable:
        return ""

    def edge_lines(page: str) -> tuple[str, str]:
        lines = [line.strip() for line in page.split("\n") if line.strip()]
        return (lines[0] if lines else "", lines[-1] if lines else "")

    firsts = Counter()
    lasts = Counter()
    for page in usable:
        first, last = edge_lines(page)
        if first:
            firsts[first] += 1
        if last:
            lasts[last] += 1

    threshold = max(2, len(usable) // 2)
    furniture = {line for line, n in firsts.items() if n >= threshold}
    furniture |= {line for line, n in lasts.items() if n >= threshold}
    # never strip something long enough to be real prose
    furniture = {line for line in furniture if len(line) <= 90}

    cleaned_pages = []
    for page in usable:
        kept = []
        for line in page.split("\n"):
            bare = line.strip()
            if not bare:
                kept.append(line)
                continue
            if bare in furniture or PAGE_NUMBER.match(bare):
                continue
            kept.append(line)
        cleaned_pages.append("\n".join(kept))

    return "\n\n".join(p for p in cleaned_pages if p.strip())


# ---------------------------------------------------------------------------
# Project Gutenberg boilerplate
# ---------------------------------------------------------------------------

# Tolerant of the many marker variants PG has used over the years.
PG_START = re.compile(
    r"\*\*\*\s*START OF (?:THE|THIS)?\s*PROJECT GUTENBERG EBOOK.*?\*\*\*", re.IGNORECASE | re.DOTALL
)
PG_END = re.compile(
    r"\*\*\*\s*END OF (?:THE|THIS)?\s*PROJECT GUTENBERG EBOOK.*", re.IGNORECASE | re.DOTALL
)
PRODUCED_BY = re.compile(
    r"^[ \t]*(produced by|prepared by|transcribed by|e-?text prepared by|updated editions will)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)
# A licence block that survives mid-text.
LICENSE_BLOCK = re.compile(
    r"^[ \t]*(START|END): FULL LICENSE.*?$|^[ \t]*THE FULL PROJECT GUTENBERG LICENSE.*?$",
    re.IGNORECASE | re.MULTILINE,
)


def strip_gutenberg_boilerplate(text: str) -> str:
    """Remove everything outside the START/END markers, plus stray credit lines.

    Falls back to returning the text untouched when no markers are present, so
    a non-Gutenberg upload is never truncated.
    """
    match = PG_START.search(text)
    if match:
        text = text[match.end():]
    match = PG_END.search(text)
    if match:
        text = text[: match.start()]

    text = PRODUCED_BY.sub("", text)
    text = LICENSE_BLOCK.sub("", text)
    return text.strip()


def normalize_uploaded_text(raw: str, source: str = "txt", pages: list[str] | None = None) -> str:
    """The single entry point used by the upload pipeline.

    txt  - strip Gutenberg boilerplate, then rejoin wrapped paragraphs
    pdf  - strip running headers/footers and page numbers first
    epub - paragraphs already come from <p> tags, so only tidy whitespace
    """
    if source == "pdf" and pages is not None:
        raw = strip_pdf_furniture(pages)

    if source != "epub":
        raw = strip_gutenberg_boilerplate(raw)

    if source == "epub":
        # HTML gave us real paragraph boundaries; re-wrapping would be wrong.
        cleaned = re.sub(r"[ ]{2,}", " ", _basic_clean(raw))
        return tidy_inline_spacing(cleaned).strip()

    return normalize_paragraphs(raw)
