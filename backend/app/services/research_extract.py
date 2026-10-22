"""Turn a research PDF into sections of readable text.

The book pipeline (``services/extract.extract_pdf``) asks pypdf for a page of
text. That is right for a novel and wrong for a journal paper: a two-column
page comes back with the columns read across rather than down, so every
sentence is spliced into its neighbour, and the references land in the reading
flow as though they were prose.

This path works from geometry instead (``services/pdf_layout``):

    pages -> reading order -> furniture removed -> paragraphs -> sections

and keeps figure and table captions, equations and table rows out of the body
text, because none of them read as prose.

Nothing here touches the database, the network or an LLM. It is pure
bytes-in / sections-out, so it can be tested on a handful of small fixtures.

What it deliberately does NOT do: OCR a scan, reconstruct a table, parse an
equation, or guess a piece of metadata it cannot find. A blank field is the
correct answer when the document does not say.
"""

import io
import re
from dataclasses import dataclass, field

from app.services.extract import ExtractionError
from app.services.normalize import (
    join_wrapped_lines,
    merge_split_paragraphs,
    tidy_inline_spacing,
)
from app.services.pdf_layout import (
    LayoutUnavailable,
    Line,
    Page,
    is_furniture,
    reading_order,
    read_pages,
    repeated_edge_lines,
)
from app.services.segmentation import word_count

# Section kinds stored on chapters.section_kind for a research document.
ABSTRACT = "abstract"
BODY = "body"
REFERENCES = "references"
APPENDIX = "appendix"
FRONT_MATTER = "front_matter"
RESEARCH_SECTION_KINDS = (ABSTRACT, BODY, REFERENCES, APPENDIX, FRONT_MATTER)
# Kinds that make up the reading flow. References and the title block are
# stored and reachable, but are not what the reader is taken through.
READABLE_KINDS = (ABSTRACT, BODY, APPENDIX)

PAPER = "paper"
TEXTBOOK = "textbook"
DOC_KINDS = (PAPER, TEXTBOOK)

# Below this many words a PDF has no usable text layer: it is a scan.
MIN_TEXT_WORDS = 50
# A textbook is recognised by having a real outline with at least this many
# entries. Fewer than that and we fall back to heading detection.
MIN_OUTLINE_ENTRIES = 3


# ---------------------------------------------------------------------------
# line classification
# ---------------------------------------------------------------------------

TEXT = "text"
CAPTION = "caption"
EQUATION = "equation"
TABLE_ROW = "table_row"

CAPTION_START = re.compile(
    r"^\s*(fig(?:ure|\.)?|tab(?:le|\.)?|chart|scheme|listing|algorithm|exhibit|plate)"
    r"\s*\.?\s*(\d{1,3}|[IVXLC]{1,5})\s*[.:)\-–—]",
    re.IGNORECASE,
)
# A trailing "(1)" or "(3.2)" is how a numbered equation is tagged.
EQUATION_TAG = re.compile(r"\(\s*\d{1,3}(?:\.\d{1,3})?\s*\)\s*$")
MATH_CHARS = set("=+<>≤≥≈≠±×÷∑∏∫√∂∇∈∉⊂⊆∪∩→←↔∞µσαβγδθλπρφψω^_|/")
# Two or more spaces repeated across a line is column alignment, not prose.
TABLE_GAPS = re.compile(r"\S {2,}\S")
WORD_RE = re.compile(r"[A-Za-z]{2,}")


def _math_ratio(text: str) -> float:
    stripped = [ch for ch in text if not ch.isspace()]
    if not stripped:
        return 0.0
    return sum(1 for ch in stripped if ch in MATH_CHARS) / len(stripped)


def _numeric_ratio(text: str) -> float:
    tokens = text.split()
    if not tokens:
        return 0.0
    numeric = sum(1 for t in tokens if re.fullmatch(r"[-+(]?[\d.,%)]+", t))
    return numeric / len(tokens)


