"""Geometry for PDFs: where the text sits on the page, and in what order to read it.

The book pipeline asks pypdf for a page of text and takes what it gets. That is
fine for a novel, which is one column, and wrong for a journal paper, which is
two: the text comes back with the columns read across rather than down, so every
sentence is cut in half by its neighbour.

This module reads *positions* rather than text. From line boxes it works out how
many columns a page has, splits any line a parser merged across the gutter,
orders the result the way a person reads it, and reports what repeats at the page
edges (running heads and folios). It stores nothing and calls nothing.

pdfminer.six does the parsing. It is MIT-licensed, pure Python apart from
cryptography (already a dependency), and gives character-level boxes - which is
what makes splitting a merged line possible. PyMuPDF would also do the job but
is AGPL, which is not a licence this project can take on.
"""

import io
import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# How wide a vertical gap between two groups of line starts has to be, as a
# share of page width, before we believe it is a column gutter.
MIN_COLUMN_SEPARATION = 0.22
# A column has to hold this many lines, and this share of the page's lines,
# before it counts. Stops a centred title or a stray marginal note from being
# read as a column of its own.
MIN_COLUMN_LINES = 4
MIN_COLUMN_SHARE = 0.12
MAX_COLUMNS = 3
# Line starts within this many points are the same column.
X_BIN = 4.0

# Bands at the top and bottom of the page where running heads and page numbers
# live. Deliberately narrow: real body text starts below this.
EDGE_BAND = 0.075
# A line is furniture when it appears in the edge band of at least this share
# of pages.
EDGE_REPEAT_SHARE = 0.5
# ...and never when it is long enough to be a real sentence.
MAX_FURNITURE_CHARS = 110

PAGE_NUMBER = re.compile(r"^\s*[\[\(\-–—]*\s*(\d{1,4}|[ivxlcdm]{1,7})\s*[\]\)\-–—]*\s*$", re.I)


class LayoutUnavailable(RuntimeError):
    """pdfminer could not read the file, or is not installed."""


