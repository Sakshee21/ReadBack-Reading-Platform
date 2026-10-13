"""Generate the tiny upload fixtures committed under tests/fixtures/uploads/.

Run once; the outputs are committed so the test suite needs no network and no
extra tooling:

    python tests/fixtures/make_upload_fixtures.py

All text is public domain (Jane Austen, *Pride and Prejudice*, 1813).
"""

import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent / "uploads"

OPENING = (
    "It is a truth universally acknowledged, that a single man in possession "
    "of a good fortune, must be in want of a wife. However little known the "
    "feelings or views of such a man may be on his first entering a "
    "neighbourhood, this truth is so well fixed in the minds of the "
    "surrounding families, that he is considered as the rightful property of "
    "some one or other of their daughters."
)
REPLY = (
    "My dear Mr. Bennet, said his lady to him one day, have you heard that "
    "Netherfield Park is let at last? Mr. Bennet replied that he had not. But "
    "it is, returned she; for Mrs. Long has just been here, and she told me "
    "all about it. Mr. Bennet made no answer. Do not you want to know who has "
    "taken it? cried his wife impatiently."
)


def paragraphs(seed: str, count: int) -> str:
    return "\n\n".join(f"{seed} ({i + 1})" for i in range(count))


def write_txt() -> Path:
    body = "\n\n".join(
        [
            "CHAPTER I",
            paragraphs(OPENING, 4),
            "CHAPTER II",
            paragraphs(REPLY, 4),
            "CHAPTER III",
            paragraphs(OPENING, 4),
        ]
    )
    path = OUT / "sample.txt"
    path.write_text(body, encoding="utf-8")
    return path


def write_epub() -> Path:
    """A minimal but valid EPUB 2, written by hand so the fixture doesn't depend
    on ebooklib's writer."""
    path = OUT / "sample.epub"

    def chapter_html(title: str, body: str) -> str:
        paras = "".join(f"<p>{p}</p>" for p in body.split("\n\n"))
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
            f"<head><title>{title}</title></head>"
            f"<body><h1>{title}</h1>{paras}</body></html>"
        )

    chapters = {
        "chap1.xhtml": ("The Bennets", paragraphs(OPENING, 4)),
        "chap2.xhtml": ("Netherfield Park", paragraphs(REPLY, 4)),
        "chap3.xhtml": ("An Invitation", paragraphs(OPENING, 4)),
    }

    manifest = "".join(
        f'<item id="{name.split(".")[0]}" href="{name}" media-type="application/xhtml+xml"/>'
        for name in chapters
    )
    spine = "".join(f'<itemref idref="{name.split(".")[0]}"/>' for name in chapters)
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Sample Upload Book</dc:title>"
        "<dc:creator>Jane Austen</dc:creator>"
        '<dc:identifier id="bookid">readback-fixture-1</dc:identifier>'
        "<dc:language>en</dc:language>"
        "</metadata>"
        f'<manifest>{manifest}<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>'
        f'<spine toc="ncx">{spine}</spine>'
        "</package>"
    )
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        '<head><meta name="dtb:uid" content="readback-fixture-1"/></head>'
        "<docTitle><text>Sample Upload Book</text></docTitle><navMap>"
        + "".join(
            f'<navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>{title}</text></navLabel>'
            f'<content src="{name}"/></navPoint>'
            for i, (name, (title, _)) in enumerate(chapters.items())
        )
        + "</navMap></ncx>"
    )
    container = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )

    with zipfile.ZipFile(path, "w") as zf:
        # The mimetype entry must be first and stored uncompressed.
        zf.writestr(
            zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED
        )
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/toc.ncx", ncx)
        for name, (title, body) in chapters.items():
            zf.writestr(f"OEBPS/{name}", chapter_html(title, body))
    return path


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def write_pdf(name: str = "sample.pdf", with_text: bool = True) -> Path:
    """A minimal PDF with an uncompressed text layer, so pypdf can extract it.

    with_text=False produces a page with no text operators at all, standing in
    for a scanned document.
    """
    path = OUT / name

    if with_text:
        lines = []
        for i in range(14):
            source = OPENING if i % 2 == 0 else REPLY
            lines.append(source[:78] + f" line {i + 1}")
        shown = "\n".join(f"({_pdf_escape(line)}) Tj 0 -16 Td" for line in lines)
        content = f"BT /F1 11 Tf 40 760 Td\n{shown}\nET"
    else:
        content = "0.5 0.5 0.5 rg 40 40 500 700 re f"  # a grey box: no text layer

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode("latin-1")

    path.write_bytes(bytes(out))
    return path


