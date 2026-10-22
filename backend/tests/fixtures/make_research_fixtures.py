"""Generate the research-document PDF fixtures under tests/fixtures/research/.

Run once; the outputs are committed so the test suite needs no network and no
extra tooling:

    python tests/fixtures/make_research_fixtures.py

The PDFs are written by hand (no reportlab) for the same reason the upload
fixtures are: a committed fixture should not depend on a generator library.
Each line is placed with an absolute text matrix, so these fixtures reproduce
the two things that break naive extraction - column geometry and
content-stream order.

All prose is invented filler. Nothing here is copied from a real paper.
"""

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "research"

# A4 at 72dpi, with the two-column geometry an IEEE template uses.
PAGE_W, PAGE_H = 595, 842
MARGIN_X, MARGIN_TOP = 54, 788
COL_W = 240
COL1_X = MARGIN_X
COL2_X = MARGIN_X + COL_W + 17  # 17pt gutter
LINE_H = 11.5
BODY_SIZE = 9.5


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def wrap(text: str, chars: int) -> list[str]:
    """Break text into lines of at most `chars` characters."""
    words, lines, current = text.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > chars:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


class Item:
    """One positioned line of text."""

    __slots__ = ("x", "y", "text", "size")

    def __init__(self, x: float, y: float, text: str, size: float = BODY_SIZE):
        self.x, self.y, self.text, self.size = x, y, text, size


def column(x: float, top: float, lines: list[str], size: float = BODY_SIZE) -> list[Item]:
    return [Item(x, top - i * LINE_H, line, size) for i, line in enumerate(lines)]


class PdfBuilder:
    """A minimal PDF writer: absolute-positioned text, optional outline, Info."""

    def __init__(self, title: str = "", author: str = ""):
        self.pages: list[list[Item]] = []
        self.title = title
        self.author = author
        self.outline: list[tuple[str, int]] = []  # (label, page index)

    def add_page(self, items: list[Item]) -> None:
        self.pages.append(items)

    def _content(self, items: list[Item]) -> str:
        return "\n".join(
            f"BT /F1 {it.size:g} Tf 1 0 0 1 {it.x:g} {it.y:g} Tm "
            f"({_escape(it.text)}) Tj ET"
            for it in items
        )

    def build(self) -> bytes:
        n = len(self.pages)
        # Fixed object numbering, worked out before anything is written.
        catalog_id, pages_id, font_id = 1, 2, 3
        page_ids = [4 + 2 * i for i in range(n)]
        content_ids = [5 + 2 * i for i in range(n)]
        next_id = 4 + 2 * n
        outline_root_id = next_id if self.outline else 0
        outline_item_ids: list[int] = []
        if self.outline:
            next_id += 1
            outline_item_ids = [next_id + i for i in range(len(self.outline))]
            next_id += len(self.outline)
        info_id = next_id

        objects: dict[int, str] = {}
        outlines_ref = f" /Outlines {outline_root_id} 0 R" if self.outline else ""
        objects[catalog_id] = f"<< /Type /Catalog /Pages {pages_id} 0 R{outlines_ref} >>"
        kids = " ".join(f"{pid} 0 R" for pid in page_ids)
        objects[pages_id] = f"<< /Type /Pages /Kids [{kids}] /Count {n} >>"
        objects[font_id] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

        for i, items in enumerate(self.pages):
            objects[page_ids[i]] = (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_ids[i]} 0 R >>"
            )
            stream = self._content(items)
            objects[content_ids[i]] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"

        if self.outline:
            objects[outline_root_id] = (
                f"<< /Type /Outlines /First {outline_item_ids[0]} 0 R "
                f"/Last {outline_item_ids[-1]} 0 R /Count {len(self.outline)} >>"
            )
            for i, (label, page_index) in enumerate(self.outline):
                parts = [
                    f"/Title ({_escape(label)})",
                    f"/Parent {outline_root_id} 0 R",
                    f"/Dest [{page_ids[page_index]} 0 R /Fit]",
                ]
                if i > 0:
                    parts.append(f"/Prev {outline_item_ids[i - 1]} 0 R")
                if i + 1 < len(outline_item_ids):
                    parts.append(f"/Next {outline_item_ids[i + 1]} 0 R")
                objects[outline_item_ids[i]] = "<< " + " ".join(parts) + " >>"

        info_parts = []
        if self.title:
            info_parts.append(f"/Title ({_escape(self.title)})")
        if self.author:
            info_parts.append(f"/Author ({_escape(self.author)})")
        objects[info_id] = ("<< " + " ".join(info_parts) + " >>") if info_parts else "<< >>"

        out = bytearray(b"%PDF-1.4\n")
        offsets: dict[int, int] = {}
        for obj_id in sorted(objects):
            offsets[obj_id] = len(out)
            out += f"{obj_id} 0 obj\n{objects[obj_id]}\nendobj\n".encode("latin-1")

        highest = max(objects)
        xref_at = len(out)
        out += f"xref\n0 {highest + 1}\n".encode("latin-1")
        out += b"0000000000 65535 f \n"
        for obj_id in range(1, highest + 1):
            if obj_id in offsets:
                out += f"{offsets[obj_id]:010d} 00000 n \n".encode("latin-1")
            else:  # a gap in the numbering; mark it free
                out += b"0000000000 65535 f \n"
        out += (
            f"trailer\n<< /Size {highest + 1} /Root {catalog_id} 0 R "
            f"/Info {info_id} 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
        ).encode("latin-1")
        return bytes(out)


