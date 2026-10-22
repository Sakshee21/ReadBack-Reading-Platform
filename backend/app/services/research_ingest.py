"""Store an extracted research document.

Research documents reuse the existing three tables rather than growing a
parallel set: a **section is a chapter** and a **chunk is a micro-session**.
That is what lets highlights, notes and citations work on a paper with no
changes to any of them - they all anchor to a micro-session already.

What is deliberately different from a book:

* chunks are smaller (~180-320 words), because they are the unit a tag is
  judged against and a highlight anchors to, not a timed reading session;
* no cliffhanger breaks and no imagine-first prompts - a paper has no
  narrative pacing to preserve and nothing to picture;
* only the abstract, body and appendices are chunked. The title block and the
  reference list are stored whole and served for reading, but are not part of
  the flow the reader is taken through.
"""

from app.config import settings
from app.models import Book, Chapter, MicroSession
from app.services.research_extract import READABLE_KINDS, ResearchDocument
from app.services.segmentation import split_into_micro_sessions, word_count


def chunk_section(text: str, min_words: int | None = None, max_words: int | None = None) -> list[dict]:
    """Cut one section into chunks at paragraph boundaries.

    The book packer does this job already, including splitting a paragraph
    that is longer than a whole chunk, so it is reused with the narrative
    features switched off.
    """
    chunks = split_into_micro_sessions(
        text,
        min_words=min_words or settings.research_chunk_min_words,
        max_words=max_words or settings.research_chunk_max_words,
        conservative_cliffhangers=False,
        visualization_prompts=False,
    )
    for chunk in chunks:
        # A paper has no cliffhangers and nothing to picture. Leaving these set
        # would let the reading-habit mechanics fire on research material.
        chunk["is_cliffhanger_break"] = False
        chunk["has_visualization_prompt"] = False
    return chunks


def persist_research_document(db, book: Book, doc: ResearchDocument) -> tuple[int, int, int]:
    """Write sections and chunks. Returns (sections, chunks, readable_words)."""
    chunk_count = 0
    readable_words = 0

    for index, section in enumerate(doc.sections):
        chapter = Chapter(
            book_id=book.id,
            index=index,
            title=(section.title or "")[:500],
            text=section.text,
            word_count=word_count(section.text),
            # No extractive recap: "previously on" belongs to a story, and a
            # machine summary of a paper is the key-points feature, which says
            # plainly that it is generated.
            summary="",
            recap_source="extractive",
            section_kind=section.kind,
            is_cliffhanger_break=False,
        )
        db.add(chapter)
        db.flush()

        if section.kind not in READABLE_KINDS:
            continue  # stored and readable, but not part of the flow

        readable_words += word_count(section.text)
        for chunk in chunk_section(section.text):
            db.add(
                MicroSession(
                    chapter_id=chapter.id,
                    index=chunk["index"],
                    text=chunk["text"],
                    word_count=chunk["word_count"],
                    is_cliffhanger_break=False,
                    has_visualization_prompt=False,
                )
            )
            chunk_count += 1

    return len(doc.sections), chunk_count, readable_words


REQUIRED_FOR_A_CITATION = ("title", "authors", "year")


def needs_review(book: Book, *, unverified: list[str] | None = None, no_date: bool = False) -> list[str]:
    """Fields a citation cannot be written without, that are missing or guessed.

    Blank is the honest answer when a document does not say, but it must not
    pass silently into a citation - so the panel asks for these by name.
    """
    missing = []
    if not (book.title or "").strip():
        missing.append("title")
    if not (book.author or "").strip() or book.author == "Unknown":
        missing.append("authors")
    if book.published_year is None and not no_date:
        missing.append("year")
    for field in unverified or []:
        if field not in missing:
            missing.append(field)
    return missing


def apply_metadata(book: Book, doc: ResearchDocument, *, override: dict | None = None) -> list[str]:
    """Copy extracted metadata onto the book, letting the uploader win.

    An empty extracted field stays empty: the point of the metadata form is
    that the person fills in what the document does not say, not that the
    software invents it. Returns the fields that are still only a guess.
    """
    override = {k: v for k, v in (override or {}).items() if v not in (None, "")}
    meta = doc.metadata

    title = override.get("title") or meta.title
    if title:
        book.title = str(title)[:500]
    authors = override.get("authors") or meta.authors
    book.author = (str(authors)[:255] if authors else "") or "Unknown"

    year = override.get("year") or meta.year
    book.published_year = int(year) if year else None
    venue = override.get("venue") or meta.venue
    book.venue = str(venue)[:300] if venue else None
    doi = override.get("doi") or meta.doi
    book.doi = str(doi)[:200] if doi else None
    book.page_count = doc.page_count or None
    book.doc_kind = doc.doc_kind
    # A field the uploader typed is theirs, not a guess.
    return [field for field in meta.unverified if field not in override]
