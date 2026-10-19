"""Theme routes: what a reader may see, consent, the upload flag, the export."""

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models import (
    Book,
    MicroSession,
    MicroSessionTagging,
    MicroSessionTheme,
    UserBookProgress,
)
from app.security import create_access_token
from app.services import themes
from tests.test_themes_service import db, drop_book, make_book, make_user  # noqa: F401


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def tag(db, ms, *pairs):
    reply = json.dumps({"themes": [{"theme": t, "score": s} for t, s in pairs]})
    assert themes.tag_chunk(db, ms, client=None, provider=lambda c, t: reply) == "done"


def set_position(db, user, book, ms):
    db.query(UserBookProgress).filter_by(user_id=user.id, book_id=book.id).delete()
    db.add(UserBookProgress(user_id=user.id, book_id=book.id, current_chapter_id=ms.chapter_id, current_micro_session_id=ms.id))
    db.commit()


@pytest.fixture()
def story(db):
    """A seeded-style book with four chunks, tagged, and a reader on chunk 2."""
    user = make_user(db)
    book, chunks = make_book(db, texts=("Lovers met at the ball.", "A murder at the manor.", "Ruin and debt.", "War broke out."))
    tag(db, chunks[0], ("romance", 5), ("class_money", 2))
    tag(db, chunks[1], ("mystery_detection", 5), ("romance", 3))
    tag(db, chunks[2], ("class_money", 4))
    tag(db, chunks[3], ("war_conflict", 5))
    set_position(db, user, book, chunks[1])
    yield user, book, chunks
    drop_book(db, book.id)


def test_themes_lists_only_reached_chunks_and_counts_score_3_plus(client, db, story):
    user, book, chunks = story
    body = client.get(f"/books/{book.id}/themes", headers=auth(user)).json()
    counts = {t["theme"]: t["count"] for t in body["themes"]}
    assert counts == {"romance": 2, "mystery_detection": 1}  # class_money 2 is below 3; later chunks hidden
    assert {t["theme"]: t["label"] for t in body["themes"]}["romance"] == "Romance & courtship"
    assert body["tagging"] == {"tagged": 2, "pending": 0, "failed": 0}


def test_a_later_chunk_never_appears_in_any_route(client, db, story):
    user, book, chunks = story
    h = auth(user)
    listing = client.get(f"/books/{book.id}/themes", headers=h).json()
    assert "war_conflict" not in {t["theme"] for t in listing["themes"]}
    assert listing["tagging"]["tagged"] == 2
    assert client.get(f"/books/{book.id}/themes/war_conflict", headers=h).json() == []
    assert client.get(f"/books/{book.id}/themes/class_money", headers=h).json() == []  # chunk 3 hidden, chunk 1 is score 2
    ids = {p["micro_session_id"] for p in client.get(f"/books/{book.id}/themes/romance", headers=h).json()}
    assert ids == {chunks[0].id, chunks[1].id}
    for path in (f"/books/{book.id}/themes", f"/books/{book.id}/themes/romance"):
        assert "Ruin" not in client.get(path, headers=h).text and "War broke" not in client.get(path, headers=h).text
    # a failed later chunk is not counted either
    db.get(MicroSessionTagging, chunks[3].id).status = "failed"
    db.commit()
    assert client.get(f"/books/{book.id}/themes", headers=h).json()["tagging"]["failed"] == 0


def test_passages_come_in_reading_order_with_preview_and_location(client, db, story):
    user, book, chunks = story
    rows = client.get(f"/books/{book.id}/themes/romance", headers=auth(user)).json()
    assert [r["micro_session_id"] for r in rows] == [chunks[0].id, chunks[1].id]
    first = rows[0]
    assert first["preview"].startswith("Lovers met") and len(first["preview"]) <= 160
    assert first["chapter_index"] == 1 and first["chapter_title"] == "Chapter One" and first["session_number"] == 1
    assert first["score"] == 5
    assert [t["theme"] for t in first["themes"]] == ["romance"]  # the score-2 theme is not shown
    assert {t["theme"] for t in rows[1]["themes"]} == {"mystery_detection", "romance"}


def test_moving_forward_reveals_more(client, db, story):
    user, book, chunks = story
    set_position(db, user, book, chunks[3])
    counts = {t["theme"]: t["count"] for t in client.get(f"/books/{book.id}/themes", headers=auth(user)).json()["themes"]}
    assert counts["war_conflict"] == 1 and counts["class_money"] == 1


def test_theme_route_422_for_unknown_theme(client, db, story):
    user, book, _ = story
    assert client.get(f"/books/{book.id}/themes/sadness", headers=auth(user)).status_code == 422


def test_requires_auth(client, story):
    _, book, _ = story
    assert client.get(f"/books/{book.id}/themes").status_code == 401
    assert client.get(f"/books/{book.id}/themes/romance").status_code == 401
    assert client.patch(f"/books/{book.id}/theme-consent", json={"granted": True}).status_code == 401