# ---------------------------------------------------------------------------
# content
# ---------------------------------------------------------------------------

TITLE = "Attention Scaffolding for Sustained Long-Form Reading"
AUTHORS = "A. Reader, B. Writer, and C. Editor"
VENUE = "IEEE Transactions on Learning Technologies, vol. 14, no. 3, 2021"
DOI = "10.1109/TLT.2021.1234567"

ABSTRACT = (
    "Long-form reading has declined among undergraduates while short-form media "
    "consumption has risen. We present a reading platform that borrows retention "
    "mechanics from streaming interfaces and applies them to book reading. In a "
    "three-week study with twenty participants we measure session length, "
    "comprehension retention and self-reported engagement. Sessions lengthened by "
    "a mean of four minutes and comprehension scores did not decline, suggesting "
    "that habit scaffolding need not come at the cost of depth."
)

# The body, as (heading or None, text) pairs.
BODY = [
    (
        "I. INTRODUCTION",
        "The activation energy required to begin a reading session is dispropor"
        "tionately high when compared with low-effort alternatives. Prior work "
        "attributes this to the absence of automated progression rather than to "
        "any deficit in reading ability. We take the position that modern "
        "behavioural mechanics should be repurposed rather than resisted.",
    ),
    (
        None,
        "Our contribution is threefold. First, we describe a segmentation method "
        "that cuts a book at narrative boundaries. Second, we report a pilot "
        "deployment. Third, we release the instrumentation schema so that other "
        "groups can replicate the measurement.",
    ),
    (
        "II. RELATED WORK",
        "Dual coding theory holds that symbolic and imagistic representations are "
        "encoded along separate pathways. The original formulation by Paivio has "
        "been extended to reading comprehension by a number of authors. "
        "Separately, the literature on variable reward scheduling describes why "
        "intermittent reinforcement sustains engagement more effectively than "
        "fixed schedules.",
    ),
    (
        "III. METHOD",
        "Participants were recruited from an undergraduate population. Each was "
        "assigned one of five public-domain novels. The platform logged every "
        "user-facing interaction with a timestamp, and active reading time "
        "excluded intervals during which the browser tab was hidden.",
    ),
    (
        None,
        "Segment length was held between four hundred and six hundred words. The "
        "boundary detector preferred positions at which a paragraph ended with an "
        "unresolved question, on the assumption that such positions function as "
        "cliffhangers.",
    ),
    (
        "IV. RESULTS",
        "Mean session length rose from eleven to fifteen minutes over the study "
        "period. Comprehension checkpoint scores were flat, with a mean of 0.72 "
        "in week one and 0.74 in week three. Eighteen of twenty participants "
        "reported that the recap feature reduced the friction of resuming a book.",
    ),
    (
        "V. DISCUSSION",
        "The absence of a comprehension penalty is the result we consider most "
        "load-bearing. A platform that lengthens sessions by degrading attention "
        "quality would not be worth deploying. We note that our sample is small "
        "and drawn from a single institution.",
    ),
    (
        "VI. CONCLUSION",
        "Habit scaffolding borrowed from streaming interfaces lengthened reading "
        "sessions without measurable comprehension cost. Future work should test "
        "whether revealing artwork suppresses self-generated imagery.",
    ),
]

