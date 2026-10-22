from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import annotatable_for_user, get_current_user, is_research
from app.models import Book, Chapter, Highlight, MicroSession, MicroSessionTheme, User
from app.schemas import HighlightIn, HighlightOut, HighlightPatch
from app.services.research_extract import READABLE_KINDS
from app.services.themes import MIN_SHOWN_SCORE, THEMES, reached_micro_session_ids

router = APIRouter(tags=["highlights"])

CONTEXT_CHARS = 40


def _session_numbers(db: Session, book: Book) -> dict[int, int]:
    """micro-session id -> "Session N", numbered as the Sessions drawer does
    (story chapters only, in reading order). One query, not a walk of the
    whole book.

    A research document has no story chapters, so its chunks are numbered
    across the sections that are actually read instead - otherwise every note
    on a paper would come back unnumbered.
    """
    kinds = list(READABLE_KINDS) if is_research(book) else ["story"]
    rows = (
        db.query(MicroSession.id)
        .join(Chapter, MicroSession.chapter_id == Chapter.id)
        .filter(Chapter.book_id == book.id, Chapter.section_kind.in_(kinds))
        .order_by(Chapter.index, MicroSession.index)
        .all()
    )
    return {row[0]: n for n, row in enumerate(rows, start=1)}


def _research_tags_for(db: Session, book: Book, micro_session_ids: set[int]) -> dict[int, list[dict]]:
    """The same shape as _themes_for, from the research tag list.

    A research document carries rhetorical tags, not literary themes, so a note
    taken on a paper is labelled "Method" rather than nothing at all. There is
    no spoiler rule: a paper has no plot to give away.
    """
    from app.models import ResearchTag
    from app.services.research_tags import (
        MIN_SHOWN_SCORE as TAG_MIN_SCORE,
        RESEARCH_TAGS,
    )

    if not micro_session_ids:
        return {}
    rows = (
        db.query(ResearchTag)
        .filter(
            ResearchTag.micro_session_id.in_(micro_session_ids),
            ResearchTag.score >= TAG_MIN_SCORE,
            ResearchTag.tag.in_(list(RESEARCH_TAGS)),
        )
        .all()
    )
    order = list(RESEARCH_TAGS)
    rows.sort(key=lambda r: (-r.score, order.index(r.tag)))
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r.micro_session_id, []).append(
            {"theme": r.tag, "label": RESEARCH_TAGS[r.tag]}
        )
    return out


def _themes_for(db: Session, user: User, book: Book, micro_session_ids: set[int]) -> dict[int, list[dict]]:
    """micro-session id -> its themes worth showing, best first. Only passages the
    reader has reached: a tag on a later one could give the plot away."""
    if is_research(book):
        return _research_tags_for(db, book, micro_session_ids)
    micro_session_ids = micro_session_ids & reached_micro_session_ids(db, user, book)
    if not micro_session_ids:
        return {}
    rows = (
        db.query(MicroSessionTheme)
        .filter(
            MicroSessionTheme.micro_session_id.in_(micro_session_ids),
            MicroSessionTheme.score >= MIN_SHOWN_SCORE,
            MicroSessionTheme.theme.in_(list(THEMES)),
        )
        .all()
    )
    order = list(THEMES)
    rows.sort(key=lambda r: (-r.score, order.index(r.theme)))
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r.micro_session_id, []).append({"theme": r.theme, "label": THEMES[r.theme]})
    return out


def _out(
    h: Highlight, chapter: Chapter, ms: MicroSession, numbers: dict[int, int], themes: list[dict] | None = None
) -> HighlightOut:
    return HighlightOut(
        id=h.id,
        book_id=h.book_id,
        micro_session_id=h.micro_session_id,
        chapter_index=chapter.index,
        chapter_title=chapter.title,
        session_index=ms.index,
        session_number=numbers.get(ms.id),
        start=h.start,
        end=h.end,
        quote=h.quote,
        context_before=h.context_before,
        context_after=h.context_after,
        color=h.color,
        comment=h.comment,
        themes=themes or [],
        created_at=h.created_at,
        updated_at=h.updated_at,
    )