def _hard_wrap(text: str, width: int = 70, indent: str = "") -> str:
    """Wrap like Project Gutenberg does: break at ~70 chars mid-sentence."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(indent + current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(indent + current)
    return "\n".join(lines)


def write_gutenberg_txt() -> Path:
    """Hard-wrapped text with licence header/footer, contents and a preface -
    the shape that produced the orphan-word bug."""
    body = "\n\n".join(
        [
            "The Project Gutenberg eBook of A Sample Novel",
            "Produced by Some Volunteer and the Online Distributed Proofreading Team.",
            "*** START OF THE PROJECT GUTENBERG EBOOK A SAMPLE NOVEL ***",
            "CONTENTS",
            "\n".join(["CHAPTER I.  The Garret", "CHAPTER II.  The Bridge", "CHAPTER III.  The Stairs",
                       "CHAPTER IV.  The Room", "CHAPTER V.  The Street", "CHAPTER VI.  The Return"]),
            "PREFACE",
            # Long enough to survive the chapter detector's lead-in rule, so it
            # reaches the front-matter classifier rather than being dropped.
            _hard_wrap(
                "This edition reproduces the text of the first printing. The editor "
                "has silently corrected obvious typographical errors and has "
                "standardised the use of quotation marks throughout the volume. "
                "The translator wishes to record his thanks to the many "
                "correspondents who pointed out errors in the earlier issue, and "
                "to the librarians who made the original sheets available for "
                "collation. A full account of the textual variants will be found "
                "in the appendix, together with a note on the orthography of the "
                "period and a short bibliography of the principal authorities "
                "consulted during the preparation of this volume."
            ),
            "CHAPTER I",
            # the exact failure from the bug report: a sentence broken across lines
            "He had successfully avoided meeting his landlady on the staircase. His\n"
            "garret was under the roof of a high, five-storied house and was more like\n"
            "a cupboard than a room.",
            _hard_wrap(
                "The landlady who provided him with garret, dinners, and attendance, "
                "lived on the floor below, and every time he went out he was obliged "
                "to pass her kitchen, the door of which invariably stood open. And "
                "each time he passed, the young man had a sick, frightened feeling, "
                "which made him scowl and feel ashamed."
            ),
            _hard_wrap(OPENING + " " + REPLY),
            "CHAPTER II",
            _hard_wrap(REPLY + " " + OPENING),
            _hard_wrap(OPENING + " " + REPLY),
            "*** END OF THE PROJECT GUTENBERG EBOOK A SAMPLE NOVEL ***",
            "This eBook is for the use of anyone anywhere at no cost and with almost "
            "no restrictions whatsoever. START: FULL LICENSE",
        ]
    )
    path = OUT / "gutenberg_style.txt"
    path.write_text(body, encoding="utf-8")
    return path


def write_verse_txt() -> Path:
    """Short consistent lines that must NOT be joined into a paragraph."""
    poem = "\n".join(
        [
            "Tyger Tyger, burning bright,",
            "In the forests of the night;",
            "What immortal hand or eye,",
            "Could frame thy fearful symmetry?",
        ]
    )
    listing = "\n".join(
        ["1. The first item here", "2. The second item here", "3. The third item here",
         "4. The fourth item here"]
    )
    body = "\n\n".join(
        ["CHAPTER I", _hard_wrap(OPENING), poem, listing, _hard_wrap(REPLY), _hard_wrap(OPENING)]
    )
    path = OUT / "verse.txt"
    path.write_text(body, encoding="utf-8")
    return path


def write_no_headings_txt() -> Path:
    """A long book with no chapter headings at all."""
    body = "\n\n".join(_hard_wrap(OPENING + " " + REPLY) for _ in range(40))
    path = OUT / "no_headings.txt"
    path.write_text(body, encoding="utf-8")
    return path


def write_headered_pdf() -> Path:
    """Pages carrying a repeated running header and page numbers."""
    path = OUT / "headers.pdf"
    pages = []
    for page_no in range(1, 6):
        lines = ["A SAMPLE NOVEL"]  # running header, same on every page
        for i in range(10):
            source = OPENING if i % 2 == 0 else REPLY
            lines.append(source[:70] + f" p{page_no}l{i}")
        lines.append(str(page_no))  # page number footer
        pages.append(lines)

    objects_pages = []
    for lines in pages:
        shown = "\n".join(f"({_pdf_escape(line)}) Tj 0 -16 Td" for line in lines)
        objects_pages.append(f"BT /F1 11 Tf 40 780 Td\n{shown}\nET")

    # object layout: 1 catalog, 2 pages, then per page: page obj + content obj
    page_obj_ids = [3 + 2 * i for i in range(len(pages))]
    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    font_id = 3 + 2 * len(pages)

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>",
    ]
    for i, content in enumerate(objects_pages):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {4 + 2 * i} 0 R >>"
        )
        objects.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode("latin-1")
    path.write_bytes(bytes(out))
    return path


def write_frontmatter_epub() -> Path:
    """An EPUB with cover, nav/toc and colophon spine items to be skipped."""
    path = OUT / "frontmatter.epub"

    def html(title: str, body_html: str, epub_type: str = "") -> str:
        attr = f' epub:type="{epub_type}"' if epub_type else ""
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops">'
            f"<head><title>{title}</title></head>"
            f"<body{attr}><h1>{title}</h1>{body_html}</body></html>"
        )

    def paras(text: str, n: int) -> str:
        return "".join(f"<p>{text} ({i + 1})</p>" for i in range(n))

    docs = {
        "cover.xhtml": html("Cover", "<p>Sample Novel</p>", "cover"),
        "toc.xhtml": html("Contents", "<p>Chapter I</p><p>Chapter II</p>", "toc"),
        "colophon.xhtml": html("Colophon", paras("Typography notes", 4), "colophon"),
        "chapter-1.xhtml": html("Chapter I", paras(OPENING, 4)),
        "chapter-2.xhtml": html("Chapter II", paras(REPLY, 4)),
    }

    manifest = "".join(
        f'<item id="{n.split(".")[0]}" href="{n}" media-type="application/xhtml+xml"/>'
        for n in docs
    )
    spine = "".join(f'<itemref idref="{n.split(".")[0]}"/>' for n in docs)
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Sample Novel With Front Matter</dc:title>"
        "<dc:creator>Jane Austen</dc:creator>"
        '<dc:identifier id="bookid">readback-fixture-2</dc:identifier>'
        "<dc:language>en</dc:language></metadata>"
        f"<manifest>{manifest}</manifest><spine>{spine}</spine></package>"
    )
    container = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED
        )
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        for name, content in docs.items():
            zf.writestr(f"OEBPS/{name}", content)
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    made = [
        write_txt(),
        write_epub(),
        write_pdf(),
        write_pdf("scanned.pdf", with_text=False),
        write_gutenberg_txt(),
        write_verse_txt(),
        write_no_headings_txt(),
        write_headered_pdf(),
        write_frontmatter_epub(),
    ]
    for path in made:
        print(f"  {path.name:16s} {path.stat().st_size:>7,d} bytes")
    print(f"Wrote {len(made)} fixtures to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