def classify_line(text: str) -> str:
    """What kind of thing this line is, from its shape alone.

    Conservative by design: anything that might be prose is TEXT. A false
    CAPTION only moves a sentence into the caption list, but a false TEXT puts
    a row of numbers in the middle of a paragraph.
    """
    bare = text.strip()
    if not bare:
        return TEXT
    if CAPTION_START.match(bare):
        return CAPTION

    words = WORD_RE.findall(bare)
    # An equation: mostly symbols, or symbol-heavy with a numbered tag and
    # hardly any words.
    if _math_ratio(bare) >= 0.25 and len(words) <= 6:
        return EQUATION
    if EQUATION_TAG.search(bare) and len(words) <= 4 and _math_ratio(bare) >= 0.08:
        return EQUATION
    # A table row: aligned columns, or almost all numbers.
    if len(TABLE_GAPS.findall(bare)) >= 2 and len(words) <= 8:
        return TABLE_ROW
    if _numeric_ratio(bare) >= 0.6 and len(bare.split()) >= 3:
        return TABLE_ROW
    return TEXT


# ---------------------------------------------------------------------------
# drop caps and split capitals
# ---------------------------------------------------------------------------

# A drop cap or a small-caps opening is set as its own run, so extraction
# hands back the first letter as a separate token: "T HE Internet" for a
# heading that reads THE INTERNET, or "T his paper" for a paragraph.
#
# Only the start of a line is repaired. Mid-sentence the same shape is almost
# always real - "vitamin C and iron" would otherwise become "Cand" - and drop
# caps only ever appear at the start of a heading or a paragraph.
SPLIT_CAP_START = re.compile(r"^([A-Z])\s+([A-Za-z]{2,})")
VOWELS = set("AEIOUY")


def _is_split_word(letter: str, rest: str) -> bool:
    """Is "<letter> <rest>" one word that extraction broke in two?

    The remainder has to be written as one case throughout: "T Hello" is two
    words, "T HE" and "T he" are halves of one. A and I are real words, so
    they are only rejoined when the remainder is unpronounceable on its own -
    NTRODUCTION has no vowel in its first two letters, MITRE does.
    """
    if not (rest.isupper() or rest.islower()):
        return False
    if letter not in ("A", "I"):
        return True
    return not (set(rest[:2].upper()) & VOWELS)


def repair_split_capitals(text: str) -> str:
    """Rejoin a leading capital that extraction split from its word."""
    out = (text or "").lstrip()
    for _ in range(3):  # "T H E" would need more than one pass
        match = SPLIT_CAP_START.match(out)
        if not match or not _is_split_word(match.group(1), match.group(2)):
            return out
        out = f"{match.group(1)}{match.group(2)}{out[match.end():]}"
    return out


# ---------------------------------------------------------------------------
# bylines
# ---------------------------------------------------------------------------

BYLINE_MAX_CHARS = 120
# Words that appear in prose and essentially never in a name. A byline is
# split on its separators first, so "and" is not in here.
BYLINE_PROSE_WORDS = {
    "a", "an", "the", "of", "to", "in", "on", "at", "by", "for", "from", "with",
    "that", "this", "these", "those", "it", "its", "their", "our", "we", "they",
    "is", "are", "was", "were", "be", "been", "has", "have", "had", "can",
    "will", "would", "should", "may", "which", "when", "while", "where",
    "according", "ensure", "using", "used", "based", "labeled", "labelled",
    "paper", "study", "dataset", "data", "method", "results", "propose",
    "present", "show", "shows", "described", "credibility", "tactics",
}
# A name token: an initial, or a capitalised word (with hyphens, apostrophes
# and particles like van or de allowed in lower case inside a name).
NAME_TOKEN = re.compile(r"^(?:[A-Z]\.|[A-Z][A-Za-z'’\-]*\.?|van|von|de|del|der|di|da|la|le|bin|al)$")
BYLINE_SPLIT = re.compile(r",|;|\sand\s|\s&\s|·|\|", re.IGNORECASE)
# A full stop after a whole word ends a sentence. After a single letter it is
# an initial, which is why the length matters.
SENTENCE_STOP = re.compile(r"[A-Za-z]{2,}\.(\s|$)")
NOT_IN_A_NAME = re.compile(
    r"\d|@|https?://|[/:()\[\]{}<>+=*]|\b(universit\w*|institut\w*|department|dept"
    r"|laborator\w*|college|school|faculty|centre|center|corp|inc|ltd|gmbh"
    r"|abstract|keywords?|index terms)\b",
    re.IGNORECASE,
)


