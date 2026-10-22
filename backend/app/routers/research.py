"""The research track: papers and textbooks, read by section.

Kept apart from the reading-habit pilot on purpose. A research document:

* lives under /research with its own library, and never appears in /books;
* is always private to the person who uploaded it (there is no shared research
  library, so unlike a seeded book there is no null-owner case);
* emits no reading events, starts no reading sessions and touches no streak -
  ``deps.book_for_user`` refuses research ids, which closes every
  reading-habit endpoint to it, and ``/events`` drops anything that slips
  through;
* is excluded from the pilot CSV exports and has its own.

What it keeps from the reading side: highlights with colours and comments, the
notes page, citation copying, and the appearance themes. Those all anchor to a
micro-session, and a research chunk is a micro-session, so none of them needed
changing.
"""

import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import RESEARCH, get_current_user, research_for_user
from app.models import (
    Book,
    Chapter,
    Highlight,
    MicroSession,
    ReadingEvent,
    ReadingSession,
    ResearchTag,
    ResearchTagging,
    SectionKeyPoints,
    User,
    UserBookProgress,
)
from app.schemas import (
    ConsentIn,
    KeyPointsOut,
    ResearchChunkOut,
    ResearchChunkTagsOut,
    ResearchDocumentDetailOut,
    ResearchDocumentOut,
    ResearchMetadataIn,
    ResearchSectionOut,
    ResearchSectionReadOut,
    ResearchTagStatusOut,
)
from app.services.extract import ExtractionError, safe_filename
from app.services.research_extract import (
    DOC_KINDS,
    READABLE_KINDS,
    extract_research_pdf,
)
from app.services import research_tags
from app.services.research_ingest import (
    apply_metadata,
    needs_review as research_needs_review,
    persist_research_document,
)
from app.services.segmentation import word_count

router = APIRouter(prefix="/research", tags=["research"])


# ---------------------------------------------------------------------------
# shaping
# ---------------------------------------------------------------------------


def _sections_of(document: Book) -> list[Chapter]:
    return sorted(document.chapters, key=lambda c: c.index)


def _section_out(section: Chapter) -> ResearchSectionOut:
    return ResearchSectionOut(
        id=section.id,
        index=section.index,
        title=section.title or "",
        kind=section.section_kind,
        word_count=section.word_count,
        chunk_count=len(section.micro_sessions),
        readable=section.section_kind in READABLE_KINDS,
    )


def _document_out(document: Book, *, tagging_enabled: bool = False) -> ResearchDocumentOut:
    notes = _notes(document)
    return ResearchDocumentOut(
        id=document.id,
        title=document.title,
        authors=document.author or "",
        doc_kind=document.doc_kind if document.doc_kind in DOC_KINDS else None,
        year=document.published_year,
        venue=document.venue,
        doi=document.doi,
        page_count=document.page_count,
        word_count=document.total_word_count,
        section_count=len(document.chapters),
        status=document.status,
        failure_reason=document.failure_reason,
        tagging_consent=bool(document.theme_tagging_consent),
        tagging_enabled=tagging_enabled,
        unverified=notes["unverified"],
        no_date=notes["no_date"],
        needs_review=research_needs_review(
            document, unverified=notes["unverified"], no_date=notes["no_date"]
        ),
    )


def _notes(document: Book) -> dict:
    notes = document.research_notes if isinstance(document.research_notes, dict) else {}
    return {
        "captions": list(notes.get("captions") or []),
        "warnings": list(notes.get("warnings") or []),
        "unverified": list(notes.get("unverified") or []),
        "no_date": bool(notes.get("no_date")),
    }


# ---------------------------------------------------------------------------
# upload and conversion
# ---------------------------------------------------------------------------


