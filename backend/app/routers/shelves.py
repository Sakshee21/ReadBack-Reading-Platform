"""Shelves: a reader's own groupings of books.

Purely organisational. A shelf holds references, so putting a book on one
changes nothing about the book, taking it off leaves it in the library, and
deleting a shelf deletes no books. Nothing here touches the reader, the
seeded content or any pilot measure.

Everything is scoped to the signed-in reader. A shelf belonging to someone
else is **404, not 403**, for the same reason a private upload is: a 403
confirms that a shelf exists at that id.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import book_for_user, get_current_user
from app.models import ReadingEvent, Shelf, ShelfBook, User
from app.schemas import ReorderIn, ShelfBookIn, ShelfIn, ShelfOut

router = APIRouter(prefix="/shelves", tags=["shelves"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _shelf_for_user(db: Session, shelf_id: int, user: User) -> Shelf:
    shelf = db.get(Shelf, shelf_id)
    if shelf is None or shelf.user_id != user.id:
        raise HTTPException(status_code=404, detail="Shelf not found")
    return shelf


def _out(shelf: Shelf) -> ShelfOut:
    ordered = sorted(shelf.books, key=lambda row: (row.position, row.book_id))
    return ShelfOut(
        id=shelf.id,
        name=shelf.name,
        position=shelf.position,
        book_ids=[row.book_id for row in ordered],
        book_count=len(ordered),
        created_at=shelf.created_at,
    )


def _log(db: Session, user: User, event_type: str, *, book_id: int | None = None, **fields) -> None:
    """Record a shelf event.

    Written here rather than from the browser because these are server
    actions, and an event that only fires when a client remembers to send it
    is not worth counting. **The shelf name is never in the payload** - a
    reader naming a shelf after a diagnosis or a person should not put that in
    the pilot export. Ids and counts only.
    """
    db.add(
        ReadingEvent(
            user_id=user.id,
            book_id=book_id,
            event_type=event_type,
            event_metadata=fields or None,
        )
    )


def _next_position(values: list[int]) -> int:
    return (max(values) + 1) if values else 0


def _apply_order(rows: list, ids: list[int], key) -> None:
    """Put ``rows`` in the order given by ``ids``.

    Anything not listed keeps its relative order after the ones that are, so a
    partial list cannot lose a shelf or a book.
    """
    wanted = {value: index for index, value in enumerate(ids)}
    ordered = sorted(
        rows,
        key=lambda row: (wanted.get(key(row), len(wanted)), row.position, key(row)),
    )
    for index, row in enumerate(ordered):
        row.position = index


# ---------------------------------------------------------------------------
# shelves
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ShelfOut])
def list_shelves(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """This reader's shelves, in their chosen order, each with its book ids."""
    shelves = (
        db.query(Shelf)
        .filter(Shelf.user_id == user.id)
        .order_by(Shelf.position, Shelf.id)
        .all()
    )
    return [_out(shelf) for shelf in shelves]