def looks_like_byline(text: str) -> bool:
    """Is this line a list of author names, rather than a sentence?

    Deliberately hard to satisfy. The failure this replaces put a sentence
    from the body of a paper - "Honeypot and labeled according to Enterprise
    Tactics of MITRE ATT&CK to ensure dataset credibility." - into the author
    field of every citation the reader copied. A blank author field is a
    visible gap; a wrong one is not.
    """
    bare = " ".join((text or "").split())
    if not bare or len(bare) > BYLINE_MAX_CHARS:
        return False
    if NOT_IN_A_NAME.search(bare):
        return False
    if SENTENCE_STOP.search(bare):
        return False
    if bare.rstrip().endswith((",", ";", ":")):
        return False

    names = [piece.strip() for piece in BYLINE_SPLIT.split(bare) if piece.strip()]
    if not names or len(names) > 12:
        return False
    for name in names:
        tokens = name.split()
        if not 1 <= len(tokens) <= 4:
            return False
        for token in tokens:
            # An initial is a single letter, so "A." must not be read as the
            # article "a" and rejected along with it.
            initial = re.fullmatch(r"[A-Z]\.?", token)
            if not initial and token.lower().strip(".") in BYLINE_PROSE_WORDS:
                return False
            if not NAME_TOKEN.match(token):
                return False
    # One bare surname is a label ("Methods"), not a byline. Either several
    # names, or one name of at least two tokens.
    return len(names) > 1 or len(names[0].split()) > 1


# ---------------------------------------------------------------------------
# heading detection
# ---------------------------------------------------------------------------

# "I.", "IV.", "1", "1.", "2.3", "A.", "A.1" - a section number.
NUMBER_PREFIX = re.compile(
    r"^\s*(?:(?:[IVXLCDM]{1,6}|\d{1,2}(?:\.\d{1,2}){0,3}|[A-H])\s*[.)]\s+|"
    r"(?:\d{1,2}(?:\.\d{1,2}){1,3})\s+)"
)
# Section names that appear in papers and textbooks, with or without a number.
NAMED_HEADING = re.compile(
    r"^\s*(?:"
    r"abstract|summary|keywords?|index terms"
    r"|introduction|background|motivation|related works?|prior works?|literature review"
    r"|method(?:s|ology)?|materials and methods|approach|model|architecture|design"
    r"|implementation|experiments?|experimental (?:setup|design|results)"
    r"|dataset|data|evaluation|results?|analysis|findings"
    r"|discussion|limitations?|threats to validity|conclusions?|concluding remarks"
    r"|future work|acknowledge?ments?|acknowledgments?"
    r"|references|bibliography|works cited|literature cited"
    r"|appendi(?:x|ces)|supplementary material|notation|glossary"
    r"|chapter\s+[\dIVXLC]+|part\s+[\dIVXLC]+|exercises?|problems|further reading"
    r")\b\s*[:.\-–—]?\s*",
    re.IGNORECASE,
)
# IEEE runs the abstract straight on from its own label.
ABSTRACT_RUN_ON = re.compile(r"^\s*(abstract|summary)\s*[-–—:.]\s*(\S)", re.IGNORECASE)

MAX_HEADING_CHARS = 90
MAX_HEADING_WORDS = 12
# A heading set in a larger face than the body is a heading whatever it says.
HEADING_SIZE_RATIO = 1.15


def strip_number_prefix(title: str) -> str:
    return NUMBER_PREFIX.sub("", title or "").strip()


def looks_like_heading(line: Line, body_size: float) -> bool:
    """Is this line a section heading rather than a sentence?"""
    bare = line.text.strip()
    if not bare or len(bare) > MAX_HEADING_CHARS:
        return False
    if classify_line(bare) in (CAPTION, TABLE_ROW, EQUATION):
        return False

    without_number = strip_number_prefix(bare)
    if not without_number:
        return False  # a bare numeral is a folio, not a heading
    words = without_number.split()
    if len(words) > MAX_HEADING_WORDS:
        return False

    numbered = bool(NUMBER_PREFIX.match(bare))
    # A heading is set apart from the prose around it, by a number, by capitals
    # or by a larger face. A bare lower-case word is not a heading even when it
    # happens to be a section name: the word "evaluation" on a line of its own
    # in the middle of a paragraph is prose that wrapped.
    if not numbered and without_number.islower():
        return False

    # A section name has to *be* the line, not merely start it. Matching a
    # prefix turns every reference entry beginning "Approach." or "design,"
    # into a section heading, which then cuts the bibliography into pieces.
    if NAMED_HEADING.fullmatch(without_number):
        return True
    if NAMED_HEADING.match(without_number) and len(words) <= 4:
        return True
    # A numbered heading does not end in a full stop; "1. We then ran..." does.
    if numbered and not bare.endswith("."):
        return True
    if body_size and line.size >= body_size * HEADING_SIZE_RATIO and len(words) <= 8:
        return True
    letters = [ch for ch in without_number if ch.isalpha()]
    if letters and all(ch.isupper() for ch in letters) and len(words) <= 8:
        return True
    return False