REFERENCES = [
    "[1] A. Paivio, Mental Representations: A Dual Coding Approach. Oxford, "
    "U.K.: Oxford Univ. Press, 1986.",
    '[2] B. J. Fogg, "A behavior model for persuasive design," in Proc. 4th '
    "Int. Conf. Persuasive Technol., 2009, pp. 1-7.",
    '[3] M. Mangen and A. van der Weel, "The evolution of reading in the age '
    'of digitisation," J. Res. Reading, vol. 39, no. 1, pp. 116-124, 2016.',
    '[4] K. Thompson and R. Patel, "Micro-sessions and retention in digital '
    'reading," IEEE Trans. Learn. Technol., vol. 12, no. 2, pp. 201-213, 2019.',
]

CAPTION = (
    "Fig. 1. Mean active session length by study week. Error bars show one "
    "standard deviation."
)
EQUATION = "L(t) = a log(1 + bt) + e,    e ~ N(0, s^2)        (1)"
TABLE_ROWS = [
    "Week   N    Mean    SD",
    "1      20   11.2    3.4",
    "2      20   13.8    3.9",
    "3      19   15.1    4.2",
]

RUNNING_HEADER = "IEEE TRANSACTIONS ON LEARNING TECHNOLOGIES, VOL. 14, NO. 3, MARCH 2021"
COL_CHARS = 52  # characters that fit a 240pt column at 9.5pt Helvetica
# Each body paragraph is emitted this many times. Filler, but it makes the
# paper run to several pages, which is the only way the fixture can exercise
# running heads, folios and a page break in the middle of a column.
PARAGRAPH_REPEAT = 6


def _column_lines() -> list[str]:
    """The paper body as a flat list of column lines, headings included."""
    lines: list[str] = []
    for heading, text in BODY:
        if heading:
            lines.append("")
            lines.append(heading)
        for _ in range(PARAGRAPH_REPEAT):
            lines.extend(wrap(text, COL_CHARS))
            lines.append("")
        lines.pop()
    # A caption, an equation and a table, none of which should read as prose.
    lines.append("")
    lines.extend(wrap(CAPTION, COL_CHARS))
    lines.append("")
    lines.append(EQUATION)
    lines.append("")
    lines.extend(TABLE_ROWS)
    lines.append("")
    lines.append("REFERENCES")
    for ref in REFERENCES:
        lines.extend(wrap(ref, COL_CHARS))
    return lines


def _hyphenate_a_line(lines: list[str]) -> list[str]:
    """Break one long word across a line end, the way LaTeX does, so the
    joiner has a real hyphenated wrap to repair."""
    return [
        line[: -len("dispropor")] + "dispropor-" if line.endswith("dispropor") else line
        for line in lines
    ]


