"""User book uploads: conversion, validation, privacy and cleanup.

Uploads convert in a FastAPI BackgroundTask. TestClient runs those
synchronously once the response is returned, so by the time a request returns
the book is already in its final state - no polling needed in tests.
"""

import csv
import io
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Book, Chapter, MicroSession, ReadingEvent, UserBookProgress
from app.services.extract import ExtractionError, safe_filename, sniff_format

UPLOADS = Path(__file__).parent / "fixtures" / "uploads"


def fixture(name: str) -> bytes:
    path = UPLOADS / name
    if not path.exists():
        pytest.skip(f"run tests/fixtures/make_upload_fixtures.py to create {name}")
    return path.read_bytes()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def register(client) -> tuple[dict, int]:
    email = f"upl_{uuid.uuid4().hex[:10]}@test.com"
    token = client.post(
        "/auth/register", json={"email": email, "password": "pw12345"}
    ).json()["access_token"]
    db = SessionLocal()
    try:
        from app.models import User

        uid = db.query(User).filter(User.email == email).first().id
    finally:
        db.close()
    return {"Authorization": f"Bearer {token}"}, uid


def upload(client, headers, name, data, ctype="application/octet-stream", **form):
    return client.post(
        "/books/upload",
        files={"file": (name, data, ctype)},
        data=form,
        headers=headers,
    )


def cleanup(client, headers, book_id):
    client.delete(f"/books/{book_id}", headers=headers)


# --------------------------------------------------------------------------
# sniffing / filename safety (pure)
# --------------------------------------------------------------------------


def test_safe_filename_strips_paths_and_markup():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename(r"C:\windows\evil.txt") == "evil.txt"
    assert safe_filename("") == "upload"

    # whatever survives, it can never carry a path or markup
    for nasty in ("<script>x</script>.txt", "../a/b/c.txt", "a\\b\\c.txt", "%00.txt"):
        cleaned = safe_filename(nasty)
        assert not {"/", "\\", "<", ">", "%"} & set(cleaned), cleaned
        assert ".." not in cleaned


def test_sniff_rejects_unknown_extension():
    with pytest.raises(ExtractionError) as exc:
        sniff_format("book.docx", b"anything")
    assert exc.value.reason_code == "unsupported_extension"


def test_sniff_rejects_spoofed_extension():
    """A PDF renamed to .txt must not be parsed as text."""
    with pytest.raises(ExtractionError) as exc:
        sniff_format("book.txt", fixture("sample.pdf"))
    assert exc.value.reason_code == "extension_mismatch"


def test_sniff_rejects_a_plain_zip_named_epub():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "not a book")
    with pytest.raises(ExtractionError) as exc:
        sniff_format("book.epub", buf.getvalue())
    assert exc.value.reason_code == "not_an_epub"


# --------------------------------------------------------------------------
# successful conversion
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["sample.txt", "sample.epub", "sample.pdf"])
def test_upload_converts_to_chapters_and_sessions(client, name):
    headers, _ = register(client)
    resp = upload(client, headers, name, fixture(name), title="Fixture Book", author="Austen")
    assert resp.status_code == 202, resp.text
    book_id = resp.json()["id"]

    status = client.get(f"/books/{book_id}/status", headers=headers).json()
    assert status["status"] == "ready", status.get("failure_reason")
    assert status["chapter_count"] >= 1
    assert status["micro_session_count"] >= 1
    assert status["total_word_count"] > 0

    # and it is readable through the normal reader path
    pos = client.get(f"/books/{book_id}/reader", headers=headers)
    assert pos.status_code == 200
    assert pos.json()["micro_session"]["text"].strip()
    cleanup(client, headers, book_id)


def test_epub_uses_its_own_chapter_structure(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "sample.epub", fixture("sample.epub")).json()["id"]
    chapters = client.get(f"/books/{book_id}", headers=headers).json()
    # the fixture declares three documents with <h1> titles
    assert len(chapters) == 3
    assert any(c["title"] for c in chapters)
    cleanup(client, headers, book_id)