def section_kind_for(title: str, *, seen_references: bool) -> str:
    """Which stored section kind a heading introduces."""
    bare = strip_number_prefix(title).strip().lower()
    if re.match(r"^(abstract|summary)\b", bare):
        return ABSTRACT
    if re.match(r"^(references|bibliography|works cited|literature cited)\b", bare):
        return REFERENCES
    if re.match(r"^(appendi(x|ces)|supplementary|acknowledge?ments?|acknowledgments?)\b", bare):
        return APPENDIX
    # After the reference list, anything unlabelled is still back matter.
    return REFERENCES if seen_references else BODY


# ---------------------------------------------------------------------------
# paragraph assembly
# ---------------------------------------------------------------------------

# A line ending this far short of its column is the end of a paragraph.
SHORT_LINE_SHARE = 0.11
# An indent this much past the column edge starts one.
INDENT_POINTS = 5.0


@dataclass
class Block:
    """A run of lines that belong together."""

    kind: str
    lines: list[str]
    page: int
    heading: bool = False

    def text(self) -> str:
        if self.kind == TEXT:
            joined = tidy_inline_spacing(join_wrapped_lines(self.lines))
            # Repairs a drop cap at the head of a heading or a paragraph.
            return repair_split_capitals(joined)
        return "\n".join(line.strip() for line in self.lines)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _column_of(line: Line, page: Page) -> int:
    for i, col in enumerate(page.columns):
        if col.holds(line):
            return i
    return -1


def _right_edges(lines: list[Line], page: Page) -> dict[int, float]:
    """The full-measure right edge of each column, from the lines in it."""
    edges: dict[int, list[float]] = {}
    for line in lines:
        edges.setdefault(_column_of(line, page), []).append(line.x1)
    return {col: max(values) for col, values in edges.items()}


def page_blocks(page: Page, repeated: set[str], body_size: float) -> list[Block]:
    """Group one page into blocks, deciding paragraph breaks from geometry."""
    lines = [ln for ln in reading_order(page) if not is_furniture(ln, page, repeated)]
    if not lines:
        return []

    heights = _median([ln.bottom - ln.top for ln in lines]) or 10.0
    edges = _right_edges(lines, page)
    gaps = [
        b.top - a.bottom
        for a, b in zip(lines, lines[1:])
        if _column_of(a, page) == _column_of(b, page) and b.top >= a.top
    ]
    normal_gap = _median(gaps)
    gap_limit = normal_gap + max(1.5, heights * 0.35)

    blocks: list[Block] = []
    previous: Line | None = None

    def start(kind: str, heading: bool = False) -> Block:
        block = Block(kind=kind, lines=[], page=page.number, heading=heading)
        blocks.append(block)
        return block

    current: Block | None = None
    for line in lines:
        kind = classify_line(line.text)
        heading = kind == TEXT and looks_like_heading(line, body_size)

        run_on = ABSTRACT_RUN_ON.match(line.text) if heading is False else None
        if run_on:
            # "Abstract-Long-form reading has..." is a heading plus a paragraph.
            label = line.text[: run_on.end(1)].strip()
            rest = line.text[run_on.start(2) :].strip()
            start(TEXT, heading=True).lines.append(label)
            current = start(TEXT)
            current.lines.append(rest)
            previous = line
            continue

        broken = (
            current is None
            or heading
            or current.heading
            or current.kind != kind
            or previous is None
            # Two lines on the same visual row sit side by side, so neither
            # can be the wrapped continuation of the other. This is the safety
            # net for a page whose columns were not detected: without it the
            # columns are read across and the join produces nonsense like
            # "an industries", where one column ended and the next began.
            or abs(line.top - previous.top) < heights * 0.5
            or _column_of(previous, page) != _column_of(line, page)
            or line.top - previous.bottom > gap_limit
            or previous.x1 < edges.get(_column_of(previous, page), previous.x1) * (1 - SHORT_LINE_SHARE)
            or line.x0 > min(
                (c.x0 for c in page.columns if c.holds(line)),
                default=line.x0,
            ) + INDENT_POINTS
        )
        if broken:
            current = start(kind, heading=heading)
        current.lines.append(line.text)
        previous = line

    return [b for b in blocks if b.lines]


