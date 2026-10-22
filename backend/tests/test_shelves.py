"""Shelves: a reader's own groupings of books.

The property that matters most here is that shelves are *organisational*. A
shelf holds references, so none of this may change a book, lose a book, or
leak one reader's library to another.
"""

import csv
import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Book, ReadingEvent, Shelf, ShelfBook, User


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def register(client) -> dict:
    email = f"shelf_{uuid.uuid4().hex[:10]}@test.com"
    token = client.post(
        "/auth/register", json={"email": email, "password": "pw12345"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def reader(client):
    return register(client)


@pytest.fixture
def seeded_books(client, reader):
    books = [b for b in client.get("/books", headers=reader).json() if b["status"] == "ready"]
    if len(books) < 2:
        pytest.skip("needs at least two seeded books; run scripts/seed_books.py")
    return books


def make_shelf(client, headers, name="Crime"):
    response = client.post("/shelves", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def cleanup(client, headers):
    for shelf in client.get("/shelves", headers=headers).json():
        client.delete(f"/shelves/{shelf['id']}", headers=headers)


# ---------------------------------------------------------------------------
# creating, renaming, deleting
# ---------------------------------------------------------------------------


def test_a_new_reader_has_no_shelves(client, reader):
    assert client.get("/shelves", headers=reader).json() == []


def test_a_shelf_can_be_created_and_listed(client, reader):
    shelf = make_shelf(client, reader, "Crime")
    try:
        assert shelf["name"] == "Crime"
        assert shelf["book_ids"] == []
        assert shelf["book_count"] == 0
        listed = client.get("/shelves", headers=reader).json()
        assert [s["id"] for s in listed] == [shelf["id"]]
    finally:
        cleanup(client, reader)


def test_a_name_is_trimmed_and_cannot_be_blank(client, reader):
    try:
        shelf = make_shelf(client, reader, "   To read  ")
        assert shelf["name"] == "To read"
        for bad in ("", "   ", "\t\n"):
            assert client.post("/shelves", json={"name": bad}, headers=reader).status_code == 422
        too_long = "x" * (settings.shelf_name_max + 1)
        assert client.post("/shelves", json={"name": too_long}, headers=reader).status_code == 422
    finally:
        cleanup(client, reader)


def test_a_name_is_unique_per_reader_whatever_the_case(client, reader):
    try:
        make_shelf(client, reader, "Crime")
        for clash in ("Crime", "crime", "CRIME", "  Crime "):
            response = client.post("/shelves", json={"name": clash}, headers=reader)
            assert response.status_code == 409, clash
    finally:
        cleanup(client, reader)


def test_two_readers_may_use_the_same_shelf_name(client, reader):
    other = register(client)
    try:
        make_shelf(client, reader, "Crime")
        assert client.post("/shelves", json={"name": "Crime"}, headers=other).status_code == 201
    finally:
        cleanup(client, reader)
        cleanup(client, other)


def test_a_shelf_can_be_renamed(client, reader):
    shelf = make_shelf(client, reader, "Crime")
    try:
        renamed = client.patch(
            f"/shelves/{shelf['id']}", json={"name": "Mystery"}, headers=reader
        ).json()
        assert renamed["name"] == "Mystery"
        # Renaming to its own name is allowed; only another shelf clashes.
        assert client.patch(
            f"/shelves/{shelf['id']}", json={"name": "mystery"}, headers=reader
        ).status_code == 200
    finally:
        cleanup(client, reader)


def test_renaming_onto_another_shelf_is_refused(client, reader):
    first = make_shelf(client, reader, "Crime")
    make_shelf(client, reader, "Romance")
    try:
        response = client.patch(
            f"/shelves/{first['id']}", json={"name": "romance"}, headers=reader
        )
        assert response.status_code == 409
    finally:
        cleanup(client, reader)


def test_the_shelf_cap_is_enforced(client, reader, monkeypatch):
    monkeypatch.setattr(settings, "shelves_per_user", 2)
    try:
        make_shelf(client, reader, "One")
        make_shelf(client, reader, "Two")
        response = client.post("/shelves", json={"name": "Three"}, headers=reader)
        assert response.status_code == 409
        assert "up to 2 shelves" in response.json()["detail"]
    finally:
        cleanup(client, reader)


# ---------------------------------------------------------------------------
# books on shelves
# ---------------------------------------------------------------------------


def test_a_book_can_be_put_on_a_shelf_and_taken_off_again(client, reader, seeded_books):
    shelf = make_shelf(client, reader, "Crime")
    book = seeded_books[0]
    try:
        added = client.post(
            f"/shelves/{shelf['id']}/books", json={"book_id": book["id"]}, headers=reader
        )
        assert added.status_code == 201
        assert added.json()["book_ids"] == [book["id"]]

        removed = client.delete(
            f"/shelves/{shelf['id']}/books/{book['id']}", headers=reader
        )
        assert removed.status_code == 200
        assert removed.json()["book_ids"] == []

        # The book itself is untouched.
        assert book["id"] in [b["id"] for b in client.get("/books", headers=reader).json()]
    finally:
        cleanup(client, reader)


def test_adding_the_same_book_twice_changes_nothing(client, reader, seeded_books):
    shelf = make_shelf(client, reader, "Crime")
    book = seeded_books[0]
    try:
        client.post(f"/shelves/{shelf['id']}/books", json={"book_id": book["id"]}, headers=reader)
        again = client.post(
            f"/shelves/{shelf['id']}/books", json={"book_id": book["id"]}, headers=reader
        )
        assert again.status_code == 201
        assert again.json()["book_ids"] == [book["id"]]
        assert again.json()["book_count"] == 1
    finally:
        cleanup(client, reader)


def test_a_book_can_be_on_several_shelves(client, reader, seeded_books):
    crime = make_shelf(client, reader, "Crime")
    favourites = make_shelf(client, reader, "Favourites")
    book = seeded_books[0]
    try:
        for shelf in (crime, favourites):
            client.post(
                f"/shelves/{shelf['id']}/books", json={"book_id": book["id"]}, headers=reader
            )
        listed = client.get("/shelves", headers=reader).json()
        assert all(book["id"] in s["book_ids"] for s in listed)
    finally:
        cleanup(client, reader)


def test_taking_a_book_off_one_shelf_leaves_it_on_the_other(client, reader, seeded_books):
    crime = make_shelf(client, reader, "Crime")
    favourites = make_shelf(client, reader, "Favourites")
    book = seeded_books[0]
    try:
        for shelf in (crime, favourites):
            client.post(
                f"/shelves/{shelf['id']}/books", json={"book_id": book["id"]}, headers=reader
            )
        client.delete(f"/shelves/{crime['id']}/books/{book['id']}", headers=reader)

        listed = {s["id"]: s for s in client.get("/shelves", headers=reader).json()}
        assert listed[crime["id"]]["book_ids"] == []
        assert listed[favourites["id"]]["book_ids"] == [book["id"]]
    finally:
        cleanup(client, reader)


def test_removing_a_book_that_is_not_there_is_404(client, reader, seeded_books):
    shelf = make_shelf(client, reader, "Crime")
    try:
        response = client.delete(
            f"/shelves/{shelf['id']}/books/{seeded_books[0]['id']}", headers=reader
        )
        assert response.status_code == 404
    finally:
        cleanup(client, reader)


def test_the_books_per_shelf_cap_is_enforced(client, reader, seeded_books, monkeypatch):
    monkeypatch.setattr(settings, "books_per_shelf", 1)
    shelf = make_shelf(client, reader, "Crime")
    try:
        first = client.post(
            f"/shelves/{shelf['id']}/books", json={"book_id": seeded_books[0]["id"]}, headers=reader
        )
        assert first.status_code == 201
        second = client.post(
            f"/shelves/{shelf['id']}/books", json={"book_id": seeded_books[1]["id"]}, headers=reader
        )
        assert second.status_code == 409
    finally:
        cleanup(client, reader)


def test_an_unknown_book_cannot_be_shelved(client, reader):
    shelf = make_shelf(client, reader, "Crime")
    try:
        response = client.post(
            f"/shelves/{shelf['id']}/books", json={"book_id": 999999}, headers=reader
        )
        assert response.status_code == 404
    finally:
        cleanup(client, reader)


# ---------------------------------------------------------------------------
# ordering
# ---------------------------------------------------------------------------


def test_shelves_keep_the_order_they_are_given(client, reader):
    first = make_shelf(client, reader, "One")
    second = make_shelf(client, reader, "Two")
    third = make_shelf(client, reader, "Three")
    try:
        wanted = [third["id"], first["id"], second["id"]]
        reordered = client.post("/shelves/reorder", json={"ids": wanted}, headers=reader).json()
        assert [s["id"] for s in reordered] == wanted
        # And it survives a reload.
        assert [s["id"] for s in client.get("/shelves", headers=reader).json()] == wanted
    finally:
        cleanup(client, reader)


def test_a_partial_order_keeps_the_rest_rather_than_losing_it(client, reader):
    first = make_shelf(client, reader, "One")
    second = make_shelf(client, reader, "Two")
    third = make_shelf(client, reader, "Three")
    try:
        reordered = client.post(
            "/shelves/reorder", json={"ids": [third["id"]]}, headers=reader
        ).json()
        assert [s["id"] for s in reordered] == [third["id"], first["id"], second["id"]]
    finally:
        cleanup(client, reader)


def test_books_keep_the_order_they_are_given(client, reader, seeded_books):
    shelf = make_shelf(client, reader, "Crime")
    ids = [book["id"] for book in seeded_books[:2]]
    try:
        for book_id in ids:
            client.post(f"/shelves/{shelf['id']}/books", json={"book_id": book_id}, headers=reader)
        wanted = list(reversed(ids))
        body = client.post(
            f"/shelves/{shelf['id']}/books/reorder", json={"ids": wanted}, headers=reader
        ).json()
        assert body["book_ids"] == wanted
    finally:
        cleanup(client, reader)


def test_reordering_refuses_an_id_that_is_not_yours(client, reader):
    other = register(client)
    theirs = make_shelf(client, other, "Theirs")
    mine = make_shelf(client, reader, "Mine")
    try:
        response = client.post(
            "/shelves/reorder", json={"ids": [mine["id"], theirs["id"]]}, headers=reader
        )
        assert response.status_code == 404
    finally:
        cleanup(client, reader)
        cleanup(client, other)


# ---------------------------------------------------------------------------
# privacy
# ---------------------------------------------------------------------------


def test_one_reader_never_sees_another_readers_shelves(client, reader):
    other = register(client)
    theirs = make_shelf(client, other, "Theirs")
    try:
        assert client.get("/shelves", headers=reader).json() == []
        assert client.patch(
            f"/shelves/{theirs['id']}", json={"name": "Mine now"}, headers=reader
        ).status_code == 404
        assert client.delete(f"/shelves/{theirs['id']}", headers=reader).status_code == 404
        assert client.post(
            f"/shelves/{theirs['id']}/books", json={"book_id": 1}, headers=reader
        ).status_code == 404
        # Still theirs, unchanged.
        assert client.get("/shelves", headers=other).json()[0]["name"] == "Theirs"
    finally:
        cleanup(client, other)


def test_a_private_upload_cannot_be_shelved_by_anyone_else(client, reader):
    """book_for_user 404s on someone else's upload, which closes this too."""
    owner = register(client)
    db = SessionLocal()
    try:
        owner_row = db.query(User).order_by(User.id.desc()).first()
        upload = Book(
            gutenberg_id=None,
            title="A private upload",
            author="Someone",
            full_text="",
            total_word_count=0,
            owner_user_id=owner_row.id,
            is_user_uploaded=True,
            source_type="upload",
            status="ready",
        )
        db.add(upload)
        db.commit()
        upload_id = upload.id
    finally:
        db.close()

    shelf = make_shelf(client, reader, "Mine")
    try:
        response = client.post(
            f"/shelves/{shelf['id']}/books", json={"book_id": upload_id}, headers=reader
        )
        assert response.status_code == 404
    finally:
        cleanup(client, reader)
        db = SessionLocal()
        try:
            db.query(ShelfBook).filter(ShelfBook.book_id == upload_id).delete()
            db.query(Book).filter(Book.id == upload_id).delete()
            db.commit()
        finally:
            db.close()


def test_shelves_need_authentication(client):
    assert client.get("/shelves").status_code == 401
    assert client.post("/shelves", json={"name": "Crime"}).status_code == 401


# ---------------------------------------------------------------------------
# cascades
# ---------------------------------------------------------------------------


def test_deleting_a_shelf_keeps_the_books(client, reader, seeded_books):
    shelf = make_shelf(client, reader, "Crime")
    book = seeded_books[0]
    client.post(f"/shelves/{shelf['id']}/books", json={"book_id": book["id"]}, headers=reader)

    assert client.delete(f"/shelves/{shelf['id']}", headers=reader).status_code == 204
    assert client.get("/shelves", headers=reader).json() == []

    db = SessionLocal()
    try:
        assert db.query(ShelfBook).filter(ShelfBook.shelf_id == shelf["id"]).count() == 0
        assert db.get(Book, book["id"]) is not None
    finally:
        db.close()


def test_deleting_an_uploaded_book_takes_it_off_every_shelf(client, reader):
    """A shelf must not be left pointing at a book that no longer exists."""
    db = SessionLocal()
    try:
        me = db.query(User).order_by(User.id.desc()).first()
        upload = Book(
            gutenberg_id=None,
            title="My upload",
            author="Me",
            full_text="",
            total_word_count=0,
            owner_user_id=me.id,
            is_user_uploaded=True,
            source_type="upload",
            status="ready",
        )
        db.add(upload)
        db.commit()
        upload_id = upload.id
    finally:
        db.close()

    # The fixture reader is the most recently registered user, which is who
    # the upload belongs to.
    shelf = make_shelf(client, reader, "Mine")
    added = client.post(
        f"/shelves/{shelf['id']}/books", json={"book_id": upload_id}, headers=reader
    )
    assert added.status_code == 201, added.text

    assert client.delete(f"/books/{upload_id}", headers=reader).status_code == 204

    body = client.get("/shelves", headers=reader).json()
    assert body[0]["book_ids"] == []
    db = SessionLocal()
    try:
        assert db.query(ShelfBook).filter(ShelfBook.book_id == upload_id).count() == 0
    finally:
        db.close()
    cleanup(client, reader)


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------


def _events_for(user_email_headers, client, types):
    response = client.get(f"/admin/export/events.csv?token={settings.admin_token}")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    return [row for row in rows if row["event_type"] in types]


def test_shelf_events_are_recorded_and_exported(client, reader, seeded_books):
    shelf = make_shelf(client, reader, "Crime")
    book = seeded_books[0]
    client.post(f"/shelves/{shelf['id']}/books", json={"book_id": book["id"]}, headers=reader)
    client.patch(f"/shelves/{shelf['id']}", json={"name": "Mystery"}, headers=reader)
    client.delete(f"/shelves/{shelf['id']}/books/{book['id']}", headers=reader)
    client.delete(f"/shelves/{shelf['id']}", headers=reader)

    db = SessionLocal()
    try:
        kinds = [
            row.event_type
            for row in db.query(ReadingEvent)
            .filter(ReadingEvent.event_type.like("%shelf%"))
            .order_by(ReadingEvent.id)
            .all()
        ]
    finally:
        db.close()
    for expected in (
        "shelf_created",
        "book_added_to_shelf",
        "shelf_renamed",
        "book_removed_from_shelf",
        "shelf_deleted",
    ):
        assert expected in kinds, expected

    exported = _events_for(reader, client, {"shelf_created", "shelf_deleted"})
    assert exported, "shelf events must reach the pilot CSV"


def test_a_shelf_name_is_never_in_an_event(client, reader, seeded_books):
    """A reader may name a shelf after a diagnosis or a person. Ids and counts
    are enough to analyse the feature; the name is not ours to export."""
    make_shelf(client, reader, "Grief and loss")
    try:
        db = SessionLocal()
        try:
            rows = (
                db.query(ReadingEvent)
                .filter(ReadingEvent.event_type.like("%shelf%"))
                .all()
            )
            blob = " ".join(str(row.event_metadata) for row in rows)
        finally:
            db.close()
        assert "Grief" not in blob
        assert "grief" not in blob.lower()

        response = client.get(f"/admin/export/events.csv?token={settings.admin_token}")
        assert "Grief and loss" not in response.text
    finally:
        cleanup(client, reader)


def test_existing_event_logging_still_works(client, reader):
    """Shelf events are written server-side; the browser path must be
    unaffected."""
    response = client.post(
        "/events",
        json={"event_type": "session_start", "book_id": None},
        headers=reader,
    )
    assert response.status_code == 201
    assert response.json() == {"logged": 1}