async def _read_capped(upload: UploadFile, limit: int) -> bytes:
    """Read the upload, refusing anything over the limit without buffering it all.

    The same shape as the book uploader's helper, with the research cap: a
    journal PDF with embedded figures is heavier than a plain-text novel.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"That file is larger than {limit // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _convert_research(document_id: int, data: bytes, doc_kind: str | None, override: dict) -> None:
    """Background conversion. Never raises - failures land on the row."""
    db = SessionLocal()
    try:
        document = db.get(Book, document_id)
        if document is None:
            return
        try:
            doc = extract_research_pdf(data, doc_kind=doc_kind)
            if doc.page_count > settings.research_max_pages:
                raise ExtractionError(
                    f"That document is {doc.page_count:,} pages, over the "
                    f"{settings.research_max_pages:,} page limit.",
                    "too_many_pages",
                )
            words = doc.readable_words
            if words < settings.research_min_words:
                raise ExtractionError(
                    f"Only {words} words of readable text were found - too little to "
                    "split into sections.",
                    "too_short",
                )
            if words > settings.research_max_words:
                raise ExtractionError(
                    f"That document is {words:,} words, over the "
                    f"{settings.research_max_words:,} word limit.",
                    "too_long",
                )

            document.full_text = "\n\n".join(s.text for s in doc.sections)
            _, chunks, readable_words = persist_research_document(db, document, doc)
            if chunks == 0:
                raise ExtractionError(
                    "No readable sections were found in that document.",
                    "no_readable_sections",
                )
            unverified = apply_metadata(document, doc, override=override)
            document.total_word_count = readable_words
            document.research_notes = {
                "captions": doc.captions,
                "warnings": doc.warnings,
                "unverified": unverified,
                "no_date": False,
            }
            document.status = "ready"
            document.failure_reason = None
            db.commit()
        except ExtractionError as exc:
            db.rollback()
            document = db.get(Book, document_id)
            if document:
                document.status = "failed"
                document.failure_reason = exc.message
                db.commit()
        except Exception:  # noqa: BLE001 - never leave a document stuck "processing"
            db.rollback()
            document = db.get(Book, document_id)
            if document:
                document.status = "failed"
                document.failure_reason = "Conversion failed unexpectedly."
                db.commit()
    finally:
        db.close()


@router.post("/upload", response_model=ResearchDocumentOut, status_code=202)
async def upload_research_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    doc_kind: str | None = Form(None),
    title: str | None = Form(None),
    authors: str | None = Form(None),
    year: int | None = Form(None),
    venue: str | None = Form(None),
    doi: str | None = Form(None),
    tagging_consent: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a paper or textbook PDF. Conversion runs in the background; poll
    ``GET /research/{id}`` for ``status``.

    Metadata passed here wins over whatever the document says about itself, so
    the uploader can correct it up front. Anything left out is read from the
    document, and stays blank when the document does not say.
    """
    if not settings.research_enabled:
        raise HTTPException(status_code=404, detail="The research section is switched off.")

    owned = (
        db.query(Book)
        .filter(
            Book.owner_user_id == user.id,
            Book.source_type == RESEARCH,
            Book.status != "failed",
        )
        .count()
    )
    if owned >= settings.research_docs_per_user:
        raise HTTPException(
            status_code=409,
            detail=f"You can keep up to {settings.research_docs_per_user} research "
            "documents. Delete one to make room.",
        )

    if doc_kind is not None and doc_kind not in DOC_KINDS:
        raise HTTPException(
            status_code=422, detail="doc_kind must be 'paper' or 'textbook'."
        )

    name = safe_filename(file.filename or "document.pdf")
    data = await _read_capped(file, settings.research_max_bytes)
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    # The research path reads page geometry, which only a PDF has. Checked on
    # the bytes, so a renamed .docx is refused here rather than parsed.
    if not data.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="The research section takes PDF files only. "
            "Upload EPUB or text files as books instead.",
        )

    fallback = name.rsplit(".", 1)[0].replace("_", " ").strip() or "Untitled document"
    document = Book(
        gutenberg_id=None,
        title=(title or fallback)[:500],
        author=(authors or "")[:255] or "Unknown",
        full_text="",
        total_word_count=0,
        owner_user_id=user.id,
        is_user_uploaded=True,
        source_type=RESEARCH,
        status="processing",
        doc_kind=doc_kind,
        published_year=year,
        venue=venue,
        doi=doi,
        theme_tagging_consent=tagging_consent,
        theme_tagging_consent_at=dt.datetime.utcnow() if tagging_consent else None,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    override = {
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue,
        "doi": doi,
    }
    background.add_task(_convert_research, document.id, data, doc_kind, override)
    return _document_out(document)


# ---------------------------------------------------------------------------
# library and document
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ResearchDocumentOut])
def list_research_documents(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """This user's research documents - never anyone else's."""
    documents = (
        db.query(Book)
        .filter(Book.owner_user_id == user.id, Book.source_type == RESEARCH)
        .order_by(Book.id.desc())
        .all()
    )
    return [
        _document_out(d, tagging_enabled=research_tags.tagging_enabled(d)) for d in documents
    ]


@router.get("/{document_id}", response_model=ResearchDocumentDetailOut)
def get_research_document(
    document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    document = research_for_user(db, document_id, user)
    notes = _notes(document)
    base = _document_out(document, tagging_enabled=research_tags.tagging_enabled(document))
    return ResearchDocumentDetailOut(
        **base.model_dump(),
        sections=[_section_out(s) for s in _sections_of(document)],
        captions=notes["captions"],
        warnings=notes["warnings"],
    )


@router.patch("/{document_id}", response_model=ResearchDocumentOut)
def update_research_metadata(
    document_id: int,
    payload: ResearchMetadataIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Correct the citation metadata by hand.

    Only the fields present in the request are touched, so clearing one field
    does not wipe the rest. Nothing here is derived or guessed.
    """
    document = research_for_user(db, document_id, user)
    sent = payload.model_dump(exclude_unset=True)
    if "title" in sent and sent["title"]:
        document.title = sent["title"][:500]
    if "authors" in sent:
        document.author = (sent["authors"] or "")[:255] or "Unknown"
    if "year" in sent:
        document.published_year = sent["year"]
    if "venue" in sent:
        document.venue = sent["venue"]
    if "doi" in sent:
        document.doi = sent["doi"]

    # A field the owner has looked at is no longer a guess, and saying the
    # document has no date is the one thing that makes a missing year citable.
    notes = _notes(document)
    notes["unverified"] = [f for f in notes["unverified"] if f not in sent]
    if "no_date" in sent and sent["no_date"] is not None:
        notes["no_date"] = bool(sent["no_date"])
    document.research_notes = notes

    db.commit()
    db.refresh(document)
    return _document_out(document)


@router.get("/{document_id}/sections/{section_id}", response_model=ResearchSectionReadOut)
def read_research_section(
    document_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One whole section: the unit the research reader shows.

    There is no saved position, no autoplay and no next-up countdown. Moving
    between sections is the reader's choice, so the response just names the
    neighbours.
    """
    document = research_for_user(db, document_id, user)
    sections = _sections_of(document)
    section = next((s for s in sections if s.id == section_id), None)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")

    readable = [s for s in sections if s.section_kind in READABLE_KINDS]
    position = next((i for i, s in enumerate(readable) if s.id == section.id), None)
    previous_id = readable[position - 1].id if position not in (None, 0) else None
    next_id = (
        readable[position + 1].id
        if position is not None and position + 1 < len(readable)
        else None
    )

    chunks = sorted(section.micro_sessions, key=lambda m: m.index)
    if not chunks:
        # A non-flow section (the title block, the reference list) is stored
        # whole, so serve its text as a single chunk rather than nothing.
        chunk_out = [
            ResearchChunkOut(
                id=0, index=0, text=section.text, word_count=section.word_count
            )
        ]
    else:
        chunk_out = [
            ResearchChunkOut(
                id=c.id, index=c.index, text=c.text, word_count=c.word_count
            )
            for c in chunks
        ]

    return ResearchSectionReadOut(
        document_id=document.id,
        section=_section_out(section),
        chunks=chunk_out,
        previous_section_id=previous_id,
        next_section_id=next_id,
        tags=research_tags.tags_for_chunks(db, document, [c.id for c in chunks]),
        key_points=research_tags.key_points_for(db, section),
    )


@router.delete("/{document_id}", status_code=204)
def delete_research_document(
    document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Delete a research document and everything hanging off it."""
    document = research_for_user(db, document_id, user)

    chapter_ids = [c.id for c in document.chapters]
    chunk_ids = [ms.id for c in document.chapters for ms in c.micro_sessions]

    if chunk_ids:
        db.query(ResearchTag).filter(ResearchTag.micro_session_id.in_(chunk_ids)).delete(
            synchronize_session=False
        )
        db.query(ResearchTagging).filter(
            ResearchTagging.micro_session_id.in_(chunk_ids)
        ).delete(synchronize_session=False)
        db.query(Highlight).filter(Highlight.micro_session_id.in_(chunk_ids)).delete(
            synchronize_session=False
        )
    if chapter_ids:
        db.query(SectionKeyPoints).filter(
            SectionKeyPoints.chapter_id.in_(chapter_ids)
        ).delete(synchronize_session=False)
    db.query(Highlight).filter(Highlight.book_id == document.id).delete(
        synchronize_session=False
    )
    # Research documents should have none of these, but a stray row would block
    # the delete on its foreign key.
    db.query(ReadingEvent).filter(ReadingEvent.book_id == document.id).delete(
        synchronize_session=False
    )
    db.query(ReadingSession).filter(ReadingSession.book_id == document.id).delete(
        synchronize_session=False
    )
    db.query(UserBookProgress).filter(UserBookProgress.book_id == document.id).delete(
        synchronize_session=False
    )

    db.delete(document)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# the research track's own export
# ---------------------------------------------------------------------------


@router.get("/export/sections.csv")
def export_research_sections_csv(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """One row per section of this user's own research documents.

    Separate from the pilot exports by design: research documents are not study
    data, so they are not in events.csv or themes.csv, and this is per-user and
    authenticated rather than guarded by the admin token.
    """
    import csv
    import io

    from fastapi.responses import Response

    columns = [
        "document_id", "doc_kind", "title", "authors", "year", "venue", "doi",
        "pages", "section_index", "section_title", "section_kind", "section_words",
        "chunks", "tags", "highlights",
    ]
    documents = (
        db.query(Book)
        .filter(
            Book.owner_user_id == user.id,
            Book.source_type == RESEARCH,
            Book.status == "ready",
        )
        .order_by(Book.id)
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for document in documents:
        for section in _sections_of(document):
            chunk_ids = [ms.id for ms in section.micro_sessions]
            tags: list[str] = []
            highlights = 0
            if chunk_ids:
                rows = (
                    db.query(ResearchTag.tag, ResearchTag.score)
                    .filter(
                        ResearchTag.micro_session_id.in_(chunk_ids),
                        ResearchTag.score >= research_tags.MIN_SHOWN_SCORE,
                    )
                    .all()
                )
                tags = sorted({tag for tag, _ in rows})
                highlights = (
                    db.query(Highlight)
                    .filter(
                        Highlight.user_id == user.id,
                        Highlight.micro_session_id.in_(chunk_ids),
                    )
                    .count()
                )
            writer.writerow(
                [
                    document.id,
                    document.doc_kind or "",
                    document.title,
                    document.author or "",
                    document.published_year or "",
                    document.venue or "",
                    document.doi or "",
                    document.page_count or "",
                    section.index,
                    section.title or "",
                    section.section_kind,
                    word_count(section.text),
                    len(chunk_ids),
                    " ".join(tags),
                    highlights,
                ]
            )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=research_sections.csv"},
    )


# ---------------------------------------------------------------------------
# research tagging and key points
#
# Every model call happens in a background task. The reader never waits: it
# asks for the status, sees queued/running/done/failed, and the tags appear on
# the next load. Nothing runs without consent, which is re-checked around each
# call and whose withdrawal deletes what was written.
# ---------------------------------------------------------------------------


@router.put("/{document_id}/consent", response_model=ResearchTagStatusOut)
def set_tagging_consent(
    document_id: int,
    payload: ConsentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Give or withdraw consent for this document to be sent to an AI service.

    Withdrawing deletes every tag and key-point row for the document, not just
    future ones. Consent that can be withdrawn without erasing what it
    produced is not really consent.
    """
    document = research_for_user(db, document_id, user)
    document.theme_tagging_consent = bool(payload.consent)
    document.theme_tagging_consent_at = dt.datetime.utcnow() if payload.consent else None
    db.commit()

    if not payload.consent:
        research_tags.purge(db, document)
    db.refresh(document)
    return research_tags.queue_status(db, document)


@router.get("/{document_id}/tags/status", response_model=ResearchTagStatusOut)
def tagging_status(
    document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    document = research_for_user(db, document_id, user)
    return research_tags.queue_status(db, document)


@router.post("/{document_id}/tags/queue", response_model=ResearchTagStatusOut, status_code=202)
def queue_tagging(
    document_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Queue the untagged chunks of this document and start working through them.

    Safe to call again at any point: the queue is in the database, finished
    chunks are skipped, and a chunk that failed recently waits out its cooldown
    rather than burning the rate limit.
    """
    document = research_for_user(db, document_id, user)
    status = research_tags.queue_status(db, document)
    if not status.enabled:
        return status

    plan = research_tags.plan_queue(db, document)
    if plan:
        research_tags.mark_queued(db, plan)
        background.add_task(research_tags.run_queue, document.id)
    return research_tags.queue_status(db, document)


@router.get("/{document_id}/tags", response_model=list[ResearchChunkTagsOut])
def list_document_tags(
    document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Every shown tag in the document, for the tag overview."""
    document = research_for_user(db, document_id, user)
    return research_tags.tags_for_chunks(db, document, research_tags.chunk_ids_of(document))


@router.post(
    "/{document_id}/sections/{section_id}/key-points",
    response_model=KeyPointsOut,
    status_code=202,
)
def request_key_points(
    document_id: int,
    section_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ask for machine-generated key points for one section.

    Always labelled as generated where it is shown. If the call fails the panel
    stays empty - a wrong summary of a paper someone is about to cite is worse
    than no summary.
    """
    document = research_for_user(db, document_id, user)
    if not settings.research_key_points_on_demand:
        raise HTTPException(
            status_code=409, detail="Key points are switched off on this server."
        )
    if not research_tags.tagging_enabled(document):
        raise HTTPException(
            status_code=409,
            detail="Key points need your consent for this document to be sent to an AI service.",
        )
    section = next((s for s in _sections_of(document) if s.id == section_id), None)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    if section.section_kind not in READABLE_KINDS:
        raise HTTPException(
            status_code=409, detail="Key points are only generated for readable sections."
        )

    background.add_task(research_tags.generate_key_points, section.id)
    existing = research_tags.key_points_for(db, section)
    return existing or KeyPointsOut(status="queued")