def body_font_size(pages: list[Page]) -> float:
    """The size most of the text is set in, so a heading can be told by face."""
    sizes = [round(ln.size, 1) for page in pages for ln in page.lines if ln.size]
    if not sizes:
        return 0.0
    counts: dict[float, int] = {}
    for size in sizes:
        counts[size] = counts.get(size, 0) + 1
    return max(counts.items(), key=lambda pair: pair[1])[0]


# ---------------------------------------------------------------------------
# metadata
# ---------------------------------------------------------------------------

DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>,;]+", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
VENUE_HINT = re.compile(
    r"\b(proceedings|proc\.|conference|conf\.|journal|transactions|trans\.|symposium"
    r"|workshop|ieee|acm|springer|elsevier|arxiv|preprint|vol\.|volume\s+\d|no\.\s*\d"
    r"|pp\.\s*\d)\b",
    re.IGNORECASE,
)
PLACEHOLDER_TITLES = {"untitled", "unknown", "microsoft word", "document", "pdf"}


@dataclass
class ResearchMetadata:
    """What the document says about itself.

    Blank means "not found" - never a guess. ``unverified`` names the fields
    that were taken from a weaker source than the page itself (today only a
    year read out of the PDF creation date), so the reader can be told which
    ones to check before citing.
    """

    title: str = ""
    authors: str = ""
    year: int | None = None
    venue: str = ""
    doi: str = ""
    unverified: list[str] = field(default_factory=list)


def _plausible_title(value: str) -> bool:
    bare = (value or "").strip()
    if len(bare) < 8 or len(bare) > 400:
        return False
    low = bare.lower()
    if any(p in low for p in PLACEHOLDER_TITLES):
        return False
    # A producer often writes the source filename into /Title.
    return not re.search(r"\.(pdf|docx?|tex|indd)$", low)


def _largest_text_on_first_page(page: Page) -> str:
    """The biggest type in the top half of page one - normally the title."""
    candidates = [
        ln
        for ln in page.lines
        if ln.size and ln.top < page.height * 0.5 and WORD_RE.search(ln.text)
    ]
    if not candidates:
        return ""
    biggest = max(ln.size for ln in candidates)
    titles = [
        ln.text.strip()
        for ln in sorted(candidates, key=lambda ln: ln.top)
        if ln.size >= biggest - 0.3
    ]
    joined = join_wrapped_lines(titles).strip()
    return joined if _plausible_title(joined) else ""


COPYRIGHT_YEAR = re.compile(
    r"(?:©|\(c\)|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", re.IGNORECASE
)


# Producers that write their own name into /Author. "Microsoft Word" has the
# shape of a byline and no rule about shape can tell it from "Jane Doe", so it
# takes a list. Matched whole, because "Writer" on its own is a surname.
SOFTWARE_NAMES = {
    "microsoft word", "microsoft powerpoint", "microsoft office word", "word",
    "adobe acrobat", "acrobat", "adobe indesign", "adobe illustrator",
    "libreoffice", "openoffice", "libreoffice writer", "openoffice writer",
    "pages", "preview", "quartz pdfcontext", "ghostscript", "pdftex", "latex",
    "pdflatex", "xetex", "xelatex", "tex", "google docs", "unknown", "user",
    "administrator", "untitled",
}


def _is_software_name(value: str) -> bool:
    return " ".join((value or "").split()).strip().lower() in SOFTWARE_NAMES


def _embedded_info(data: bytes) -> dict:
    """Title, author and creation year from the information dictionary."""
    try:
        from pypdf import PdfReader

        info = PdfReader(io.BytesIO(data)).metadata or {}
    except Exception:  # noqa: BLE001 - a missing or broken Info dict is normal
        return {}
    created = str(info.get("/CreationDate") or "")
    match = re.search(r"D:(\d{4})", created) or re.search(r"\b(19\d{2}|20\d{2})\b", created)
    year = int(match.group(1)) if match else None
    if year is not None and not 1950 <= year <= 2100:
        year = None
    return {
        "title": str(info.get("/Title") or "").strip(),
        "author": str(info.get("/Author") or "").strip(),
        "created_year": year,
    }


