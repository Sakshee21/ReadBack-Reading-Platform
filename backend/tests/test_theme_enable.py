"""Seeded books are tagged for everyone; only uploads have a tagging switch (their consent)."""

import pytest

from app.models import Book, MicroSessionTheme
from app.services import theme_worker
from tests.test_themes_api import auth, client, passage_themes, set_position, tag  # noqa: F401
from tests.test_themes_service import db, drop_book, make_book, make_user  # noqa: F401
from tests.test_themes_worker import prefetch  # noqa: F401

TEXTS = tuple(f"Chunk number {i}." for i in range(8))


def listed(client, user, book):
    return next(r for r in client.get("/books", headers=auth(user)).json() if r["id"] == book.id)


@pytest.fixture()
def seeded(db):
    book, chunks = make_book(db, texts=TEXTS)
    yield book, chunks
    drop_book(db, book.id)


def test_every_reader_sees_a_seeded_books_tags_with_nothing_switched_on(client, db, seeded):
    book, chunks = seeded
    tag(db, chunks[0], ("romance", 5))
    reader = make_user(db)
    set_position(db, reader, book, chunks[0])
    assert listed(client, reader, book)["theme_tagging_enabled"] is False  # no switch exists for it
    body = client.get(f"/books/{book.id}/themes", headers=auth(reader)).json()
    assert [t["theme"] for t in body["themes"]] == ["romance"]
    assert passage_themes(client, reader, book, chunks[0]).json()["themes"][0]["theme"] == "romance"


def test_there_is_no_per_reader_switch_route_any_more(client, db, seeded):
    book, _ = seeded
    reader = make_user(db)
    response = client.patch(f"/books/{book.id}/theme-tagging", json={"enabled": True}, headers=auth(reader))
    assert response.status_code in (404, 405)


def test_a_seeded_book_is_never_tagged_on_demand(client, db, seeded, monkeypatch):
    book, chunks = seeded
    monkeypatch.setattr("app.config.settings.theme_tagging_on_demand", True)
    monkeypatch.setattr("app.config.settings.op_api_key", "k")
    monkeypatch.setattr("app.config.settings.op_model", "m")
    started = []
    monkeypatch.setattr(theme_worker, "run_prefetch", lambda *a, **kw: started.append(a))
    reader = make_user(db)
    assert prefetch(client, auth(reader), book, chunks[0]).json() == {"queued": 0}
    assert started == []


def test_an_uploads_switch_is_the_owners_consent(client, db):
    owner, stranger = make_user(db), make_user(db)
    book, chunks = make_book(db, owner=owner)
    try:
        assert listed(client, owner, book)["theme_tagging_enabled"] is False
        client.patch(f"/books/{book.id}/theme-consent", json={"granted": True}, headers=auth(owner))
        assert listed(client, owner, book)["theme_tagging_enabled"] is True
        body = client.get(f"/books/{book.id}/reader", headers=auth(owner)).json()
        assert body["book"]["theme_tagging_enabled"] is True
        client.patch(f"/books/{book.id}/theme-consent", json={"granted": False}, headers=auth(owner))
        assert listed(client, owner, book)["theme_tagging_enabled"] is False
    finally:
        drop_book(db, book.id)