@dataclass
class Line:
    """One line of text with its box, in top-down coordinates."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float = 0.0
    # Character boxes, kept only long enough to split a merged line. Cleared
    # afterwards so a long document does not carry them around.
    chars: list[tuple[float, float, str]] = field(default_factory=list, repr=False)

    @property
    def width(self) -> float:
        return self.x1 - self.x0


@dataclass
class Column:
    x0: float
    x1: float

    def holds(self, line: Line) -> bool:
        """True when the line starts in this column. Start, not overlap: a line
        that spills past the gutter still belongs to the column it begins in."""
        return self.x0 - X_BIN <= line.x0 < self.x1


@dataclass
class Page:
    number: int
    width: float
    height: float
    lines: list[Line]
    columns: list[Column]

    @property
    def column_count(self) -> int:
        return max(1, len(self.columns))


# ---------------------------------------------------------------------------
# reading the file
# ---------------------------------------------------------------------------


def _laparams():
    from pdfminer.layout import LAParams

    # boxes_flow=None turns off pdfminer's own reading-order guessing: we want
    # raw boxes and will order them ourselves. char_margin is pulled in from
    # the default 2.0 because a two-column gutter is often narrower than that,
    # and anything wider merges the columns into single lines before we see
    # them. Lines that still get merged are split later from their characters.
    return LAParams(char_margin=1.0, line_margin=0.4, word_margin=0.1,
                    boxes_flow=None, detect_vertical=False)


def read_pages(data: bytes, max_pages: int | None = None) -> list[Page]:
    """Parse the PDF into pages of positioned lines, columns already worked out."""
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTChar, LTTextContainer, LTTextLine
        from pdfminer.pdfparser import PDFSyntaxError
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise LayoutUnavailable("pdfminer.six is not installed") from exc

    pages: list[Page] = []
    try:
        for index, layout in enumerate(extract_pages(io.BytesIO(data), laparams=_laparams())):
            if max_pages is not None and index >= max_pages:
                break
            height = float(layout.height)
            raw: list[Line] = []
            for element in layout:
                if not isinstance(element, LTTextContainer):
                    continue
                for line in element:
                    if not isinstance(line, LTTextLine):
                        continue
                    text = line.get_text().strip()
                    if not text:
                        continue
                    chars = [
                        (float(c.x0), float(c.x1), c.get_text())
                        for c in line
                        if isinstance(c, LTChar)
                    ]
                    sizes = [float(c.size) for c in line if isinstance(c, LTChar)]
                    raw.append(
                        Line(
                            text=text,
                            x0=float(line.x0),
                            x1=float(line.x1),
                            top=height - float(line.y1),
                            bottom=height - float(line.y0),
                            size=round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
                            chars=chars,
                        )
                    )
            columns = detect_columns(raw, float(layout.width))
            lines = split_merged_lines(raw, columns)
            for line in lines:
                line.chars = []  # geometry is settled; drop the per-character data
            lines.sort(key=lambda ln: (round(ln.top, 1), ln.x0))
            pages.append(
                Page(
                    number=index + 1,
                    width=float(layout.width),
                    height=height,
                    lines=lines,
                    columns=columns,
                )
            )
    except PDFSyntaxError as exc:
        raise LayoutUnavailable(f"not a readable PDF ({exc})") from exc
    except LayoutUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - pdfminer raises a wide range
        raise LayoutUnavailable(f"{type(exc).__name__}") from exc
    return pages


# ---------------------------------------------------------------------------
# columns
# ---------------------------------------------------------------------------


def detect_columns(lines: list[Line], page_width: float) -> list[Column]:
    """Group line starts into columns.

    Clustering on the left edge, rather than looking for an empty vertical
    band, is what makes this survive a parser that has already merged some
    lines across the gutter: those merged lines still *start* in column one, so
    column two keeps its own cluster of line starts.

    Returns [] for a single-column page, so a caller can treat "no columns"
    and "one column" the same way.
    """
    if len(lines) < MIN_COLUMN_LINES * 2:
        return []

    # Bin the left edges and keep the populated bins in order.
    counts: dict[int, int] = {}
    for line in lines:
        counts[int(line.x0 // X_BIN)] = counts.get(int(line.x0 // X_BIN), 0) + 1

    # Merge neighbouring bins into clusters: justification jitters a line start
    # by a point or two, which would otherwise look like two columns.
    clusters: list[tuple[float, int]] = []  # (left edge, line count)
    for bin_index in sorted(counts):
        x = bin_index * X_BIN
        if clusters and x - clusters[-1][0] <= X_BIN * 1.5:
            left, n = clusters[-1]
            clusters[-1] = (left, n + counts[bin_index])
        else:
            clusters.append((x, counts[bin_index]))

    minimum = max(MIN_COLUMN_LINES, int(len(lines) * MIN_COLUMN_SHARE))
    strong = [(x, n) for x, n in clusters if n >= minimum]
    if len(strong) < 2:
        return []

    # Keep the clusters that are far enough apart to be columns rather than an
    # indent. Walk left to right, taking a cluster only once it clears the gap.
    gap = page_width * MIN_COLUMN_SEPARATION
    kept = [strong[0]]
    for x, n in strong[1:]:
        if x - kept[-1][0] >= gap:
            kept.append((x, n))
    if len(kept) < 2:
        return []
    kept = kept[:MAX_COLUMNS]

    columns: list[Column] = []
    for i, (x, _) in enumerate(kept):
        right = kept[i + 1][0] if i + 1 < len(kept) else max(ln.x1 for ln in lines) + X_BIN
        columns.append(Column(x0=x, x1=right))
    return columns


# A merged pair of column lines has the whole gutter sitting empty in the
# middle of it. A genuinely full-width line - a title, an abstract, a running
# head - has characters running straight across. Word spacing never reaches
# this, so the gap is what tells the two apart. Measured against the font size,
# because a gap that is wide in 9pt body text is one character in a 15pt title.
GUTTER_MIN_GAP = 6.0
GUTTER_GAP_EMS = 1.0


def _gap_across(line: Line, boundary: float) -> float:
    """The width of the empty space straddling ``boundary`` on this line.

    Measured between *adjacent* characters. Taking it between the last
    character ending before the boundary and the first starting after it looks
    equivalent but is not: a character sitting astride the boundary belongs to
    neither set, and its own width then reads as a gap - which is enough to cut
    a title in half.
    """
    chars = sorted(line.chars, key=lambda c: c[0])
    for left, right in zip(chars, chars[1:]):
        if left[0] <= boundary <= right[0]:
            return max(0.0, right[0] - left[1])
    return 0.0


def _gutter_gap_threshold(line: Line) -> float:
    return max(GUTTER_MIN_GAP, (line.size or 9.0) * GUTTER_GAP_EMS)


def split_merged_lines(lines: list[Line], columns: list[Column]) -> list[Line]:
    """Cut any line that a parser ran across a gutter back into column pieces.

    Without this, the handful of lines whose inter-column gap fell under the
    parser threshold stay joined, and each one glues a sentence from column one
    onto an unrelated sentence from column two. A line is only cut where the
    gutter is genuinely blank, so full-width text is left whole.
    """
    if len(columns) < 2:
        return lines

    boundaries = [c.x0 for c in columns[1:]]
    out: list[Line] = []
    for line in lines:
        if not line.chars:
            out.append(line)
            continue
        needed = _gutter_gap_threshold(line)
        crossed = [
            b
            for b in boundaries
            if line.x0 < b - X_BIN < line.x1 and _gap_across(line, b) >= needed
        ]
        if not crossed:
            out.append(line)
            continue
        out.extend(_split_at(line, crossed))
    return out


def _split_at(line: Line, boundaries: list[float]) -> list[Line]:
    """Split one line into pieces at the given x positions, using its chars."""
    edges = [-float("inf"), *sorted(boundaries), float("inf")]
    pieces: list[Line] = []
    for left, right in zip(edges, edges[1:]):
        chars = [c for c in line.chars if left - X_BIN <= c[0] < right - X_BIN]
        text = "".join(c[2] for c in chars).strip()
        if not text:
            continue
        pieces.append(
            Line(
                text=text,
                x0=min(c[0] for c in chars),
                x1=max(c[1] for c in chars),
                top=line.top,
                bottom=line.bottom,
                size=line.size,
                chars=chars,
            )
        )
    return pieces or [line]


# ---------------------------------------------------------------------------
# reading order
# ---------------------------------------------------------------------------


def spans_columns(line: Line, columns: list[Column]) -> bool:
    """True for a line that runs across the whole text block - a title, an
    abstract, a full-width figure - rather than sitting inside one column."""
    if len(columns) < 2:
        return False
    # It has to start in the first column and reach well into the last one.
    reach = columns[-1].x0 + (columns[-1].x1 - columns[-1].x0) * 0.25
    return line.x0 < columns[1].x0 - X_BIN and line.x1 >= reach


def reading_order(page: Page) -> list[Line]:
    """The page's lines in the order a person reads them.

    Full-width lines divide the page into horizontal bands. Within a band the
    columns are read in turn, top to bottom. That keeps a title above the
    columns, a full-width table in the middle, and a footnote below, all in the
    right place - which a plain "all of column one, then all of column two"
    rule gets wrong.
    """
    if page.column_count < 2:
        return sorted(page.lines, key=lambda ln: (round(ln.top, 1), ln.x0))

    ordered: list[Line] = []
    band: list[Line] = []

    def flush() -> None:
        if not band:
            return
        for col in page.columns:
            ordered.extend(
                sorted(
                    (ln for ln in band if col.holds(ln)),
                    key=lambda ln: (round(ln.top, 1), ln.x0),
                )
            )
        # Anything that fell outside every column still has to be read.
        placed = {id(ln) for ln in ordered}
        ordered.extend(
            sorted(
                (ln for ln in band if id(ln) not in placed),
                key=lambda ln: (round(ln.top, 1), ln.x0),
            )
        )
        band.clear()

    for line in sorted(page.lines, key=lambda ln: (round(ln.top, 1), ln.x0)):
        if spans_columns(line, page.columns):
            flush()
            ordered.append(line)
        else:
            band.append(line)
    flush()
    return ordered


# ---------------------------------------------------------------------------
# running heads, folios
# ---------------------------------------------------------------------------


def _edge_lines(page: Page) -> list[Line]:
    top_limit = page.height * EDGE_BAND
    bottom_limit = page.height * (1 - EDGE_BAND)
    return [ln for ln in page.lines if ln.top <= top_limit or ln.bottom >= bottom_limit]


def _normalise(text: str) -> str:
    """Fold the parts of a running head that change from page to page, so
    "Smith et al. / 12" and "Smith et al. / 13" count as the same line."""
    return re.sub(r"\d+", "#", " ".join(text.split())).strip()


def repeated_edge_lines(pages: list[Page]) -> set[str]:
    """Normalised lines that appear in the edge band of at least half the pages."""
    if len(pages) < 2:
        return set()
    counts: dict[str, int] = {}
    for page in pages:
        for key in {_normalise(ln.text) for ln in _edge_lines(page)}:
            if key and len(key) <= MAX_FURNITURE_CHARS:
                counts[key] = counts.get(key, 0) + 1
    threshold = max(2, int(len(pages) * EDGE_REPEAT_SHARE))
    return {key for key, n in counts.items() if n >= threshold}


def is_furniture(line: Line, page: Page, repeated: set[str]) -> bool:
    """A running head, a folio, or a page number - never body text."""
    bare = line.text.strip()
    if not bare:
        return True
    in_edge = line.top <= page.height * EDGE_BAND or line.bottom >= page.height * (1 - EDGE_BAND)
    if in_edge and PAGE_NUMBER.match(bare):
        return True
    return in_edge and _normalise(bare) in repeated


def page_lines_without_furniture(pages: list[Page]) -> list[list[Line]]:
    """Every page in reading order, with running heads and folios removed."""
    repeated = repeated_edge_lines(pages)
    return [
        [ln for ln in reading_order(page) if not is_furniture(ln, page, repeated)]
        for page in pages
    ]