def build_two_column(interleaved: bool) -> bytes:
    """An IEEE-style two-column paper.

    interleaved=True emits each visual row as "left line, right line", which is
    what a PDF whose producer ships text row by row looks like.
    interleaved=False emits all of column one and then all of column two, which
    is what pdflatex usually produces. The two orders behave differently under
    naive extraction, which is why both fixtures exist.
    """
    pdf = PdfBuilder(title=TITLE, author=AUTHORS)
    lines = _hyphenate_a_line(_column_lines())

    abstract_lines = wrap(ABSTRACT, 110)
    head = [
        Item(MARGIN_X, MARGIN_TOP, TITLE, 15),
        Item(MARGIN_X, MARGIN_TOP - 22, AUTHORS, 10),
        Item(MARGIN_X, MARGIN_TOP - 36, VENUE, 8),
        Item(MARGIN_X, MARGIN_TOP - 48, f"Digital Object Identifier {DOI}", 8),
        Item(MARGIN_X, MARGIN_TOP - 70, "Abstract-" + abstract_lines[0], 9),
    ]
    for i, line in enumerate(abstract_lines[1:], start=1):
        head.append(Item(MARGIN_X, MARGIN_TOP - 70 - i * LINE_H, line, 9))
    first_col_top = MARGIN_TOP - 70 - len(abstract_lines) * LINE_H - 20

    rows_page1 = int((first_col_top - 70) // LINE_H)
    rows_later = int((MARGIN_TOP - 30 - 70) // LINE_H)

    cursor = 0
    page_no = 1
    while cursor < len(lines):
        if page_no == 1:
            items = list(head)
            top, rows = first_col_top, rows_page1
        else:
            items = [Item(MARGIN_X, MARGIN_TOP, RUNNING_HEADER, 7)]
            top, rows = MARGIN_TOP - 30, rows_later

        left = lines[cursor : cursor + rows]
        right = lines[cursor + rows : cursor + 2 * rows]
        cursor += 2 * rows

        if interleaved:
            for i in range(max(len(left), len(right))):
                if i < len(left) and left[i]:
                    items.append(Item(COL1_X, top - i * LINE_H, left[i]))
                if i < len(right) and right[i]:
                    items.append(Item(COL2_X, top - i * LINE_H, right[i]))
        else:
            items += [it for it in column(COL1_X, top, left) if it.text]
            items += [it for it in column(COL2_X, top, right) if it.text]

        items.append(Item(PAGE_W / 2 - 6, 50, str(page_no), 8))  # page number
        pdf.add_page(items)
        page_no += 1

    return pdf.build()


TEXTBOOK_CHAPTERS = [
    (
        "Chapter 1. Foundations of Attention",
        "Attention is not a single faculty but a family of mechanisms that "
        "select among competing inputs. This chapter introduces the vocabulary "
        "used throughout the book and distinguishes sustained attention from "
        "selective attention. The distinction matters because the two respond "
        "differently to training, and a method that improves one may leave the "
        "other untouched.",
    ),
    (
        "Chapter 2. Reading and Working Memory",
        "Reading a long narrative requires the reader to hold a situation model "
        "in working memory across hours of elapsed time. We review the evidence "
        "that such models degrade predictably with time away from the text, and "
        "we consider what follows for the design of reading tools.",
    ),
    (
        "Chapter 3. Measuring Engagement",
        "Self-report and behavioural measures of engagement often disagree. "
        "This chapter sets out the instruments used in the studies that follow, "
        "including the vividness of visual imagery questionnaire and a simple "
        "comprehension checkpoint with known reliability.",
    ),
]


def build_textbook() -> bytes:
    """A single-column textbook with a real PDF outline and running headers."""
    pdf = PdfBuilder(title="A Textbook of Reading and Attention", author="D. Lecturer")
    chars = 95
    for index, (heading, text) in enumerate(TEXTBOOK_CHAPTERS):
        items = [
            Item(MARGIN_X, MARGIN_TOP, "A TEXTBOOK OF READING AND ATTENTION", 7),
            Item(MARGIN_X, MARGIN_TOP - 34, heading, 14),
        ]
        body: list[str] = []
        for _ in range(4):  # repeated so each chapter has enough words to segment
            body.extend(wrap(text, chars))
            body.append("")
        items += [it for it in column(MARGIN_X, MARGIN_TOP - 60, body) if it.text]
        items.append(Item(PAGE_W / 2 - 6, 50, str(index + 1), 8))
        pdf.add_page(items)
        pdf.outline.append((heading, index))
    return pdf.build()




# ---------------------------------------------------------------------------
# A paper shaped like the one that produced a wrong citation
# ---------------------------------------------------------------------------

MESSY_TITLE = "Detecting Intrusions with Honeypots"
# No byline at all: the affiliation stands where authors usually go. The old
# extractor walked past it and took a sentence out of the body instead.
MESSY_AFFILIATION = "Department of Computer Science, University of Somewhere"
MESSY_ABSTRACT = (
    "We present a dataset of intrusion attempts gathered from a public "
    "honeypot and describe the labelling procedure used to prepare it."
)
# The sentence that ended up in the author field of every citation copied.
MESSY_BODY_SENTENCE = (
    "Honeypot and labeled according to Enterprise Tactics of MITRE ATT&CK "
    "to ensure dataset credibility."
)


def build_messy_paper() -> bytes:
    """A paper with no byline, no date, and a drop-cap heading.

    Everything here is a shape that made the extractor invent metadata:
    nothing to read as authors, nothing to read as a year, and a heading whose
    first letter is set as its own run so it extracts as "T HE".
    """
    pdf = PdfBuilder(title=MESSY_TITLE, author="Microsoft Word")
    items = [
        Item(MARGIN_X, MARGIN_TOP, MESSY_TITLE, 15),
        Item(MARGIN_X, MARGIN_TOP - 24, MESSY_AFFILIATION, 9),
    ]
    abstract_lines = wrap(MESSY_ABSTRACT, 100)
    items.append(Item(MARGIN_X, MARGIN_TOP - 52, "Abstract-" + abstract_lines[0], 9))
    for i, line in enumerate(abstract_lines[1:], start=1):
        items.append(Item(MARGIN_X, MARGIN_TOP - 52 - i * LINE_H, line, 9))

    top = MARGIN_TOP - 52 - len(abstract_lines) * LINE_H - 22
    # The drop cap: the first letter is its own run, a few points left of the
    # rest of the word, which is what makes extraction hand back "T HE".
    items.append(Item(MARGIN_X, top, "T", 11))
    items.append(Item(MARGIN_X + 11, top, "HE Internet of Things", 11))

    body = []
    for _ in range(6):
        body.extend(wrap(MESSY_BODY_SENTENCE, 95))
        body.extend(
            wrap(
                "Traffic was captured over six months and replayed in a closed "
                "network for analysis. The resulting corpus is available on request.",
                95,
            )
        )
        body.append("")
    items += [it for it in column(MARGIN_X, top - 2 * LINE_H, body) if it.text]
    pdf.add_page(items)

    # Two more pages carrying a running head. A head has to repeat before it
    # can be recognised as one, so a two-page fixture would leave it looking
    # like a section heading - which is a property of the fixture, not of the
    # extractor.
    for page_no in (2, 3):
        later = [Item(MARGIN_X, MARGIN_TOP, "DETECTING INTRUSIONS WITH HONEYPOTS", 7)]
        more = []
        for _ in range(6):
            more.extend(wrap("The evaluation compares three detectors on the corpus.", 95))
            more.append("")
        later += [it for it in column(MARGIN_X, MARGIN_TOP - 40, more) if it.text]
        later.append(Item(PAGE_W / 2 - 6, 50, str(page_no), 8))
        pdf.add_page(later)
    return pdf.build()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    written = {
        "twocol_interleaved.pdf": build_two_column(interleaved=True),
        "twocol_columnmajor.pdf": build_two_column(interleaved=False),
        "textbook_outline.pdf": build_textbook(),
        "messy_paper.pdf": build_messy_paper(),
    }
    for name, data in written.items():
        (OUT / name).write_bytes(data)
        print(f"  {name:26s} {len(data):>8,d} bytes")
    print(f"Wrote {len(written)} fixtures to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
