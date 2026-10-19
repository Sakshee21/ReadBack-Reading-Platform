"""Theme tagging: tables, service, validation and the provider call."""

import uuid

import pytest

from app.config import Settings
from app.database import SessionLocal
from app.models import (
    Book,
    Chapter,
    MicroSession,
    MicroSessionTagging,
    MicroSessionTheme,
    User,
)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_user(db) -> User:
    user = User(email=f"th_{uuid.uuid4().hex[:10]}@test.com", password_hash="x")
    db.add(user)
    db.commit()
    return user


def make_book(db, texts=("First chunk of text.", "Second chunk of text."), owner=None, consent=False):
    book = Book(
        title="TH test",
        author="Tester",
        full_text=" ".join(texts),
        owner_user_id=owner.id if owner else None,
        is_user_uploaded=owner is not None,
        source_type="upload" if owner else "seeded",
        theme_tagging_consent=consent,
    )
    chapter = Chapter(index=1, title="Chapter One", text=" ".join(texts), word_count=6)
    for i, t in enumerate(texts):
        chapter.micro_sessions.append(MicroSession(index=i + 1, text=t, word_count=4))
    book.chapters.append(chapter)
    db.add(book)
    db.commit()
    return book, list(chapter.micro_sessions)


def drop_book(db, book_id):
    from app.models import ReadingSession, UserBookProgress

    db.expire_all()
    db.query(UserBookProgress).filter(UserBookProgress.book_id == book_id).delete()
    db.query(ReadingSession).filter(ReadingSession.book_id == book_id).delete()
    db.commit()
    book = db.get(Book, book_id)
    if book is not None:
        db.delete(book)
        db.commit()


# --------------------------------------------------------------------------
# tables and settings
# --------------------------------------------------------------------------


def test_theme_rows_round_trip(db):
    book, (a, b) = make_book(db)
    try:
        db.add(
            MicroSessionTheme(
                micro_session_id=a.id, theme="romance", score=4, source="llm",
                model="m", prompt_version=1, theme_list_version=1,
            )
        )
        db.add(MicroSessionTagging(micro_session_id=a.id, status="done", model="m", prompt_version=1, theme_list_version=1))
        db.commit()
        db.expire_all()
        row = db.query(MicroSessionTheme).filter_by(micro_session_id=a.id).one()
        assert (row.theme, row.score, row.source, row.model) == ("romance", 4, "llm", "m")
        assert row.created_at is not None
        assert db.get(MicroSessionTagging, a.id).status == "done"
    finally:
        drop_book(db, book.id)


def test_deleting_a_book_removes_its_tags_and_tagging_rows(db):
    user = make_user(db)
    book, (a, _) = make_book(db, owner=user)
    db.add(MicroSessionTheme(micro_session_id=a.id, theme="romance", score=4, source="llm", model="m", prompt_version=1, theme_list_version=1))
    db.add(MicroSessionTagging(micro_session_id=a.id, status="done", model="m", prompt_version=1, theme_list_version=1))
    db.commit()
    ms_id = a.id
    db.delete(book)
    db.commit()
    db.expire_all()
    assert db.query(MicroSessionTheme).filter_by(micro_session_id=ms_id).count() == 0
    assert db.get(MicroSessionTagging, ms_id) is None


def test_book_consent_defaults_to_false(db):
    book, _ = make_book(db)
    try:
        db.expire_all()
        fresh = db.get(Book, book.id)
        assert fresh.theme_tagging_consent is False
        assert fresh.theme_tagging_consent_at is None
    finally:
        drop_book(db, book.id)


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.theme_tagging_on_demand is False
    assert s.theme_call_gap_seconds == 4.0
    assert s.op_api_key == "" and s.op_model == ""