def _abstract_top(page: Page) -> float:
    """Where the abstract starts, which is where the title block ends."""
    for line in sorted(page.lines, key=lambda ln: ln.top):
        if re.match(r"^\s*(abstract|keywords?|index terms)\b", line.text, re.IGNORECASE):
            return line.top
    return page.height * 0.45


def _byline_near_title(pages: list[Page], title: str) -> str:
    """The author line, taken only from the title block.

    Position is half the test and shape is the other half: a byline sits
    between the title and the abstract, and reads like names. Searching the
    whole page for anything with a comma in it is what put a sentence out of
    the body into the author field.
    """
    if not pages:
        return ""
    page = pages[0]
    limit = _abstract_top(page)
    title_words = {word for word in title.lower().split() if len(word) > 3}

    for line in sorted(page.lines, key=lambda ln: ln.top):
        if line.top >= limit:
            break  # past the abstract: no longer the title block
        bare = repair_split_capitals(line.text.strip())
        if not bare:
            continue
        if title_words and set(bare.lower().split()) & title_words:
            continue  # still inside the title
        if looks_like_byline(bare):
            return bare
    return ""


def _year_from_page(pages: list[Page], venue: str, front_text: str) -> int | None:
    """A publication year the document states, or None.

    Tried in the order of how much the document commits to each: a copyright
    line, the venue line, a running head or footer, and last the title block
    when it mentions exactly one year. Several different years means we cannot
    tell which is the publication year, so none is taken.
    """
    copyright_match = COPYRIGHT_YEAR.search(front_text)
    if copyright_match:
        return int(copyright_match.group(1))

    years = {int(y) for y in YEAR_RE.findall(venue or "")}
    if len(years) == 1:
        return years.pop()

    for line in sorted(repeated_edge_lines(pages)):
        years = {int(y) for y in YEAR_RE.findall(line)}
        if len(years) == 1:
            return years.pop()

    years = {int(y) for y in YEAR_RE.findall(front_text[:1200])}
    return years.pop() if len(years) == 1 else None


def extract_metadata(data: bytes, pages: list[Page], front_text: str) -> ResearchMetadata:
    """Read what metadata the document actually carries.

    Order of trust for each field: what the document prints, then the embedded
    information dictionary, then nothing at all. A field that cannot be
    settled is left blank for the reader to fill in - a wrong citation pasted
    into a paper is worse than an obvious gap in the panel.
    """
    meta = ResearchMetadata()
    info = _embedded_info(data)

    embedded_title = info.get("title", "")
    if _plausible_title(embedded_title):
        meta.title = embedded_title
    elif pages:
        meta.title = _largest_text_on_first_page(pages[0])

    # The embedded author field is often a username, a department, or whoever
    # ran the typesetter, so it has to look like a byline as well.
    embedded_author = info.get("author", "")
    if looks_like_byline(embedded_author) and not _is_software_name(embedded_author):
        meta.authors = embedded_author.strip()
    else:
        meta.authors = _byline_near_title(pages, meta.title)

    doi = DOI_RE.search(front_text)
    if doi:
        meta.doi = doi.group(0).rstrip(".")

    for line in front_text.split("\n"):
        if VENUE_HINT.search(line) and 10 <= len(line.strip()) <= 220:
            meta.venue = repair_split_capitals(line.strip())
            break

    meta.year = _year_from_page(pages, meta.venue, front_text)
    if meta.year is None and info.get("created_year"):
        # A hint, not a fact: the creation date is when the file was made,
        # which for a preprint or a rescan is not the publication year.
        meta.year = info["created_year"]
        meta.unverified.append("year")
    return meta


# ---------------------------------------------------------------------------
# the document
# ---------------------------------------------------------------------------


@dataclass
class ResearchSection:
    title: str
    text: str
    kind: str
    page_start: int = 1


@dataclass
class ResearchDocument:
    doc_kind: str
    metadata: ResearchMetadata
    sections: list[ResearchSection] = field(default_factory=list)
    captions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0
    # The line sequence after reordering, for scripts/inspect_pdf only.
    line_flow: str = ""

    @property
    def readable_words(self) -> int:
        return sum(word_count(s.text) for s in self.sections if s.kind in READABLE_KINDS)


