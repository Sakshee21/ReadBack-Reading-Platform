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


def book_for_user(db: Session, book_id: int, user: User) -> Book:
    """Fetch a book the user is allowed to read, or 404.

    Deliberately 404 and not 403: a 403 would confirm that someone else's book
    exists at that id, which is exactly what we don't want to leak.
    """
    book = db.get(Book, book_id)
    if book is None or not user_can_access(book, user):
        raise HTTPException(status_code=404, detail="Book not found")
    return book