@router.post("", response_model=ShelfOut, status_code=201)
def create_shelf(
    payload: ShelfIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    existing = db.query(Shelf).filter(Shelf.user_id == user.id).all()
    if len(existing) >= settings.shelves_per_user:
        raise HTTPException(
            status_code=409,
            detail=f"You can keep up to {settings.shelves_per_user} shelves. "
            "Delete one to make room.",
        )

    key = payload.name.casefold()
    if any(shelf.name_key == key for shelf in existing):
        raise HTTPException(status_code=409, detail="You already have a shelf with that name.")

    shelf = Shelf(
        user_id=user.id,
        name=payload.name,
        name_key=key,
        position=_next_position([s.position for s in existing]),
    )
    db.add(shelf)
    db.flush()
    _log(db, user, "shelf_created", shelf_id=shelf.id, shelf_count=len(existing) + 1)
    db.commit()
    db.refresh(shelf)
    return _out(shelf)


@router.patch("/{shelf_id}", response_model=ShelfOut)
def rename_shelf(
    shelf_id: int,
    payload: ShelfIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    shelf = _shelf_for_user(db, shelf_id, user)
    key = payload.name.casefold()
    clash = (
        db.query(Shelf)
        .filter(Shelf.user_id == user.id, Shelf.name_key == key, Shelf.id != shelf.id)
        .first()
    )
    if clash is not None:
        raise HTTPException(status_code=409, detail="You already have a shelf with that name.")

    shelf.name = payload.name
    shelf.name_key = key
    _log(db, user, "shelf_renamed", shelf_id=shelf.id)
    db.commit()
    db.refresh(shelf)
    return _out(shelf)


@router.delete("/{shelf_id}", status_code=204)
def delete_shelf(
    shelf_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Delete a shelf. The books on it stay in the library."""
    shelf = _shelf_for_user(db, shelf_id, user)
    book_count = len(shelf.books)
    _log(db, user, "shelf_deleted", shelf_id=shelf.id, book_count=book_count)
    db.delete(shelf)
    db.commit()
    return None


@router.post("/reorder", response_model=list[ShelfOut])
def reorder_shelves(
    payload: ReorderIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    shelves = db.query(Shelf).filter(Shelf.user_id == user.id).all()
    mine = {shelf.id for shelf in shelves}
    unknown = [shelf_id for shelf_id in payload.ids if shelf_id not in mine]
    if unknown:
        raise HTTPException(status_code=404, detail="Shelf not found")

    _apply_order(shelves, payload.ids, key=lambda shelf: shelf.id)
    db.commit()
    return list_shelves(db=db, user=user)


# ---------------------------------------------------------------------------
# books on a shelf
# ---------------------------------------------------------------------------


@router.post("/{shelf_id}/books", response_model=ShelfOut, status_code=201)
def add_book(
    shelf_id: int,
    payload: ShelfBookIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Put a book on a shelf.

    Only a book this reader can open: ``book_for_user`` 404s on someone else's
    upload and on a research document, so neither can be shelved.
    """
    shelf = _shelf_for_user(db, shelf_id, user)
    book = book_for_user(db, payload.book_id, user)

    already = next((row for row in shelf.books if row.book_id == book.id), None)
    if already is not None:
        return _out(shelf)  # adding twice is not an error, it is a no-op

    if len(shelf.books) >= settings.books_per_shelf:
        raise HTTPException(
            status_code=409,
            detail=f"A shelf holds up to {settings.books_per_shelf} books.",
        )

    db.add(
        ShelfBook(
            shelf_id=shelf.id,
            book_id=book.id,
            position=_next_position([row.position for row in shelf.books]),
            added_at=dt.datetime.utcnow(),
        )
    )
    _log(
        db,
        user,
        "book_added_to_shelf",
        book_id=book.id,
        shelf_id=shelf.id,
        book_count=len(shelf.books) + 1,
    )
    db.commit()
    db.refresh(shelf)
    return _out(shelf)


@router.delete("/{shelf_id}/books/{book_id}", response_model=ShelfOut)
def remove_book(
    shelf_id: int,
    book_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Take a book off a shelf. The book stays in the library."""
    shelf = _shelf_for_user(db, shelf_id, user)
    row = next((row for row in shelf.books if row.book_id == book_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="That book is not on this shelf.")

    db.delete(row)
    _log(
        db,
        user,
        "book_removed_from_shelf",
        book_id=book_id,
        shelf_id=shelf.id,
        book_count=len(shelf.books) - 1,
    )
    db.commit()
    db.refresh(shelf)
    return _out(shelf)


@router.post("/{shelf_id}/books/reorder", response_model=ShelfOut)
def reorder_books(
    shelf_id: int,
    payload: ReorderIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    shelf = _shelf_for_user(db, shelf_id, user)
    on_shelf = {row.book_id for row in shelf.books}
    unknown = [book_id for book_id in payload.ids if book_id not in on_shelf]
    if unknown:
        raise HTTPException(status_code=404, detail="That book is not on this shelf.")

    _apply_order(shelf.books, payload.ids, key=lambda row: row.book_id)
    db.commit()
    db.refresh(shelf)
    return _out(shelf)
