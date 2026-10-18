"""Highlights: a reader's private, per-book annotations of micro-session text."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Book, Chapter, Highlight, MicroSession, User, UserBookProgress
from app.security import create_access_token


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def make_user(db) -> User:
    user = User(email=f"hl_{uuid.uuid4().hex[:10]}@test.com", password_hash="x")
    db.add(user)
    db.commit()
    return user


def auth(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def make_book(db, text="Hello world. A second sentence here.", owner=None):
    book = Book(
        title="HL test",
        author="Tester",
        full_text=text,
        owner_user_id=owner.id if owner else None,
        is_user_uploaded=owner is not None,
        source_type="upload" if owner else "seeded",
    )
    chapter = Chapter(index=1, title="Chapter One", text=text, word_count=6)
    chapter.micro_sessions.append(MicroSession(index=1, text=text, word_count=6))
    book.chapters.append(chapter)
    db.add(book)
    db.commit()
    return book, chapter.micro_sessions[0]


def add_chapter(db, book, index, text):
    chapter = Chapter(book_id=book.id, index=index, title=f"Chapter {index}", text=text, word_count=3)
    chapter.micro_sessions.append(MicroSession(index=1, text=text, word_count=3))
    db.add(chapter)
    db.commit()
    return chapter.micro_sessions[0]


def drop_book(db, book_id):
    db.expire_all()
    book = db.get(Book, book_id)
    if book is not None:
        db.delete(book)
        db.commit()


def make_highlight(db, user, book, ms, start=0, end=5, color="yellow"):
    row = Highlight(
        user_id=user.id,
        book_id=book.id,
        micro_session_id=ms.id,
        start=start,
        end=end,
        quote=ms.text[start:end],
        context_before="",
        context_after=ms.text[end : end + 40],
        color=color,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def shared(db):
    """A shared (seeded-style) book with one chapter and one micro-session."""
    book, ms = make_book(db)
    yield book, ms
    drop_book(db, book.id)


@pytest.fixture()
def reader(db):
    return auth(make_user(db))


def post(client, headers, book, ms, start, end, color="yellow", **extra):
    body = {"micro_session_id": ms.id, "start": start, "end": end, "color": color, **extra}
    return client.post(f"/books/{book.id}/highlights", json=body, headers=headers)


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------


def test_highlight_row_round_trips(db):
    user = make_user(db)
    book, ms = make_book(db)
    try:
        row = make_highlight(db, user, book, ms, 0, 5)
        db.expire_all()
        got = db.get(Highlight, row.id)
        assert (got.start, got.end, got.quote, got.color) == (0, 5, "Hello", "yellow")
        assert got.comment is None
        assert got.created_at is not None and got.updated_at is not None
    finally:
        drop_book(db, book.id)


def test_deleting_a_micro_session_removes_its_highlights(db):
    user = make_user(db)
    book, ms = make_book(db)
    try:
        row_id = make_highlight(db, user, book, ms).id
        chapter = db.get(Chapter, ms.chapter_id)
        chapter.micro_sessions.clear()
        db.commit()
        db.expire_all()
        assert db.get(Highlight, row_id) is None
    finally:
        drop_book(db, book.id)


def test_deleting_the_book_removes_highlights(db):
    user = make_user(db)
    book, ms = make_book(db, owner=user)
    row_id = make_highlight(db, user, book, ms).id
    db.delete(book)
    db.commit()
    db.expire_all()
    assert db.get(Highlight, row_id) is None


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


def test_requires_auth(client, shared):
    book, _ = shared
    assert client.get(f"/books/{book.id}/highlights").status_code == 401
    assert client.post(f"/books/{book.id}/highlights", json={}).status_code == 401
    assert client.patch("/highlights/1", json={"color": "blue"}).status_code == 401
    assert client.delete("/highlights/1").status_code == 401


def test_create_derives_quote_and_context_from_the_text(client, reader, shared):
    book, ms = shared
    resp = post(client, reader, book, ms, 0, 5, comment="greeting")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["quote"] == "Hello"
    assert body["context_before"] == ""
    assert body["context_after"] == ms.text[5:45]
    assert body["comment"] == "greeting"
    assert body["color"] == "yellow"
    assert (body["chapter_index"], body["chapter_title"], body["session_index"]) == (1, "Chapter One", 1)

    inner = post(client, reader, book, ms, 13, 22).json()
    assert inner["context_before"] == ms.text[0:13]
    assert inner["quote"] == ms.text[13:22]


def test_list_is_in_reading_order_and_has_location_fields(client, reader, shared, db):
    book, ms = shared
    ms2 = add_chapter(db, book, 2, "Second chapter text.")
    post(client, reader, book, ms2, 0, 6)
    post(client, reader, book, ms, 13, 22)
    post(client, reader, book, ms, 0, 5)
    rows = client.get(f"/books/{book.id}/highlights", headers=reader).json()
    assert [(r["chapter_index"], r["start"]) for r in rows] == [(1, 0), (1, 13), (2, 0)]
    assert rows[2]["chapter_title"] == "Chapter 2"
    assert {"id", "micro_session_id", "session_index", "quote", "color", "created_at"} <= set(rows[0])


def test_list_can_filter_by_micro_session(client, reader, shared, db):
    book, ms = shared
    ms2 = add_chapter(db, book, 2, "More text here.")
    post(client, reader, book, ms, 0, 5)
    post(client, reader, book, ms2, 0, 4)
    rows = client.get(
        f"/books/{book.id}/highlights", params={"micro_session_id": ms2.id}, headers=reader
    ).json()
    assert [r["micro_session_id"] for r in rows] == [ms2.id]


def test_patch_changes_colour_and_comment_and_can_clear_comment(client, reader, shared):
    book, ms = shared
    hid = post(client, reader, book, ms, 0, 5, comment="a").json()["id"]
    r = client.patch(f"/highlights/{hid}", json={"color": "blue"}, headers=reader).json()
    assert (r["color"], r["comment"]) == ("blue", "a")
    r = client.patch(f"/highlights/{hid}", json={"comment": "b"}, headers=reader).json()
    assert (r["color"], r["comment"]) == ("blue", "b")
    r = client.patch(f"/highlights/{hid}", json={"comment": None}, headers=reader).json()
    assert r["comment"] is None
    assert client.patch(f"/highlights/{hid}", json={"color": "teal"}, headers=reader).status_code == 422
    assert client.patch(f"/highlights/{hid}", json={"comment": "x" * 2001}, headers=reader).status_code == 422


def test_delete_removes_it(client, reader, shared):
    book, ms = shared
    hid = post(client, reader, book, ms, 0, 5).json()["id"]
    assert client.delete(f"/highlights/{hid}", headers=reader).status_code == 204
    assert client.get(f"/books/{book.id}/highlights", headers=reader).json() == []
    assert client.delete(f"/highlights/{hid}", headers=reader).status_code == 404


def test_overlap_is_409_and_touching_is_allowed(client, reader, shared):
    book, ms = shared
    assert post(client, reader, book, ms, 0, 5).status_code == 201
    assert post(client, reader, book, ms, 3, 8).status_code == 409
    assert post(client, reader, book, ms, 0, 5).status_code == 409
    assert post(client, reader, book, ms, 1, 3).status_code == 409
    assert post(client, reader, book, ms, 5, 8).status_code == 201  # touches at 5
    assert post(client, reader, book, ms, 13, 14).status_code == 201


def test_overlap_only_counts_the_same_readers_highlights(client, shared, db):
    book, ms = shared
    a, b = auth(make_user(db)), auth(make_user(db))
    assert post(client, a, book, ms, 0, 5).status_code == 201
    assert post(client, b, book, ms, 0, 5).status_code == 201


@pytest.mark.parametrize("start,end", [(3, 3), (-1, 4), (0, 999), (5, 2)])
def test_bad_ranges_are_422(client, reader, shared, start, end):
    book, ms = shared
    assert post(client, reader, book, ms, start, end).status_code == 422


def test_selection_over_2000_characters_is_422(client, reader, db):
    book, ms = make_book(db, text="word " * 600)
    try:
        assert post(client, reader, book, ms, 0, 2000).status_code == 201
        assert post(client, reader, book, ms, 2000, 4001).status_code == 422
    finally:
        drop_book(db, book.id)


def test_unknown_colour_is_422(client, reader, shared):
    book, ms = shared
    assert post(client, reader, book, ms, 0, 5, color="teal").status_code == 422


def test_comment_over_2000_is_422(client, reader, shared):
    book, ms = shared
    assert post(client, reader, book, ms, 0, 5, comment="x" * 2001).status_code == 422
    assert post(client, reader, book, ms, 0, 5, comment="x" * 2000).status_code == 201


def test_micro_session_from_another_book_is_422(client, reader, shared, db):
    book, _ = shared
    other, other_ms = make_book(db, text="Totally different book text.")
    try:
        assert post(client, reader, book, other_ms, 0, 5).status_code == 422
    finally:
        drop_book(db, other.id)


def test_other_readers_highlight_is_404_and_absent_from_list(client, shared, db):
    book, ms = shared
    a, b = auth(make_user(db)), auth(make_user(db))
    hid = post(client, a, book, ms, 0, 5).json()["id"]
    assert client.get(f"/books/{book.id}/highlights", headers=b).json() == []
    assert client.patch(f"/highlights/{hid}", json={"color": "pink"}, headers=b).status_code == 404
    assert client.delete(f"/highlights/{hid}", headers=b).status_code == 404
    still = client.get(f"/books/{book.id}/highlights", headers=a).json()
    assert [r["color"] for r in still] == ["yellow"]


def test_private_uploaded_book_is_unreachable_by_another_reader(client, db):
    owner = make_user(db)
    stranger = auth(make_user(db))
    book, ms = make_book(db, owner=owner)
    try:
        assert post(client, auth(owner), book, ms, 0, 5).status_code == 201
        assert post(client, stranger, book, ms, 0, 5).status_code == 404
        assert client.get(f"/books/{book.id}/highlights", headers=stranger).status_code == 404
    finally:
        drop_book(db, book.id)


def test_astral_characters_use_code_points(client, reader, db):
    text = "\U0001F600 Hello \U00020BB7 world"
    book, ms = make_book(db, text=text)
    try:
        body = post(client, reader, book, ms, 2, 7).json()
        assert body["quote"] == "Hello"
        assert body["context_before"] == "\U0001F600 "
        assert post(client, reader, book, ms, 8, 9).json()["quote"] == "\U00020BB7"
    finally:
        drop_book(db, book.id)


def test_highlights_disappear_with_a_deleted_upload(client, db):
    owner = make_user(db)
    book, ms = make_book(db, owner=owner)
    book_id = book.id
    assert post(client, auth(owner), book, ms, 0, 5).status_code == 201
    assert client.delete(f"/books/{book_id}", headers=auth(owner)).status_code == 204
    db.expire_all()
    assert db.query(Highlight).filter(Highlight.book_id == book_id).count() == 0


def test_highlight_events_are_accepted(client, reader):
    names = [
        "highlight_created",
        "highlight_edited",
        "highlight_deleted",
        "notes_opened",
        "notes_exported",
        "highlight_jump",
    ]
    events = [{"event_type": t, "book_id": None, "metadata": {"k": 1}} for t in names]
    resp = client.post("/events", json=events, headers=reader)
    assert resp.status_code == 201 and resp.json() == {"logged": 6}


def test_highlight_has_the_same_session_number_as_the_sessions_drawer(client, reader, shared, db):
    book, ms = shared
    ms2 = add_chapter(db, book, 2, "Second chapter text.")
    first = post(client, reader, book, ms, 0, 5).json()
    second = post(client, reader, book, ms2, 0, 6).json()
    assert (first["session_number"], second["session_number"]) == (1, 2)
    listed = client.get(f"/books/{book.id}/highlights", headers=reader).json()
    assert [r["session_number"] for r in listed] == [1, 2]
    patched = client.patch(f"/highlights/{second['id']}", json={"color": "blue"}, headers=reader).json()
    assert patched["session_number"] == 2


def test_reader_position_lists_the_micro_sessions_in_a_merged_block(client, db):
    from app.models import ReadingSession

    user = make_user(db)
    headers = auth(user)
    book, ms = make_book(db, text="Part one text here.")
    try:
        ms_b = MicroSession(index=2, text="Part two text here.", word_count=4)
        ms_c = MicroSession(index=3, text="Part three text.", word_count=3)
        chapter = db.get(Chapter, ms.chapter_id)
        chapter.micro_sessions.extend([ms_b, ms_c])
        db.commit()

        single = client.get(f"/books/{book.id}/reader", headers=headers).json()
        assert [p["id"] for p in single["micro_session"]["parts"]] == [ms.id]
        assert single["micro_session"]["parts"][0]["text"] == "Part one text here."

        for _ in range(5):  # five completed sessions graduate the reader to blocks of two
            db.add(
                ReadingSession(
                    user_id=user.id, book_id=book.id, chapter_id=chapter.id,
                    micro_session_id=ms.id, completed=True,
                )
            )
        db.commit()
        merged = client.get(f"/books/{book.id}/reader", headers=headers).json()["micro_session"]
        assert [p["id"] for p in merged["parts"]] == [ms.id, ms_b.id]
        assert merged["text"] == "\n\n".join(p["text"] for p in merged["parts"])
    finally:
        db.query(ReadingSession).filter(ReadingSession.user_id == user.id).delete()
        db.query(UserBookProgress).filter(UserBookProgress.book_id == book.id).delete()
        db.commit()
        drop_book(db, book.id)


def test_peeking_at_a_passage_does_not_move_the_saved_position(client, db):
    user = make_user(db)
    headers = auth(user)
    book, ms = make_book(db, text="Part one text here.")
    try:
        ms_b = add_chapter(db, book, 2, "Chapter two text.")
        before = client.get(f"/books/{book.id}/reader", headers=headers).json()
        assert before["micro_session"]["id"] == ms.id

        peek = client.get(f"/books/{book.id}/reader", params={"ms": ms_b.id}, headers=headers)
        assert peek.status_code == 200
        assert peek.json()["micro_session"]["id"] == ms_b.id
        assert peek.json()["micro_session"]["parts"][0]["id"] == ms_b.id

        after = client.get(f"/books/{book.id}/reader", headers=headers).json()
        assert after["micro_session"]["id"] == ms.id  # still where the reader left off
    finally:
        db.query(UserBookProgress).filter(UserBookProgress.book_id == book.id).delete()
        db.commit()
        drop_book(db, book.id)


def test_peek_rejects_a_passage_from_another_book(client, db):
    user = make_user(db)
    headers = auth(user)
    book, _ = make_book(db)
    other, other_ms = make_book(db, text="Different book.")
    try:
        resp = client.get(f"/books/{book.id}/reader", params={"ms": other_ms.id}, headers=headers)
        assert resp.status_code == 404
    finally:
        db.query(UserBookProgress).filter(UserBookProgress.book_id.in_([book.id, other.id])).delete()
        db.commit()
        drop_book(db, book.id)
        drop_book(db, other.id)


# --------------------------------------------------------------------------
# hardening (review minors)
# --------------------------------------------------------------------------


def test_whitespace_only_selection_is_422(client, reader, db):
    book, ms = make_book(db, text="ab     cd")
    try:
        assert post(client, reader, book, ms, 2, 7).status_code == 422
        assert post(client, reader, book, ms, 0, 2).status_code == 201
    finally:
        drop_book(db, book.id)


def test_blank_comment_is_stored_as_none(client, reader, shared):
    book, ms = shared
    created = post(client, reader, book, ms, 0, 5, comment="   ").json()
    assert created["comment"] is None
    hid = post(client, reader, book, ms, 13, 22, comment="keep").json()["id"]
    patched = client.patch(f"/highlights/{hid}", json={"comment": "  "}, headers=reader).json()
    assert patched["comment"] is None
    stripped = client.patch(f"/highlights/{hid}", json={"comment": "  hi  "}, headers=reader).json()
    assert stripped["comment"] == "hi"


def test_patch_with_null_colour_is_422(client, reader, shared):
    book, ms = shared
    hid = post(client, reader, book, ms, 0, 5).json()["id"]
    assert client.patch(f"/highlights/{hid}", json={"color": None}, headers=reader).status_code == 422


def test_concurrent_overlapping_creates_yield_exactly_one(client, shared, db):
    from concurrent.futures import ThreadPoolExecutor

    book, ms = shared
    headers = auth(make_user(db))

    def attempt(_):
        return post(client, headers, book, ms, 0, 5).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(attempt, range(6)))
    assert sorted(codes) == [201] + [409] * 5


def test_session_numbers_skip_front_matter_and_match_the_drawer_order(client, reader, db):
    book, ms = make_book(db, text="Story text one.")
    try:
        front = Chapter(book_id=book.id, index=0, title="Contents", text="toc", word_count=1, section_kind="front_matter")
        front.micro_sessions.append(MicroSession(index=0, text="Contents list.", word_count=2))
        db.add(front)
        db.commit()
        front_ms = front.micro_sessions[0]
        ms2 = add_chapter(db, book, 2, "Story text two.")
        # a highlight inside front matter has no reader-facing session number
        db.add(
            Highlight(
                user_id=db.query(User).order_by(User.id.desc()).first().id,
                book_id=book.id, micro_session_id=front_ms.id, start=0, end=8,
                quote="Contents", context_before="", context_after=" list.", color="blue",
            )
        )
        db.commit()
        a = post(client, reader, book, ms, 0, 5).json()
        b = post(client, reader, book, ms2, 0, 5).json()
        assert (a["session_number"], b["session_number"]) == (1, 2)
    finally:
        drop_book(db, book.id)