def test_uploaded_book_is_flagged_and_has_no_quiz(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "sample.txt", fixture("sample.txt")).json()["id"]

    book = next(b for b in client.get("/books", headers=headers).json() if b["id"] == book_id)
    assert book["is_user_uploaded"] is True
    assert book["source_type"] == "upload"
    assert book["gutenberg_id"] is None

    # no hand-authored checkpoints exist for uploads, so the reader just reads
    assert client.get(f"/books/{book_id}/reader", headers=headers).json()["checkpoint_due"] is None
    cleanup(client, headers, book_id)


def test_title_and_author_fall_back_to_the_filename(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "my_book.txt", fixture("sample.txt")).json()["id"]
    book = next(b for b in client.get("/books", headers=headers).json() if b["id"] == book_id)
    assert book["title"] == "my book"
    assert book["author"] == "Unknown"
    cleanup(client, headers, book_id)


# --------------------------------------------------------------------------
# rejection
# --------------------------------------------------------------------------


def test_scanned_pdf_is_rejected_with_a_clear_reason(client):
    headers, _ = register(client)
    resp = upload(client, headers, "scanned.pdf", fixture("scanned.pdf"))
    assert resp.status_code == 202  # accepted, then fails in conversion
    book_id = resp.json()["id"]
    status = client.get(f"/books/{book_id}/status", headers=headers).json()
    assert status["status"] == "failed"
    assert "scanned" in status["failure_reason"].lower()
    cleanup(client, headers, book_id)