def test_other_readers_upload_is_404(client, db):
    owner, stranger = make_user(db), make_user(db)
    book, (a, _) = make_book(db, owner=owner, consent=True)
    try:
        tag(db, a, ("romance", 5))
        assert client.get(f"/books/{book.id}/themes", headers=auth(stranger)).status_code == 404
        assert client.get(f"/books/{book.id}/themes/romance", headers=auth(stranger)).status_code == 404
        assert client.patch(f"/books/{book.id}/theme-consent", json={"granted": False}, headers=auth(stranger)).status_code == 404
        assert client.get(f"/books/{book.id}/themes", headers=auth(owner)).status_code == 200
    finally:
        drop_book(db, book.id)


def test_consent_toggle_owner_only_and_seeded_403(client, db):
    owner = make_user(db)
    upload, _ = make_book(db, owner=owner)
    seeded, _ = make_book(db)
    try:
        assert client.patch(f"/books/{upload.id}/theme-consent", json={"granted": True}, headers=auth(owner)).json() == {"theme_tagging_consent": True}
        db.expire_all()
        fresh = db.get(Book, upload.id)
        assert fresh.theme_tagging_consent is True and fresh.theme_tagging_consent_at is not None
        assert client.patch(f"/books/{seeded.id}/theme-consent", json={"granted": True}, headers=auth(owner)).status_code == 403
        assert client.patch(f"/books/{upload.id}/theme-consent", json={"granted": "yes please"}, headers=auth(owner)).status_code == 422
    finally:
        drop_book(db, upload.id)
        drop_book(db, seeded.id)


def test_withdrawing_consent_deletes_tags_and_status(client, db):
    owner = make_user(db)
    book, (a, b) = make_book(db, owner=owner, consent=True)
    try:
        tag(db, a, ("romance", 5))
        db.add(MicroSessionTagging(micro_session_id=b.id, status="pending"))
        db.commit()
        resp = client.patch(f"/books/{book.id}/theme-consent", json={"granted": False}, headers=auth(owner))
        assert resp.json() == {"theme_tagging_consent": False}
        db.expire_all()
        assert db.query(MicroSessionTheme).filter_by(micro_session_id=a.id).count() == 0
        assert db.get(MicroSessionTagging, a.id) is None and db.get(MicroSessionTagging, b.id) is None
        fresh = db.get(Book, book.id)
        assert fresh.theme_tagging_consent is False and fresh.theme_tagging_consent_at is None
    finally:
        drop_book(db, book.id)


def test_book_out_exposes_the_consent_flag(client, db):
    owner = make_user(db)
    book, _ = make_book(db, owner=owner, consent=True)
    try:
        books = client.get("/books", headers=auth(owner)).json()
        mine = next(b for b in books if b["id"] == book.id)
        assert mine["theme_tagging_consent"] is True
        assert all(b["theme_tagging_consent"] is False for b in books if b["id"] != book.id)
    finally:
        drop_book(db, book.id)


def test_upload_with_and_without_consent_flag(client, db):
    owner = make_user(db)
    text = ("Chapter 1\n\n" + "It was a quiet morning in the village and nothing stirred. " * 40) * 3
    made = []
    try:
        for flag in (None, "true"):
            data = {"title": "Consent test"}
            if flag:
                data["theme_tagging_consent"] = flag
            resp = client.post("/books/upload", files={"file": ("book.txt", text.encode(), "text/plain")}, data=data, headers=auth(owner))
            assert resp.status_code == 202, resp.text
            made.append(resp.json()["id"])
        db.expire_all()
        assert [db.get(Book, i).theme_tagging_consent for i in made] == [False, True]
        assert db.get(Book, made[1]).theme_tagging_consent_at is not None
        assert db.get(Book, made[0]).theme_tagging_consent_at is None
    finally:
        for i in made:
            client.delete(f"/books/{i}", headers=auth(owner))


def export_rows(client):
    resp = client.get("/admin/export/themes.csv", params={"token": settings.admin_token})
    assert resp.status_code == 200
    return list(csv.DictReader(io.StringIO(resp.text))), resp


def test_export_has_columns_and_excludes_uploads_and_low_scores(client, db, story):
    user, book, chunks = story
    owner = make_user(db)
    upload, (u, _) = make_book(db, owner=owner, consent=True)
    try:
        tag(db, u, ("romance", 5))
        rows, resp = export_rows(client)
        assert resp.headers["content-type"].startswith("text/csv")
        assert list(rows[0]) == [
            "book_id", "book_title", "chapter_index", "micro_session_id", "theme", "score",
            "source", "model", "prompt_version", "theme_list_version",
        ]
        mine = [r for r in rows if int(r["book_id"]) == book.id]
        assert {(r["theme"], int(r["score"])) for r in mine} == {
            ("romance", 5), ("mystery_detection", 5), ("romance", 3), ("class_money", 4), ("war_conflict", 5),
        }
        assert not [r for r in rows if int(r["book_id"]) == upload.id]
        assert all(int(r["score"]) >= themes.MIN_SHOWN_SCORE for r in rows)
        assert {r["source"] for r in mine} == {"llm"} and {r["theme_list_version"] for r in mine} == {"1"}
    finally:
        drop_book(db, upload.id)