def read_outline(data: bytes) -> list[tuple[str, int]]:
    """The PDF outline as (label, zero-based page index) pairs.

    A textbook with real bookmarks is telling us its chapter structure, which
    beats anything a heading heuristic can work out.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        entries: list[tuple[str, int]] = []

        def walk(items) -> None:
            for item in items:
                if isinstance(item, list):
                    walk(item)
                    continue
                label = str(getattr(item, "title", "") or "").strip()
                if not label:
                    continue
                try:
                    page_index = reader.get_destination_page_number(item)
                except Exception:  # noqa: BLE001 - a broken destination is skippable
                    continue
                if page_index is not None:
                    entries.append((label[:300], int(page_index)))

        walk(reader.outline or [])
        entries.sort(key=lambda pair: pair[1])
        return entries
    except Exception:  # noqa: BLE001 - no outline is the common case
        return []


# A numbered section heading proper: a roman or arabic number, never a bare
# letter. "A." opens an IEEE subsection but also an author called A. Reader.
SECTION_NUMBER = re.compile(r"^\s*(?:[IVXLCDM]{1,6}|\d{1,2}(?:\.\d{1,2}){0,3})\s*[.)]\s+\S")
DIVISION_HEADING = re.compile(
    r"^\s*(chapter|part|section|unit|lecture|module)\s+[\dIVXLC]+\b", re.IGNORECASE
)


def opens_a_section(block: "Block") -> bool:
    """Is this heading unmistakably the start of a numbered or named section?

    Used to find where the title block ends. The lines above the first real
    heading are the title, the byline and the venue - and a byline beginning
    "A. Reader" looks exactly like an IEEE subsection heading, so position is
    the only thing that reliably tells them apart.
    """
    if not block.heading:
        return False
    title = block.text().strip()
    if DIVISION_HEADING.match(title) or SECTION_NUMBER.match(title):
        return True
    return bool(NAMED_HEADING.fullmatch(strip_number_prefix(title)))


def _demote_title_block(blocks: list[Block]) -> None:
    """Anything above the first real section heading is title-block text."""
    first = next((i for i, b in enumerate(blocks) if opens_a_section(b)), None)
    if not first:  # nothing found, or it is already the first block
        return
    for block in blocks[:first]:
        block.heading = False


def _blocks_to_sections(blocks: list[Block]) -> tuple[list[ResearchSection], list[str], dict]:
    """Fold blocks into sections at each heading."""
    _demote_title_block(blocks)
    sections: list[ResearchSection] = []
    captions: list[str] = []
    counts = {EQUATION: 0, TABLE_ROW: 0}

    title = ""
    kind = FRONT_MATTER  # everything before the first heading is the title block
    page_start = blocks[0].page if blocks else 1
    paragraphs: list[str] = []
    seen_references = False

    def flush() -> None:
        nonlocal paragraphs
        body = "\n\n".join(p for p in merge_split_paragraphs(paragraphs) if p.strip())
        if body.strip() or title:
            sections.append(
                ResearchSection(title=title, text=body.strip(), kind=kind, page_start=page_start)
            )
        paragraphs = []

    for block in blocks:
        if block.heading:
            flush()
            title = block.text().strip()
            kind = section_kind_for(title, seen_references=seen_references)
            if kind == REFERENCES:
                seen_references = True
            page_start = block.page
            continue

        if block.kind == CAPTION:
            captions.append(block.text().strip())
            continue
        if block.kind in (EQUATION, TABLE_ROW):
            counts[block.kind] += len(block.lines)
            marker = "[equation omitted]" if block.kind == EQUATION else "[table omitted]"
            if not paragraphs or paragraphs[-1] != marker:
                paragraphs.append(marker)
            continue
        paragraphs.append(block.text().strip())

    flush()
    sections = [s for s in sections if s.text or s.title]

    # If every rule fired and nothing is left to read, the labelling is wrong -
    # better to hand over the text than to show an empty document. Same stance
    # as the book path takes with front matter.
    if sections and not any(s.kind in READABLE_KINDS for s in sections):
        for section in sections:
            if section.kind == FRONT_MATTER:
                section.kind = BODY
    return sections, captions, counts


# The title, the byline and the venue together. Anything longer is a real
# front-matter section - a preface, a disclaimer - and not just a title block.
TITLE_BLOCK_MAX_WORDS = 120


def drop_title_block(sections: list["ResearchSection"]) -> list["ResearchSection"]:
    """Leave out the title block, which is already the metadata.

    Keeping it put an untitled entry at the top of every document, shown in
    the section list as "Title page", holding the same words as the citation
    panel beside it and nothing to read.
    """
    kept = [
        section
        for section in sections
        if not (
            section.kind == FRONT_MATTER
            and not section.title
            and word_count(section.text) <= TITLE_BLOCK_MAX_WORDS
        )
    ]
    return kept or sections


def _outline_sections(
    data: bytes, pages: list[Page], blocks: list[Block]
) -> list[ResearchSection] | None:
    """Sections cut at the pages the outline points to, or None if unusable."""
    outline = read_outline(data)
    if len(outline) < MIN_OUTLINE_ENTRIES:
        return None

    bounds = [(label, start) for label, start in outline]
    sections: list[ResearchSection] = []
    for i, (label, start) in enumerate(bounds):
        end = bounds[i + 1][1] if i + 1 < len(bounds) else len(pages)
        in_range = [b for b in blocks if start + 1 <= b.page <= end]
        paragraphs = [
            b.text().strip()
            for b in in_range
            if b.kind == TEXT and not (b.heading and b.text().strip() == label)
        ]
        text = "\n\n".join(p for p in merge_split_paragraphs(paragraphs) if p.strip())
        if not text.strip():
            continue
        sections.append(
            ResearchSection(title=label, text=text.strip(), kind=BODY, page_start=start + 1)
        )
    return sections or None


def extract_research_pdf(data: bytes, doc_kind: str | None = None) -> ResearchDocument:
    """Read a research PDF into sections. Raises ExtractionError for a file we
    cannot or should not handle."""
    if not data.startswith(b"%PDF-"):
        raise ExtractionError("That file is not a PDF.", "not_a_pdf")

    try:
        pages = read_pages(data)
    except LayoutUnavailable as exc:
        raise ExtractionError("That PDF could not be read.", "pdf_unreadable") from exc
    if not pages:
        raise ExtractionError("That PDF has no pages.", "pdf_empty")

    body_size = body_font_size(pages)
    repeated = repeated_edge_lines(pages)
    blocks: list[Block] = []
    flow: list[str] = []
    for page in pages:
        page_items = page_blocks(page, repeated, body_size)
        blocks.extend(page_items)
        flow.extend(line for block in page_items for line in block.lines)

    total_words = sum(word_count(b.text()) for b in blocks)
    if total_words < MIN_TEXT_WORDS:
        raise ExtractionError(
            "No text could be extracted - this looks like a scanned PDF. "
            "ReadBack needs a PDF with a real text layer, and does not run OCR.",
            "pdf_no_text_layer",
        )

    outline = read_outline(data)
    if doc_kind not in DOC_KINDS:
        doc_kind = TEXTBOOK if len(outline) >= MIN_OUTLINE_ENTRIES else PAPER

    sections, captions, counts = _blocks_to_sections(blocks)
    sections = drop_title_block(sections)
    used_outline = False
    if doc_kind == TEXTBOOK:
        from_outline = _outline_sections(data, pages, blocks)
        if from_outline:
            sections, used_outline = from_outline, True

    front_text = "\n".join(
        ln.text for ln in sorted(pages[0].lines, key=lambda ln: ln.top)
    )
    metadata = extract_metadata(data, pages, front_text)

    warnings: list[str] = []
    multi_column = [p.number for p in pages if p.column_count > 1]
    if multi_column:
        warnings.append(
            f"{len(multi_column)} of {len(pages)} pages are multi-column; "
            "columns were read down, not across."
        )
    if counts[EQUATION]:
        warnings.append(
            f"{counts[EQUATION]} equation-like lines were marked "
            "[equation omitted] rather than read as prose."
        )
    if counts[TABLE_ROW]:
        warnings.append(
            f"{counts[TABLE_ROW]} table rows were marked [table omitted]; "
            "tables are not reconstructed."
        )
    if captions:
        warnings.append(f"{len(captions)} figure or table captions were kept aside.")
    if used_outline:
        warnings.append(f"Chapters came from the PDF outline ({len(outline)} bookmarks).")
    if not any(s.kind == REFERENCES for s in sections):
        warnings.append("No reference list was found, so none could be set aside.")
    for field_name in ("title", "authors", "year", "venue", "doi"):
        if not getattr(metadata, field_name):
            warnings.append(f"Metadata field {field_name!r} could not be read; left blank.")

    return ResearchDocument(
        doc_kind=doc_kind,
        metadata=metadata,
        sections=sections,
        captions=captions,
        warnings=warnings,
        page_count=len(pages),
        line_flow="\n".join(flow),
    )
