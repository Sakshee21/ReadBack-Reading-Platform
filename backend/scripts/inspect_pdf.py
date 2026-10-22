"""Show what the extraction pipeline makes of a PDF, before anything is stored.

A diagnostic, not part of the app. Run it on a paper or a textbook to see what
the reader would actually get:

    python -m scripts.inspect_pdf path/to/paper.pdf
    python -m scripts.inspect_pdf tests/fixtures/research/*.pdf --chars 1200
    python -m scripts.inspect_pdf paper.pdf --path book     # the book pipeline

By default it reports the research path (layout-aware) when that is available
and the book path otherwise. ``--path both`` runs the two side by side, which is
the honest way to see whether layout handling is earning its keep on a given
document.

Nothing is written to the database and no network call is made.
"""

import argparse
import io
import re
import sys
from pathlib import Path

from app.services.extract import ExtractionError, extract_pdf
from app.services.frontmatter import classify_sections
from app.services.segmentation import split_into_chapters, word_count

try:
    from app.services import pdf_layout
except ImportError:  # pragma: no cover - only without pdfminer
    pdf_layout = None

try:  # the research path is optional; the book path must always work
    from app.services import research_extract
except ImportError:  # pragma: no cover - only while the module is absent
    research_extract = None


REFERENCE_HEADING = re.compile(
    r"^\s*(?:[IVXLC]+\.?\s*)?(references|bibliography|works cited|literature cited)\s*$",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"[.!?:;][\"')\]]*$")


def rule(title: str, char: str = "=") -> None:
    print()
    print(f"{char * 3} {title} {char * max(3, 72 - len(title))}")


def pdf_basics(data: bytes) -> dict:
    """Page count and embedded metadata, read with pypdf (already a dependency)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    info = reader.metadata or {}
    outline: list[str] = []
    try:
        for entry in reader.outline or []:
            if isinstance(entry, list):  # nested children
                continue
            label = getattr(entry, "title", None)
            if label:
                outline.append(str(label))
    except Exception as exc:  # noqa: BLE001 - a broken outline is a finding, not a crash
        outline = [f"<outline unreadable: {type(exc).__name__}>"]
    return {
        "pages": len(reader.pages),
        "encrypted": reader.is_encrypted,
        "meta_title": (info.get("/Title") or "").strip() if info else "",
        "meta_author": (info.get("/Author") or "").strip() if info else "",
        "outline": outline,
    }


def mid_sentence_break_ratio(text: str) -> float:
    """Share of line transitions that look stitched rather than continuous.

    Two columns read across give lines whose predecessor stops mid-sentence and
    whose successor opens with a capital - a shape ordinary prose rarely has.
    A high number here is the fingerprint of interleaved columns.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < 4:
        return 0.0
    suspicious = sum(
        1
        for a, b in zip(lines, lines[1:])
        if not SENTENCE_END.search(a) and re.match(r"^[A-Z0-9]", b)
    )
    return suspicious / (len(lines) - 1)


def find_reference_heading(text: str) -> tuple[int, str] | None:
    for i, line in enumerate(text.split("\n")):
        if REFERENCE_HEADING.match(line):
            return i, line.strip()
    return None


def report_sections(text: str) -> list[dict]:
    """What the book pipeline would make of the text: chapters, then labelled."""
    chapters = split_into_chapters(text)
    return classify_sections(chapters)


def show_text_sample(text: str, chars: int, label: str) -> None:
    rule(f"{label}: first {chars} characters", "-")
    sample = text[:chars]
    for line in sample.split("\n"):
        print(f"  | {line}")
    if len(text) > chars:
        print(f"  | ... ({word_count(text):,} words in total)")


