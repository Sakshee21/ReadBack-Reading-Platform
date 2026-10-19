"""Researcher tools, server side: publication year and highlight themes."""

import json

import pytest

from app.models import Book, Highlight, MicroSessionTheme
from app.services import themes
from scripts import seed_books
from tests.test_themes_api import auth, client, tag  # noqa: F401
from tests.test_themes_service import db, drop_book, make_book, make_user  # noqa: F401


def highlight(db, user, book, ms, quote="Lovers met"):
    row = Highlight(
        user_id=user.id, book_id=book.id, micro_session_id=ms.id,
        start=0, end=len(quote), quote=quote, color="yellow",
    )
    db.add(row)
    db.commit()
    return row


# --------------------------------------------------------------------------
# publication year
# --------------------------------------------------------------------------


def test_the_book_list_carries_what_a_citation_needs(client, db):
    user = make_user(db)
    book, _ = make_book(db)
    book.gutenberg_id, book.published_year = 987_100_001, 1818
    db.commit()
    try:
        row = next(r for r in client.get("/books", headers=auth(user)).json() if r["id"] == book.id)
        assert row["published_year"] == 1818 and row["gutenberg_id"] == 987_100_001
        assert row["author"] == "Tester" and row["title"] == "TH test"
    finally:
        drop_book(db, book.id)


def test_an_upload_has_no_publication_year(client, db):
    owner = make_user(db)
    book, _ = make_book(db, owner=owner)
    try:
        row = next(r for r in client.get("/books", headers=auth(owner)).json() if r["id"] == book.id)
        assert row["published_year"] is None
    finally:
        drop_book(db, book.id)


def test_seed_data_has_the_first_publication_years():
    years = {entry["gutenberg_id"]: entry["published_year"] for entry in seed_books.SEED_BOOKS}
    assert years == {1952: 1892, 11: 1865, 74: 1876, 84: 1818, 1342: 1813}


# --------------------------------------------------------------------------
# themes on highlight rows
# --------------------------------------------------------------------------


def themes_of(client, user, book):
    return client.get(f"/books/{book.id}/highlights", headers=auth(user)).json()[0]["themes"]


def test_a_highlight_lists_its_passage_themes_best_first_and_score_3_plus(client, db):
    user = make_user(db)
    book, (a, b) = make_book(db)
    try:
        tag(db, a, ("romance", 3), ("war_conflict", 5), ("class_money", 2))
        highlight(db, user, book, a)
        assert themes_of(client, user, book) == [
            {"theme": "war_conflict", "label": "War & conflict"},
            {"theme": "romance", "label": "Romance & courtship"},
        ]
    finally:
        drop_book(db, book.id)


def test_a_highlight_on_an_untagged_passage_has_no_themes(client, db):
    user = make_user(db)
    book, (a, b) = make_book(db)
    try:
        highlight(db, user, book, a)
        assert themes_of(client, user, book) == []
    finally:
        drop_book(db, book.id)


def test_highlight_themes_skip_retired_theme_ids(client, db):
    user = make_user(db)
    book, (a, b) = make_book(db)
    try:
        tag(db, a, ("romance", 4))
        db.add(MicroSessionTheme(micro_session_id=a.id, theme="retired_theme", score=5, source="llm"))
        db.commit()
        highlight(db, user, book, a)
        assert [t["theme"] for t in themes_of(client, user, book)] == ["romance"]
    finally:
        drop_book(db, book.id)


def test_each_highlight_gets_its_own_passages_themes(client, db):
    user = make_user(db)
    book, (a, b) = make_book(db)
    try:
        tag(db, a, ("romance", 4))
        tag(db, b, ("nature_place", 4))
        from tests.test_themes_api import set_position

        set_position(db, user, book, b)  # reached both
        highlight(db, user, book, a)
        highlight(db, user, book, b, quote="Second chunk")
        rows = client.get(f"/books/{book.id}/highlights", headers=auth(user)).json()
        assert [[t["theme"] for t in r["themes"]] for r in rows] == [["romance"], ["nature_place"]]
    finally:
        drop_book(db, book.id)


# --------------------------------------------------------------------------
# highlight themes follow the spoiler rule
# --------------------------------------------------------------------------


def test_a_highlight_on_a_passage_the_reader_has_not_reached_gets_no_themes(client, db):
    from tests.test_themes_api import set_position

    user = make_user(db)
    book, (a, b) = make_book(db)
    try:
        tag(db, a, ("romance", 4))
        tag(db, b, ("war_conflict", 5))
        set_position(db, user, book, a)  # the reader is on the first chunk only
        highlight(db, user, book, a)
        highlight(db, user, book, b, quote="Second chunk")
        rows = client.get(f"/books/{book.id}/highlights", headers=auth(user)).json()
        assert [[t["theme"] for t in r["themes"]] for r in rows] == [["romance"], []]
    finally:
        drop_book(db, book.id)


def test_highlight_themes_vanish_with_an_uploads_consent(client, db):
    owner = make_user(db)
    book, (a, b) = make_book(db, owner=owner, consent=True)
    try:
        tag(db, a, ("romance", 4))
        highlight(db, owner, book, a)
        assert [t["theme"] for t in themes_of(client, owner, book)] == ["romance"]
        client.patch(f"/books/{book.id}/theme-consent", json={"granted": False}, headers=auth(owner))
        assert themes_of(client, owner, book) == []
    finally:
        drop_book(db, book.id)