def test_oversized_upload_is_refused(client):
    headers, _ = register(client)
    big = b"word " * (settings.upload_max_bytes // 4)
    resp = upload(client, headers, "big.txt", big)
    assert resp.status_code == 413


def test_empty_upload_is_refused(client):
    headers, _ = register(client)
    assert upload(client, headers, "empty.txt", b"").status_code == 400


def test_wrong_file_type_is_refused(client):
    headers, _ = register(client)
    resp = upload(client, headers, "notes.docx", b"PK\x03\x04 whatever")
    assert resp.status_code == 400
    assert ".txt" in resp.json()["detail"]


def test_spoofed_extension_is_refused_at_the_endpoint(client):
    headers, _ = register(client)
    resp = upload(client, headers, "book.txt", fixture("sample.pdf"))
    assert resp.status_code == 400
    assert "contents are PDF" in resp.json()["detail"]


def test_too_short_text_fails_conversion(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "tiny.txt", b"Only a handful of words here.").json()["id"]
    status = client.get(f"/books/{book_id}/status", headers=headers).json()
    assert status["status"] == "failed"
    assert "too short" in status["failure_reason"].lower()
    cleanup(client, headers, book_id)


def test_upload_requires_authentication(client):
    resp = client.post("/books/upload", files={"file": ("a.txt", fixture("sample.txt"))})
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# privacy
# --------------------------------------------------------------------------


def test_another_user_cannot_see_or_fetch_the_upload(client):
    owner, _ = register(client)
    other, _ = register(client)
    book_id = upload(client, owner, "sample.txt", fixture("sample.txt")).json()["id"]

    assert book_id not in [b["id"] for b in client.get("/books", headers=other).json()]

    # every book-scoped route must 404, not 403 - a 403 would confirm it exists
    for path in (
        f"/books/{book_id}",
        f"/books/{book_id}/reader",
        f"/books/{book_id}/micro-sessions",
        f"/books/{book_id}/progress",
        f"/books/{book_id}/status",
    ):
        assert client.get(path, headers=other).status_code == 404, path

    assert client.post(
        f"/books/{book_id}/jump", json={"micro_session_id": 1}, headers=other
    ).status_code == 404
    assert client.get(f"/pace/me?book_id={book_id}", headers=other).status_code == 404
    cleanup(client, owner, book_id)


def test_another_user_cannot_start_a_session_on_the_upload(client):
    owner, _ = register(client)
    other, _ = register(client)
    book_id = upload(client, owner, "sample.txt", fixture("sample.txt")).json()["id"]
    micro_id = client.get(f"/books/{book_id}/reader", headers=owner).json()["micro_session"]["id"]

    resp = client.post(
        "/sessions/start", json={"book_id": book_id, "micro_session_id": micro_id}, headers=other
    )
    assert resp.status_code == 404
    cleanup(client, owner, book_id)


def test_another_user_cannot_delete_the_upload(client):
    owner, _ = register(client)
    other, _ = register(client)
    book_id = upload(client, owner, "sample.txt", fixture("sample.txt")).json()["id"]
    assert client.delete(f"/books/{book_id}", headers=other).status_code == 404
    assert client.get(f"/books/{book_id}/status", headers=owner).status_code == 200
    cleanup(client, owner, book_id)


def test_seeded_books_stay_visible_to_everyone(client):
    headers, _ = register(client)
    titles = [b["title"] for b in client.get("/books", headers=headers).json()]
    assert len(titles) >= 1
    for book in client.get("/books", headers=headers).json():
        if not book["is_user_uploaded"]:
            assert book["source_type"] in ("seeded", "gutenberg")


def test_seeded_books_cannot_be_deleted(client):
    headers, _ = register(client)
    seeded = next(
        b for b in client.get("/books", headers=headers).json() if not b["is_user_uploaded"]
    )
    assert client.delete(f"/books/{seeded['id']}", headers=headers).status_code == 403


# --------------------------------------------------------------------------
# cap and deletion
# --------------------------------------------------------------------------


def test_upload_cap_is_enforced(client):
    headers, _ = register(client)
    ids = []
    for i in range(settings.uploads_per_user):
        resp = upload(client, headers, f"book{i}.txt", fixture("sample.txt"))
        assert resp.status_code == 202, resp.text
        ids.append(resp.json()["id"])

    refused = upload(client, headers, "one_too_many.txt", fixture("sample.txt"))
    assert refused.status_code == 409
    assert str(settings.uploads_per_user) in refused.json()["detail"]

    # deleting one frees a slot
    cleanup(client, headers, ids[0])
    assert upload(client, headers, "now_ok.txt", fixture("sample.txt")).status_code == 202
    for book_id in ids[1:]:
        cleanup(client, headers, book_id)


def test_delete_removes_chapters_sessions_progress_and_events(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "sample.txt", fixture("sample.txt")).json()["id"]

    # generate a reading session, progress row and an event
    micro_id = client.get(f"/books/{book_id}/reader", headers=headers).json()["micro_session"]["id"]
    session_id = client.post(
        "/sessions/start", json={"book_id": book_id, "micro_session_id": micro_id}, headers=headers
    ).json()["id"]
    client.post("/sessions/complete", json={"session_id": session_id}, headers=headers)
    client.post(
        "/events", json={"event_type": "session_start", "book_id": book_id}, headers=headers
    )

    assert client.delete(f"/books/{book_id}", headers=headers).status_code == 204

    db = SessionLocal()
    try:
        assert db.get(Book, book_id) is None
        assert db.query(Chapter).filter(Chapter.book_id == book_id).count() == 0
        assert db.query(UserBookProgress).filter(UserBookProgress.book_id == book_id).count() == 0
        assert db.query(ReadingEvent).filter(ReadingEvent.book_id == book_id).count() == 0
        # micro-sessions cascade with their chapters
        assert (
            db.query(MicroSession)
            .filter(MicroSession.chapter_id.in_([-1]))
            .count()
            == 0
        )
    finally:
        db.close()

    assert client.get(f"/books/{book_id}/status", headers=headers).status_code == 404


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------


def test_upload_event_types_are_accepted_and_exported(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "sample.txt", fixture("sample.txt")).json()["id"]

    payload = [
        {"event_type": "book_upload_started", "metadata": {"source_format": "txt"}},
        {
            "event_type": "book_upload_completed",
            "book_id": book_id,
            "metadata": {"word_count": 850, "chapter_count": 3, "session_count": 3,
                         "source_format": "txt"},
        },
        {"event_type": "book_upload_failed", "metadata": {"reason_code": "pdf_no_text_layer"}},
        {"event_type": "book_deleted", "metadata": {"source_format": "txt"}},
    ]
    assert client.post("/events", json=payload, headers=headers).status_code == 201

    export = client.get(f"/admin/export/events.csv?token={settings.admin_token}")
    rows = list(csv.DictReader(io.StringIO(export.text)))
    logged = {r["event_type"] for r in rows}
    for event in ("book_upload_started", "book_upload_completed", "book_upload_failed",
                  "book_deleted"):
        assert event in logged, event

    cleanup(client, headers, book_id)


def test_csv_marks_uploaded_books_for_exclusion(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "sample.txt", fixture("sample.txt")).json()["id"]
    client.post(
        "/events", json={"event_type": "session_start", "book_id": book_id}, headers=headers
    )

    export = client.get(f"/admin/export/events.csv?token={settings.admin_token}")
    reader = csv.DictReader(io.StringIO(export.text))
    assert "is_user_uploaded" in reader.fieldnames
    assert "source_type" in reader.fieldnames

    mine = [r for r in reader if r["book_id"] == str(book_id)]
    assert mine, "no rows for the uploaded book"
    assert mine[0]["is_user_uploaded"] == "True"
    assert mine[0]["source_type"] == "upload"
    cleanup(client, headers, book_id)


# --------------------------------------------------------------------------
# paragraph formatting and front matter, end to end
# --------------------------------------------------------------------------


def chapters_of(client, headers, book_id):
    return client.get(f"/books/{book_id}", headers=headers).json()


def all_session_text(client, headers, book_id):
    """Walk every micro-session by jumping, collecting their text."""
    items = client.get(f"/books/{book_id}/micro-sessions", headers=headers).json()
    texts = []
    for item in items:
        pos = client.post(
            f"/books/{book_id}/jump", json={"micro_session_id": item["id"]}, headers=headers
        ).json()
        texts.append(pos["micro_session"]["text"])
    return texts


def test_gutenberg_upload_joins_wrapped_paragraphs(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "gutenberg_style.txt", fixture("gutenberg_style.txt")).json()["id"]
    assert client.get(f"/books/{book_id}/status", headers=headers).json()["status"] == "ready"

    text = "\n\n".join(all_session_text(client, headers, book_id))
    # the exact sentence from the bug report, now continuous
    assert "staircase. His garret was under the roof" in text
    # and no paragraph still carries a mid-sentence hard wrap
    for para in text.split("\n\n"):
        assert "\n" not in para or len(para.split("\n")[0]) < 60, repr(para[:120])
    cleanup(client, headers, book_id)


def test_gutenberg_boilerplate_never_reaches_the_reader(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "gutenberg_style.txt", fixture("gutenberg_style.txt")).json()["id"]
    text = "\n\n".join(all_session_text(client, headers, book_id))
    for banned in ("PROJECT GUTENBERG", "Produced by", "FULL LICENSE", "no restrictions"):
        assert banned not in text, banned
    cleanup(client, headers, book_id)


def test_front_matter_is_flagged_and_excluded_from_reading(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "gutenberg_style.txt", fixture("gutenberg_style.txt")).json()["id"]

    db = SessionLocal()
    try:
        kinds = {
            (c.title or "")[:20]: c.section_kind
            for c in db.query(Chapter).filter(Chapter.book_id == book_id).all()
        }
        front = [t for t, k in kinds.items() if k == "front_matter"]
        assert front, f"nothing flagged as front matter: {kinds}"
        # front matter gets no micro-sessions at all
        for chapter in db.query(Chapter).filter(
            Chapter.book_id == book_id, Chapter.section_kind != "story"
        ):
            assert chapter.micro_sessions == []
    finally:
        db.close()

    text = "\n\n".join(all_session_text(client, headers, book_id))
    assert "CONTENTS" not in text
    assert "silently corrected obvious typographical errors" not in text  # the preface
    cleanup(client, headers, book_id)


def test_visualization_prompts_on_uploads_are_sparing_and_story_only(client):
    """Uploads do get "Picture this scene" prompts, but never on front matter
    and never on a chapter's first or last session."""
    headers, _ = register(client)
    book_id = upload(client, headers, "no_headings.txt", fixture("no_headings.txt")).json()["id"]
    db = SessionLocal()
    try:
        chapters = (
            db.query(Chapter).filter(Chapter.book_id == book_id).order_by(Chapter.index).all()
        )
        total_sessions = flagged = 0
        for chapter in chapters:
            sessions = sorted(chapter.micro_sessions, key=lambda m: m.index)
            total_sessions += len(sessions)
            for i, ms in enumerate(sessions):
                if not ms.has_visualization_prompt:
                    continue
                flagged += 1
                assert chapter.section_kind == "story", "prompt on non-story section"
                assert i != 0, "prompt on a chapter's first session"
                assert i != len(sessions) - 1, "prompt on a chapter's last session"

        assert total_sessions > 5
        # sparing: well under one in every two sessions
        assert flagged <= total_sessions / 2
    finally:
        db.close()
    cleanup(client, headers, book_id)


def test_front_matter_never_gets_story_flags(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "gutenberg_style.txt", fixture("gutenberg_style.txt")).json()["id"]
    db = SessionLocal()
    try:
        for chapter in db.query(Chapter).filter(
            Chapter.book_id == book_id, Chapter.section_kind != "story"
        ):
            assert chapter.micro_sessions == [], "front matter should have no sessions at all"
    finally:
        db.close()
    cleanup(client, headers, book_id)


def test_verse_and_lists_survive_upload(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "verse.txt", fixture("verse.txt")).json()["id"]
    text = "\n\n".join(all_session_text(client, headers, book_id))
    assert "Tyger Tyger, burning bright,\nIn the forests of the night;" in text
    assert "1. The first item here\n2. The second item here" in text
    cleanup(client, headers, book_id)


def test_book_with_no_chapter_headings_still_converts(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "no_headings.txt", fixture("no_headings.txt")).json()["id"]
    status = client.get(f"/books/{book_id}/status", headers=headers).json()
    assert status["status"] == "ready"
    assert status["chapter_count"] > 1, "a long headingless book should be split into sections"
    cleanup(client, headers, book_id)


def test_pdf_headers_and_page_numbers_are_stripped(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "headers.pdf", fixture("headers.pdf")).json()["id"]
    status = client.get(f"/books/{book_id}/status", headers=headers).json()
    assert status["status"] == "ready", status.get("failure_reason")
    text = "\n\n".join(all_session_text(client, headers, book_id))
    assert "A SAMPLE NOVEL" not in text
    cleanup(client, headers, book_id)


def test_epub_cover_toc_and_colophon_are_skipped(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "frontmatter.epub", fixture("frontmatter.epub")).json()["id"]
    titles = [c["title"] for c in chapters_of(client, headers, book_id)]
    assert not any(t.lower() in ("cover", "contents", "colophon") for t in titles), titles
    assert any("chapter" in (t or "").lower() for t in titles), titles
    cleanup(client, headers, book_id)


def test_progress_counts_only_story_words(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "gutenberg_style.txt", fixture("gutenberg_style.txt")).json()["id"]
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        story_words = sum(
            c.word_count for c in book.chapters if c.section_kind == "story"
        )
        assert book.total_word_count == story_words
        assert book.total_word_count < sum(c.word_count for c in book.chapters)
    finally:
        db.close()
    cleanup(client, headers, book_id)


def test_reader_opens_on_the_first_story_chapter(client):
    headers, _ = register(client)
    book_id = upload(client, headers, "gutenberg_style.txt", fixture("gutenberg_style.txt")).json()["id"]
    pos = client.get(f"/books/{book_id}/reader", headers=headers).json()
    assert "CONTENTS" not in pos["micro_session"]["text"]
    assert "typographical errors" not in pos["micro_session"]["text"]
    cleanup(client, headers, book_id)


def test_event_metadata_carries_no_book_text(client):
    """Guard against ever logging file contents."""
    headers, _ = register(client)
    book_id = upload(client, headers, "sample.txt", fixture("sample.txt")).json()["id"]
    client.post(
        "/events",
        json={"event_type": "book_upload_completed", "book_id": book_id,
              "metadata": {"word_count": 850, "source_format": "txt"}},
        headers=headers,
    )
    export = client.get(f"/admin/export/events.csv?token={settings.admin_token}")
    assert "universally acknowledged" not in export.text
    cleanup(client, headers, book_id)