def test_export_requires_admin_token(client):
    assert client.get("/admin/export/themes.csv").status_code == 422
    assert client.get("/admin/export/themes.csv", params={"token": "wrong"}).status_code == 403


def test_uploaded_book_tags_not_visible_to_another_reader_via_the_list(client, db):
    owner, other = make_user(db), make_user(db)
    book, (a, _) = make_book(db, owner=owner, consent=True)
    try:
        tag(db, a, ("romance", 5))
        assert client.get(f"/books/{book.id}/themes", headers=auth(owner)).json()["themes"] == [
            {"theme": "romance", "label": "Romance & courtship", "count": 1}
        ]
        assert client.get(f"/books/{book.id}/themes", headers=auth(other)).status_code == 404
    finally:
        drop_book(db, book.id)


# --------------------------------------------------------------------------
# tags for the passage being read
# --------------------------------------------------------------------------


def passage_themes(client, user, book, ms):
    return client.get(f"/books/{book.id}/passage-themes", params={"ms": ms.id}, headers=auth(user))


def test_passage_themes_returns_the_current_passage_best_first_and_score_3_plus(client, db, story):
    user, book, chunks = story
    body = passage_themes(client, user, book, chunks[1]).json()
    assert [(t["theme"], t["score"]) for t in body["themes"]] == [("mystery_detection", 5), ("romance", 3)]
    assert body["themes"][0]["label"] == "Mystery & detection"
    assert body["preparing"] is False
    first = passage_themes(client, user, book, chunks[0]).json()
    assert [t["theme"] for t in first["themes"]] == ["romance"]  # class_money 2 is below the cut


def test_passage_themes_never_reveals_a_chunk_the_reader_has_not_reached(client, db, story):
    user, book, chunks = story
    body = passage_themes(client, user, book, chunks[3]).json()  # reader is on chunk 2
    assert body == {"themes": [], "preparing": False}
    assert "war_conflict" not in passage_themes(client, user, book, chunks[2]).text


def test_passage_themes_rejects_a_chunk_of_another_book_and_other_readers(client, db, story):
    user, book, chunks = story
    other_book, other_chunks = make_book(db)
    stranger = make_user(db)
    try:
        assert passage_themes(client, user, book, other_chunks[0]).status_code == 422
        assert passage_themes(client, stranger, other_book, other_chunks[0]).status_code in (200, 404)
        owner = make_user(db)
        up, up_chunks = make_book(db, owner=owner, consent=True)
        try:
            assert passage_themes(client, stranger, up, up_chunks[0]).status_code == 404
        finally:
            drop_book(db, up.id)
    finally:
        drop_book(db, other_book.id)


def test_passage_themes_requires_auth(client, story):
    _, book, chunks = story
    assert client.get(f"/books/{book.id}/passage-themes", params={"ms": chunks[0].id}).status_code in (401, 403)


def test_passage_themes_says_preparing_only_for_a_consented_upload_still_being_tagged(client, db):
    owner = make_user(db)
    book, chunks = make_book(db, owner=owner, consent=True)
    seeded, seeded_chunks = make_book(db)
    try:
        set_position(db, owner, book, chunks[0])
        assert passage_themes(client, owner, book, chunks[0]).json() == {"themes": [], "preparing": True}
        tag(db, chunks[0], ("romance", 4))
        assert passage_themes(client, owner, book, chunks[0]).json()["preparing"] is False
        set_position(db, owner, seeded, seeded_chunks[0])
        assert passage_themes(client, owner, seeded, seeded_chunks[0]).json()["preparing"] is False  # untagged seeded: nothing to wait for
    finally:
        drop_book(db, book.id)
        drop_book(db, seeded.id)


def test_a_stored_tag_whose_theme_is_no_longer_in_the_list_never_breaks_a_page(client, db, story):
    user, book, chunks = story
    db.add(MicroSessionTheme(micro_session_id=chunks[1].id, theme="retired_theme", score=5, source="llm"))
    db.commit()
    h = auth(user)
    listing = client.get(f"/books/{book.id}/themes", headers=h)
    assert listing.status_code == 200 and "retired_theme" not in listing.text
    assert client.get(f"/books/{book.id}/themes/mystery_detection", headers=h).status_code == 200
    body = passage_themes(client, user, book, chunks[1])
    assert body.status_code == 200 and "retired_theme" not in body.text