def raw_pypdf_lines(data: bytes) -> str:
    """What pypdf hands over, before any paragraph joining.

    The stitched-line measurement has to be taken here. Once the normaliser has
    folded a page into one paragraph the line boundaries are gone, and any
    measurement of them reads a reassuring zero whatever the input was.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def inspect_book_path(data: bytes, chars: int) -> dict:
    """The pipeline uploaded novels go through today."""
    try:
        text = extract_pdf(data)
    except ExtractionError as exc:
        print(f"  REJECTED by the book pipeline: {exc.message} ({exc.reason_code})")
        return {"text": "", "raw": "", "rejected": exc.reason_code}
    show_text_sample(text, chars, "book path")

    sections = report_sections(text)
    rule("book path: sections it would store", "-")
    for i, section in enumerate(sections):
        title = (section.get("title") or "(untitled)")[:58]
        print(
            f"  {i:>3}  {section.get('section_kind', 'story'):<12} "
            f"{word_count(section['text']):>7,d}w  {title}"
        )
    return {
        "text": text,
        "raw": raw_pypdf_lines(data),
        "sections": sections,
        "rejected": None,
    }


def inspect_research_path(data: bytes, chars: int) -> dict:
    if research_extract is None:
        print("  (the research path is not installed in this checkout)")
        return {}
    try:
        doc = research_extract.extract_research_pdf(data)
    except ExtractionError as exc:
        print(f"  REJECTED by the research pipeline: {exc.message} ({exc.reason_code})")
        return {"rejected": exc.reason_code}

    rule("research path: metadata it found", "-")
    for field in ("title", "authors", "year", "venue", "doi"):
        value = getattr(doc.metadata, field, None)
        print(f"  {field:<8} {value if value not in (None, '', []) else '-- not found --'}")

    rule("research path: sections", "-")
    for i, section in enumerate(doc.sections):
        print(
            f"  {i:>3}  {section.kind:<12} {word_count(section.text):>7,d}w  "
            f"{(section.title or '(untitled)')[:52]}"
        )
    if doc.captions:
        rule("research path: captions kept aside", "-")
        for caption in doc.captions[:6]:
            print(f"  - {caption[:100]}")
    if doc.warnings:
        rule("research path: warnings", "-")
        for warning in doc.warnings:
            print(f"  ! {warning}")

    body = "\n\n".join(s.text for s in doc.sections if s.kind == "body")
    show_text_sample(body, chars, "research path")
    return {"doc": doc, "text": body}


def geometry_probe(data: bytes) -> None:
    """Pure measurement: how many columns, and what repeats at the page edges."""
    if pdf_layout is None:
        print("  (geometry probe needs app.services.pdf_layout)")
        return
    try:
        pages = pdf_layout.read_pages(data)
    except Exception as exc:  # noqa: BLE001 - diagnostics must not crash
        print(f"  geometry unavailable: {type(exc).__name__}: {exc}")
        return
    for page in pages[:4]:
        kind = "single" if page.column_count < 2 else f"{page.column_count} columns"
        bounds = ", ".join(f"x={c.x0:.0f}-{c.x1:.0f}" for c in page.columns)
        spanning = sum(1 for ln in page.lines if pdf_layout.spans_columns(ln, page.columns))
        extra = f"  ({spanning} full-width lines)" if spanning else ""
        print(f"  page {page.number:>2}  {kind:<12} {len(page.lines):>3} lines  {bounds}{extra}")
    furniture = pdf_layout.repeated_edge_lines(pages)
    if furniture:
        print("  repeated at the page edges (header/footer candidates):")
        for line in sorted(furniture)[:6]:
            print(f"    - {line[:90]}")
    else:
        print("  no repeated header or footer found")


def inspect(path: Path, chars: int, which: str) -> None:
    print()
    print("#" * 78)
    print(f"# {path}")
    print("#" * 78)
    data = path.read_bytes()
    print(f"  {len(data):,} bytes on disk")

    basics = pdf_basics(data)
    rule("what the PDF says about itself")
    print(f"  pages          {basics['pages']}")
    print(f"  encrypted      {basics['encrypted']}")
    print(f"  /Title         {basics['meta_title'] or '-- empty --'}")
    print(f"  /Author        {basics['meta_author'] or '-- empty --'}")
    if basics["outline"]:
        print(f"  outline        {len(basics['outline'])} bookmarks")
        for label in basics["outline"][:8]:
            print(f"                 - {label}")
    else:
        print("  outline        -- none --")

    rule("geometry probe (measurement only)")
    geometry_probe(data)

    results = {}
    if which in ("book", "both"):
        rule("BOOK PATH (what uploads use today)")
        results["book"] = inspect_book_path(data, chars)
    if which in ("research", "both"):
        rule("RESEARCH PATH")
        results["research"] = inspect_research_path(data, chars)

    rule("findings")
    for name, result in results.items():
        text = result.get("text") or ""
        if not text:
            print(f"  {name:<9} no text (see the rejection above)")
            continue
        ratio = mid_sentence_break_ratio(result.get("raw") or "")
        verdict = (
            "looks stitched - unrelated lines are being joined"
            if ratio > 0.15
            else "line flow looks continuous"
        )
        print(f"  {name:<9} {word_count(text):>7,d} words")
        print(f"  {'':<9} mid-sentence line breaks {ratio:.0%} - {verdict}")
        doc = result.get("doc")
        if doc is not None:
            refs = [s for s in doc.sections if s.kind == "references"]
            if refs:
                words = sum(word_count(s.text) for s in refs)
                print(f"  {'':<9} {words:,} words of references held out of the reading flow")
            else:
                print(f"  {'':<9} no reference list was found")
            continue
        found = find_reference_heading(text)
        if found:
            print(
                f"  {'':<9} references are inside the reading text, from line "
                f"{found[0]} ({found[1]!r})"
            )
        else:
            print(f"  {'':<9} no reference heading found in the text")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--chars", type=int, default=900, help="characters of sample text")
    parser.add_argument(
        "--path",
        choices=("book", "research", "both"),
        default="auto",
        help="which extraction path to run (default: research if available, else book)",
    )
    args = parser.parse_args(argv)

    which = args.path
    if which == "auto":
        which = "research" if research_extract is not None else "book"

    missing = [p for p in args.paths if not p.is_file()]
    if missing:
        for path in missing:
            print(f"not a file: {path}", file=sys.stderr)
        return 2

    for path in args.paths:
        inspect(path, args.chars, which)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