def _owned(db: Session, highlight_id: int, user: User) -> Highlight:
    row = db.get(Highlight, highlight_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Highlight not found")
    return row


@router.post("/books/{book_id}/highlights", response_model=HighlightOut, status_code=201)
def create_highlight(
    book_id: int,
    payload: HighlightIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = annotatable_for_user(db, book_id, user)
    ms = db.get(MicroSession, payload.micro_session_id)
    chapter = db.get(Chapter, ms.chapter_id) if ms else None
    if ms is None or chapter is None or chapter.book_id != book.id:
        raise HTTPException(status_code=422, detail="That passage is not in this book.")
    # Python string indexes are Unicode code points, which is what the client
    # sends, so the quote is cut exactly where the reader selected.
    if payload.end > len(ms.text):
        raise HTTPException(status_code=422, detail="Selection is outside the passage.")

    if not ms.text[payload.start : payload.end].strip():
        raise HTTPException(status_code=422, detail="Select some text, not just spaces.")

    # Serialise creates for one reader and passage, so two tabs cannot both
    # pass the overlap check below.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:user_id, :ms_id)"),
        {"user_id": user.id, "ms_id": ms.id},
    )
    clash = (
        db.query(Highlight.id)
        .filter(
            Highlight.user_id == user.id,
            Highlight.micro_session_id == ms.id,
            Highlight.start < payload.end,
            payload.start < Highlight.end,
        )
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail="That overlaps an existing highlight.")

    row = Highlight(
        user_id=user.id,
        book_id=book.id,
        micro_session_id=ms.id,
        start=payload.start,
        end=payload.end,
        quote=ms.text[payload.start : payload.end],
        context_before=ms.text[max(0, payload.start - CONTEXT_CHARS) : payload.start],
        context_after=ms.text[payload.end : payload.end + CONTEXT_CHARS],
        color=payload.color,
        comment=payload.comment,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row, chapter, ms, _session_numbers(db, book), _themes_for(db, user, book, {ms.id}).get(ms.id))


@router.get("/books/{book_id}/highlights", response_model=list[HighlightOut])
def list_highlights(
    book_id: int,
    micro_session_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = annotatable_for_user(db, book_id, user)
    query = (
        db.query(Highlight, Chapter, MicroSession)
        .join(MicroSession, Highlight.micro_session_id == MicroSession.id)
        .join(Chapter, MicroSession.chapter_id == Chapter.id)
        .filter(Highlight.user_id == user.id, Highlight.book_id == book.id)
    )
    if micro_session_id is not None:
        query = query.filter(Highlight.micro_session_id == micro_session_id)
    rows = query.order_by(Chapter.index, MicroSession.index, Highlight.start).all()
    numbers = _session_numbers(db, book)
    found = _themes_for(db, user, book, {m.id for _h, _c, m in rows})
    return [_out(h, c, m, numbers, found.get(m.id)) for h, c, m in rows]


@router.patch("/highlights/{highlight_id}", response_model=HighlightOut)
def update_highlight(
    highlight_id: int,
    payload: HighlightPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = _owned(db, highlight_id, user)
    sent = payload.model_fields_set
    if "color" in sent and payload.color is not None:
        row.color = payload.color
    if "comment" in sent:
        row.comment = payload.comment
    db.commit()
    db.refresh(row)
    ms = db.get(MicroSession, row.micro_session_id)
    book = db.get(Book, row.book_id)
    return _out(
        row,
        db.get(Chapter, ms.chapter_id),
        ms,
        _session_numbers(db, book),
        _themes_for(db, user, book, {ms.id}).get(ms.id),
    )


@router.delete("/highlights/{highlight_id}", status_code=204)
def delete_highlight(
    highlight_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    db.delete(_owned(db, highlight_id, user))
    db.commit()
    return Response(status_code=204)
