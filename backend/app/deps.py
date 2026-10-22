from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Book, User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_error
    user = db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user


def user_can_access(book: Book, user: User) -> bool:
    """Seeded books (no owner) are shared; an uploaded book is private to its
    uploader."""
    return book.owner_user_id is None or book.owner_user_id == user.id


RESEARCH = "research"


def is_research(book: Book) -> bool:
    return (book.source_type or "") == RESEARCH


def book_for_user(db: Session, book_id: int, user: User) -> Book:
    """Fetch a book the user is allowed to read, or 404.

    Deliberately 404 and not 403: a 403 would confirm that someone else's book
    exists at that id, which is exactly what we don't want to leak.

    Research documents are not books and are never returned here, so no
    reading-habit endpoint can reach one by id.
    """
    book = db.get(Book, book_id)
    if book is None or is_research(book) or not user_can_access(book, user):
        raise HTTPException(status_code=404, detail="Book not found")
    return book


def annotatable_for_user(db: Session, book_id: int, user: User) -> Book:
    """A book *or* a research document this user may annotate, or 404.

    Highlights, notes and citations are deliberately shared between the two
    tracks - they anchor to a micro-session, and a research chunk is one - so
    this is the one place that accepts both. Everything to do with reading
    habits goes through ``book_for_user``, which refuses research ids.
    """
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    if is_research(book):
        if book.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Book not found")
        return book
    if not user_can_access(book, user):
        raise HTTPException(status_code=404, detail="Book not found")
    return book


def research_for_user(db: Session, document_id: int, user: User) -> Book:
    """Fetch a research document owned by this user, or 404.

    Research documents are always private - there is no shared research
    library - so unlike a seeded book there is no null-owner case. 404 rather
    than 403, for the same reason as above.
    """
    document = db.get(Book, document_id)
    if document is None or not is_research(document) or document.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
