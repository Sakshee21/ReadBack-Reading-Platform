"""GET /books/{id}/theme-map: where each theme sits across a book."""

import pytest

from app.models import MicroSession, MicroSessionTheme, UserBookProgress
from tests.test_themes_api import auth, client, set_position, tag  # noqa: F401
from tests.test_themes_service import db, drop_book, make_book, make_user  # noqa: F401

TEXTS = ("Lovers met.", "A murder.", "Ruin and debt.", "War broke out.")


@pytest.fixture()
def story(db):
    """Four tagged chunks; the reader is on chunk 2."""
    user = make_user(db)
    book, chunks = make_book(db, texts=TEXTS)
    tag(db, chunks[0], ("romance", 5), ("class_money", 2))
    tag(db, chunks[1], ("mystery_detection", 5), ("romance", 3))
    tag(db, chunks[2], ("class_money", 4))
    tag(db, chunks[3], ("war_conflict", 5), ("romance", 4))
    set_position(db, user, book, chunks[1])
    yield user, book, chunks
    drop_book(db, book.id)


def get_map(client, user, book, **params):
    return client.get(f"/books/{book.id}/theme-map", params=params, headers=auth(user))


def cells(body, theme):
    row = next((t for t in body["themes"] if t["theme"] == theme), None)
    return [(c["pos"], c["score"]) for c in row["cells"]] if row else None


def test_the_map_shows_only_reached_chunks_by_default(client, db, story):
    user, book, chunks = story
    body = get_map(client, user, book).json()
    assert body["reveal"] is False and body["total"] == 4
    assert cells(body, "romance") == [(0, 5), (1, 3)]  # chunk 4's romance is ahead of the reader
    assert cells(body, "war_conflict") is None
    assert cells(body, "class_money") is None  # chunk 1's class_money is score 2
    assert "War" not in get_map(client, user, book).text


def test_reveal_all_returns_the_whole_book_for_a_seeded_book(client, db, story):
    user, book, chunks = story
    body = get_map(client, user, book, reveal="all").json()
    assert body["reveal"] is True
    assert cells(body, "romance") == [(0, 5), (1, 3), (3, 4)]
    assert cells(body, "war_conflict") == [(3, 5)]
    assert cells(body, "class_money") == [(2, 4)]


def test_themes_are_ordered_by_how_often_they_appear_then_list_order(client, db, story):
    user, book, chunks = story
    body = get_map(client, user, book, reveal="all").json()
    order = [(t["theme"], t["count"]) for t in body["themes"]]
    assert order[0] == ("romance", 3)
    assert [c for _t, c in order] == sorted((c for _t, c in order), reverse=True)
    first = body["themes"][0]["cells"][0]
    assert set(first) == {"pos", "micro_session_id", "score"} and first["micro_session_id"] == chunks[0].id
    assert body["themes"][0]["label"] == "Romance & courtship"


def test_chapter_ranges_cover_every_position_once(client, db):
    user = make_user(db)
    book, (a, b) = make_book(db)
    from app.models import Chapter

    chapter2 = Chapter(index=2, title="Second", text="x y", word_count=2)
    chapter2.micro_sessions.append(MicroSession(index=1, text="Third.", word_count=1))
    book.chapters.append(chapter2)
    db.commit()
    try:
        body = get_map(client, user, book).json()
        assert body["total"] == 3
        assert [(c["index"], c["title"], c["start"], c["end"]) for c in body["chapters"]] == [
            (1, "Chapter One", 0, 1),
            (2, "Second", 2, 2),
        ]
    finally:
        drop_book(db, book.id)


def test_a_book_with_no_tags_still_has_chapters_and_an_empty_theme_list(client, db):
    user = make_user(db)
    book, _ = make_book(db)
    try:
        body = get_map(client, user, book, reveal="all").json()
        assert body["themes"] == [] and body["total"] == 2 and len(body["chapters"]) == 1
    finally:
        drop_book(db, book.id)


def test_retired_theme_ids_are_skipped(client, db, story):
    user, book, chunks = story
    db.add(MicroSessionTheme(micro_session_id=chunks[0].id, theme="retired_theme", score=5, source="llm"))
    db.commit()
    assert "retired_theme" not in get_map(client, user, book, reveal="all").text


def test_someone_elses_upload_is_not_found_even_with_reveal(client, db):
    owner, stranger = make_user(db), make_user(db)
    book, chunks = make_book(db, owner=owner, consent=True)
    try:
        tag(db, chunks[0], ("romance", 5))
        assert get_map(client, stranger, book, reveal="all").status_code == 404
        assert get_map(client, owner, book, reveal="all").status_code == 200
    finally:
        drop_book(db, book.id)


@pytest.mark.parametrize("value", ["yes", "ALL", "1", ""])
def test_any_reveal_value_other_than_all_is_rejected(client, db, story, value):
    user, book, _ = story
    assert get_map(client, user, book, reveal=value).status_code == 422


def test_the_map_requires_login(client, story):
    _, book, _ = story
    assert client.get(f"/books/{book.id}/theme-map").status_code in (401, 403)


def test_a_book_with_only_score_2_tags_maps_to_nothing(client, db):
    user = make_user(db)
    book, chunks = make_book(db)
    try:
        tag(db, chunks[0], ("romance", 2))
        body = get_map(client, user, book, reveal="all").json()
        assert body["themes"] == [] and body["total"] == 2
    finally:
        drop_book(db, book.id)


def test_a_second_reader_can_reveal_a_seeded_book_but_gets_nothing_extra_without_asking(client, db, story):
    _, book, chunks = story
    other = make_user(db)
    set_position(db, other, book, chunks[0])
    assert cells(get_map(client, other, book, reveal="all").json(), "war_conflict") == [(3, 5)]
    # asking again without reveal is limited again: nothing is remembered between requests
    assert cells(get_map(client, other, book).json(), "war_conflict") is None
    assert get_map(client, other, book).json()["reveal"] is False
