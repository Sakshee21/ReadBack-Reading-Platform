"""Turn an uploaded file into plain text.

Everything here is pure (bytes in, text out) so it can be tested without a
database or an HTTP request.

Security posture: the declared file extension is never trusted on its own - the
bytes are sniffed and the two must agree, so a .txt that is really a zip, or an
.epub that is really a PDF, is rejected rather than parsed. Extracted text is
only ever stored and re-served as plain text; nothing is rendered as HTML and
nothing is written to a user-controlled path.
"""

import io
import re
import zipfile

from app.services.frontmatter import should_skip_epub_item
from app.services.normalize import normalize_uploaded_text, tidy_inline_spacing

TXT = "txt"
EPUB = "epub"
PDF = "pdf"
SUPPORTED = (TXT, EPUB, PDF)

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"

# Share of characters that must be ordinary text for us to accept a .txt. Well
# under what real prose scores, but far above a binary read as latin-1.
PRINTABLE_RATIO = 0.85


class ExtractionError(Exception):
    """Raised with a message intended to be shown to the uploader."""

    def __init__(self, message: str, reason_code: str):
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code  # a category, never file contents


def sniff_format(filename: str, data: bytes) -> str:
    """Decide the real format from the bytes and confirm the extension agrees."""
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if ext not in SUPPORTED:
        raise ExtractionError(
            "Only .txt, .epub and .pdf files are supported.", "unsupported_extension"
        )

    if data.startswith(PDF_MAGIC):
        actual = PDF
    elif data.startswith(ZIP_MAGIC):
        actual = EPUB if _is_epub_zip(data) else None
        if actual is None:
            raise ExtractionError("That zip file is not an EPUB.", "not_an_epub")
    else:
        actual = TXT

    if actual != ext:
        raise ExtractionError(
            f"The file is named .{ext} but its contents are {actual.upper()}. "
            "Please upload a file whose extension matches its format.",
            "extension_mismatch",
        )
    return actual


def _is_epub_zip(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return zf.read("mimetype").strip() == b"application/epub+zip"
    except Exception:
        return False


def safe_filename(filename: str) -> str:
    """Strip any path and anything that isn't a plain name character.

    Nothing is written to disk under this name - uploads are parsed in memory -
    but it is shown back to the user and used as a title fallback, so it must
    not carry directory traversal or markup.
    """
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = re.sub(r"[^A-Za-z0-9 ._-]", "", base).strip()
    return cleaned[:120] or "upload"


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractionError("Could not read that file as text.", "undecodable")


def _looks_like_text(text: str) -> bool:
    if not text:
        return False
    sample = text[:20000]
    printable = sum(1 for ch in sample if ch.isprintable() or ch in "\n\r\t")
    return printable / len(sample) >= PRINTABLE_RATIO


def extract_txt(data: bytes) -> str:
    text = _decode(data).replace("\r\n", "\n")
    if not _looks_like_text(text):
        raise ExtractionError(
            "That file doesn't look like readable text.", "garbled_text"
        )
    # Hard-wrapped Gutenberg text becomes real paragraphs here, before anything
    # downstream sees it.
    return normalize_uploaded_text(text, source=TXT)


def extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise ExtractionError("PDF support is unavailable.", "pdf_unavailable") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError(
                "That PDF is password protected.", "pdf_encrypted"
            )
        pages = [(page.extract_text() or "") for page in reader.pages]
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("That PDF could not be read.", "pdf_unreadable") from exc

    # Page-aware: running headers/footers and page numbers are stripped using
    # the page boundaries, which are gone once the text is joined.
    text = normalize_uploaded_text("", source=PDF, pages=pages)
    if len(text.split()) < 50:
        # Almost always a scan: images with no text layer. We deliberately
        # don't OCR, so say what's wrong rather than importing an empty book.
        raise ExtractionError(
            "No text could be extracted - this looks like a scanned PDF. "
            "ReadBack needs a PDF with a real text layer.",
            "pdf_no_text_layer",
        )
    return text.strip()


def extract_epub(data: bytes) -> tuple[str, list[dict]]:
    """Returns (full text, chapters) using the EPUB's own spine order.

    The chapter list may be empty, in which case the caller falls back to the
    heuristic chapter detector used for Gutenberg books.
    """
    try:
        import ebooklib
        from bs4 import BeautifulSoup
        from ebooklib import epub
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise ExtractionError("EPUB support is unavailable.", "epub_unavailable") from exc

    # ebooklib only reads from a path, so stage it in a temp file we name.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.epub"
        path.write_bytes(data)
        try:
            # ignore_ncx silences ebooklib's deprecation warning and matches
            # the behaviour it will default to; we read the spine, not the NCX.
            book = epub.read_epub(str(path), options={"ignore_ncx": True})
        except Exception as exc:
            raise ExtractionError("That EPUB could not be read.", "epub_unreadable") from exc

        chapters: list[dict] = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            href = item.get_name() or ""
            soup = BeautifulSoup(item.get_content(), "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()

            # Skip cover/nav/toc/copyright/colophon spine items outright, using
            # epub:type where the file declares it and the filename otherwise.
            epub_types: set[str] = set()
            for tag in soup.find_all(attrs={"epub:type": True}):
                epub_types.update(str(tag.get("epub:type", "")).lower().split())
            if should_skip_epub_item(href, epub_types):
                continue

            heading = soup.find(["h1", "h2", "h3"])
            title = heading.get_text(" ", strip=True) if heading else ""

            # <p> tags already mark real paragraph boundaries, so take them
            # directly rather than re-wrapping a flattened blob of text.
            blocks = [
                p.get_text(" ", strip=True)
                for p in soup.find_all(["p", "blockquote", "li"])
            ]
            # get_text(" ") separates inline tags with a space, which leaves
            # "capable of that ? Is" - close those gaps back up.
            blocks = [
                tidy_inline_spacing(re.sub(r"\s+", " ", b)).strip()
                for b in blocks
                if b and b.strip()
            ]
            body = "\n\n".join(blocks) if blocks else soup.get_text("\n", strip=True)
            body = re.sub(r"\n{3,}", "\n\n", body)

            if len(body.split()) < 30:
                continue  # stray title page or empty section
            chapters.append({"title": title[:300], "text": body})

    if not chapters:
        raise ExtractionError(
            "No readable chapters were found in that EPUB.", "epub_empty"
        )

    full_text = "\n\n".join(c["text"] for c in chapters)
    return full_text, chapters


def extract(filename: str, data: bytes) -> tuple[str, list[dict], str]:
    """Returns (full_text, chapters_from_source, format).

    chapters_from_source is non-empty only for EPUB, whose own structure we
    trust ahead of the heuristic detector.
    """
    fmt = sniff_format(filename, data)
    if fmt == TXT:
        return extract_txt(data), [], TXT
    if fmt == PDF:
        return extract_pdf(data), [], PDF
    text, chapters = extract_epub(data)
    return text, chapters, EPUB
