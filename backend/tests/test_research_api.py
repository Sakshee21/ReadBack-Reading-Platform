"""The research track end to end: upload, read, privacy, isolation, tagging.

Conversion runs in a FastAPI BackgroundTask, which TestClient executes before
the response is handed back, so a document is already in its final state when
the upload call returns - no polling needed here.

The isolation tests are the point of this file. A research document must not
be reachable from any reading-habit endpoint, must not emit pilot events, and
must not appear in the pilot CSV.
"""

import csv
import io
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Book, MicroSession, ResearchTag, ResearchTagging, SectionKeyPoints
from app.services import research_tags

RESEARCH_FIXTURES = Path(__file__).parent / "fixtures" / "research"
UPLOAD_FIXTURES = Path(__file__).parent / "fixtures" / "uploads"


def fixture(path: Path) -> bytes:
    if not path.exists():
        pytest.skip(f"run tests/fixtures/make_research_fixtures.py to create {path.name}")
    return path.read_bytes()


PAPER = RESEARCH_FIXTURES / "twocol_interleaved.pdf"
TEXTBOOK = RESEARCH_FIXTURES / "textbook_outline.pdf"
SCANNED = UPLOAD_FIXTURES / "scanned.pdf"
EPUB = UPLOAD_FIXTURES / "sample.epub"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class FakeHttpClient:
    """Stands in for the httpx client. The provider call is faked too, so
    nothing is ever sent anywhere; this only has to be closeable."""

    def close(self) -> None:
        pass


def register(client) -> dict:
    email = f"res_{uuid.uuid4().hex[:10]}@test.com"
    token = client.post(
        "/auth/register", json={"email": email, "password": "pw12345"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner(client):
    return register(client)


def upload(client, headers, path: Path, name: str | None = None, **form):
    return client.post(
        "/research/upload",
        files={"file": (name or path.name, fixture(path), "application/pdf")},
        data=form,
        headers=headers,
    )


@pytest.fixture
def paper(client, owner):
    """A converted paper, cleaned up afterwards."""
    response = upload(client, owner, PAPER, title="Attention Scaffolding")
    assert response.status_code == 202, response.text
    document_id = response.json()["id"]
    yield document_id
    client.delete(f"/research/{document_id}", headers=owner)


# ---------------------------------------------------------------------------
# upload and conversion
# ---------------------------------------------------------------------------


def test_upload_converts_a_paper_into_sections(client, owner, paper):
    detail = client.get(f"/research/{paper}", headers=owner).json()
    assert detail["status"] == "ready", detail.get("failure_reason")
    assert detail["doc_kind"] == "paper"
    assert detail["page_count"] == 4
    assert detail["word_count"] > 500

    kinds = [s["kind"] for s in detail["sections"]]
    assert "abstract" in kinds
    assert "references" in kinds
    assert kinds.count("body") >= 5


def test_reference_and_title_sections_are_not_in_the_reading_flow(client, owner, paper):
    detail = client.get(f"/research/{paper}", headers=owner).json()
    for section in detail["sections"]:
        if section["kind"] in ("references", "front_matter"):
            assert section["readable"] is False
            assert section["chunk_count"] == 0
        else:
            assert section["readable"] is True


def test_warnings_are_surfaced_to_the_uploader(client, owner, paper):
    detail = client.get(f"/research/{paper}", headers=owner).json()
    joined = " ".join(detail["warnings"])
    assert "multi-column" in joined
    assert any("Fig. 1." in c for c in detail["captions"])


def test_uploaded_metadata_beats_the_document(client, owner):
    response = upload(
        client,
        owner,
        PAPER,
        title="My Corrected Title",
        authors="Someone Else",
        year=1999,
        venue="A Venue I Typed",
    )
    document_id = response.json()["id"]
    try:
        detail = client.get(f"/research/{document_id}", headers=owner).json()
        assert detail["title"] == "My Corrected Title"
        assert detail["authors"] == "Someone Else"
        assert detail["year"] == 1999
        assert detail["venue"] == "A Venue I Typed"
        # Not supplied, so it comes from the document.
        assert detail["doi"] == "10.1109/TLT.2021.1234567"
    finally:
        client.delete(f"/research/{document_id}", headers=owner)


def test_metadata_can_be_corrected_afterwards(client, owner, paper):
    response = client.patch(
        f"/research/{paper}", json={"year": 2020, "doi": "10.1000/corrected"}, headers=owner
    )
    assert response.status_code == 200
    body = response.json()
    assert body["year"] == 2020
    assert body["doi"] == "10.1000/corrected"
    # Fields not sent are untouched.
    assert body["title"] == "Attention Scaffolding"


def test_blank_metadata_is_stored_as_null_not_a_guess(client, owner):
    response = upload(client, owner, TEXTBOOK)
    document_id = response.json()["id"]
    try:
        detail = client.get(f"/research/{document_id}", headers=owner).json()
        assert detail["doc_kind"] == "textbook"
        assert detail["year"] is None
        assert detail["venue"] is None
        assert detail["doi"] is None
    finally:
        client.delete(f"/research/{document_id}", headers=owner)


def test_textbook_sections_come_from_the_outline(client, owner):
    response = upload(client, owner, TEXTBOOK)
    document_id = response.json()["id"]
    try:
        detail = client.get(f"/research/{document_id}", headers=owner).json()
        titles = [s["title"] for s in detail["sections"]]
        assert titles == [
            "Chapter 1. Foundations of Attention",
            "Chapter 2. Reading and Working Memory",
            "Chapter 3. Measuring Engagement",
        ]
        assert all(s["chunk_count"] >= 1 for s in detail["sections"])
    finally:
        client.delete(f"/research/{document_id}", headers=owner)


def test_a_scanned_pdf_fails_with_a_reason(client, owner):
    response = upload(client, owner, SCANNED)
    document_id = response.json()["id"]
    detail = client.get(f"/research/{document_id}", headers=owner).json()
    assert detail["status"] == "failed"
    assert "scanned" in detail["failure_reason"].lower()
    client.delete(f"/research/{document_id}", headers=owner)


def test_a_spoofed_pdf_is_refused_before_conversion(client, owner):
    """An EPUB renamed .pdf must be rejected on its bytes, not parsed."""
    response = client.post(
        "/research/upload",
        files={"file": ("paper.pdf", fixture(EPUB), "application/pdf")},
        headers=owner,
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_an_empty_file_is_refused(client, owner):
    response = client.post(
        "/research/upload",
        files={"file": ("paper.pdf", b"", "application/pdf")},
        headers=owner,
    )
    assert response.status_code == 400


def test_an_unknown_doc_kind_is_refused(client, owner):
    response = upload(client, owner, PAPER, doc_kind="thesis")
    assert response.status_code == 422


def test_an_oversized_file_is_refused(client, owner, monkeypatch):
    monkeypatch.setattr(settings, "research_max_bytes", 1024)
    response = upload(client, owner, PAPER)
    assert response.status_code == 413


def test_the_document_cap_is_enforced(client, owner, monkeypatch):
    monkeypatch.setattr(settings, "research_docs_per_user", 1)
    first = upload(client, owner, PAPER)
    assert first.status_code == 202
    second = upload(client, owner, PAPER)
    assert second.status_code == 409
    client.delete(f"/research/{first.json()['id']}", headers=owner)


# ---------------------------------------------------------------------------
# reading a section
# ---------------------------------------------------------------------------


def test_a_section_is_served_whole_with_its_neighbours(client, owner, paper):
    detail = client.get(f"/research/{paper}", headers=owner).json()
    readable = [s for s in detail["sections"] if s["readable"]]
    middle = readable[1]

    body = client.get(
        f"/research/{paper}/sections/{middle['id']}", headers=owner
    ).json()
    assert body["section"]["id"] == middle["id"]
    assert body["chunks"], "a readable section must have chunks"
    assert sum(c["word_count"] for c in body["chunks"]) > 0
    assert body["previous_section_id"] == readable[0]["id"]
    assert body["next_section_id"] == readable[2]["id"]


def test_the_first_and_last_readable_sections_have_no_neighbour(client, owner, paper):
    detail = client.get(f"/research/{paper}", headers=owner).json()
    readable = [s for s in detail["sections"] if s["readable"]]

    first = client.get(f"/research/{paper}/sections/{readable[0]['id']}", headers=owner).json()
    last = client.get(f"/research/{paper}/sections/{readable[-1]['id']}", headers=owner).json()
    assert first["previous_section_id"] is None
    assert last["next_section_id"] is None


def test_the_reference_list_is_readable_but_has_no_chunks(client, owner, paper):
    detail = client.get(f"/research/{paper}", headers=owner).json()
    references = next(s for s in detail["sections"] if s["kind"] == "references")
    body = client.get(f"/research/{paper}/sections/{references['id']}", headers=owner).json()
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["id"] == 0  # served whole, not stored as a chunk
    assert "Paivio" in body["chunks"][0]["text"]


def test_an_unknown_section_is_404(client, owner, paper):
    assert client.get(f"/research/{paper}/sections/999999", headers=owner).status_code == 404


# ---------------------------------------------------------------------------
# privacy
# ---------------------------------------------------------------------------


def test_another_user_cannot_see_the_document(client, owner, paper):
    stranger = register(client)
    assert client.get(f"/research/{paper}", headers=stranger).status_code == 404
    assert client.get(f"/research/{paper}/tags/status", headers=stranger).status_code == 404
    assert client.patch(f"/research/{paper}", json={"year": 2000}, headers=stranger).status_code == 404
    assert client.delete(f"/research/{paper}", headers=stranger).status_code == 404
    # Still there afterwards.
    assert client.get(f"/research/{paper}", headers=owner).status_code == 200


def test_another_user_cannot_see_it_in_their_library(client, owner, paper):
    stranger = register(client)
    listed = client.get("/research", headers=stranger).json()
    assert paper not in [d["id"] for d in listed]


def test_the_owner_sees_it_in_their_library(client, owner, paper):
    listed = client.get("/research", headers=owner).json()
    assert paper in [d["id"] for d in listed]


def test_research_needs_authentication(client, paper):
    assert client.get("/research").status_code == 401
    assert client.get(f"/research/{paper}").status_code == 401


# ---------------------------------------------------------------------------
# isolation from the reading-habit track
# ---------------------------------------------------------------------------


def test_a_research_document_is_not_in_the_reading_library(client, owner, paper):
    books = client.get("/books", headers=owner).json()
    assert paper not in [b["id"] for b in books]


def test_reading_endpoints_cannot_reach_a_research_document(client, owner, paper):
    """deps.book_for_user refuses research ids, which closes the whole
    reading-habit surface at once."""
    for path in (
        f"/books/{paper}",
        f"/books/{paper}/reader",
        f"/books/{paper}/micro-sessions",
        f"/books/{paper}/progress",
        f"/books/{paper}/status",
        f"/books/{paper}/themes",
    ):
        assert client.get(path, headers=owner).status_code == 404, path


def test_a_research_document_cannot_start_a_reading_session(client, owner, paper):
    db = SessionLocal()
    try:
        document = db.get(Book, paper)
        chunk = next(
            ms
            for chapter in document.chapters
            for ms in chapter.micro_sessions
        )
        chunk_id = chunk.id
    finally:
        db.close()

    response = client.post(
        "/sessions/start",
        json={"book_id": paper, "micro_session_id": chunk_id},
        headers=owner,
    )
    assert response.status_code == 404


def test_research_events_are_dropped(client, owner, paper):
    response = client.post(
        "/events",
        json=[
            {"event_type": "session_start", "book_id": paper},
            {"event_type": "session_end", "book_id": paper},
        ],
        headers=owner,
    )
    assert response.status_code == 201
    assert response.json() == {"logged": 0}


def test_research_rows_never_reach_the_pilot_export(client, owner, paper):
    from app.models import ReadingEvent

    # Write an event directly, bypassing the endpoint guard, to prove the
    # export filters as well as the write path.
    db = SessionLocal()
    try:
        db.add(ReadingEvent(user_id=1, book_id=paper, event_type="session_start"))
        db.commit()
        planted = True
    except Exception:
        db.rollback()
        planted = False
    finally:
        db.close()

    response = client.get(f"/admin/export/events.csv?token={settings.admin_token}")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert str(paper) not in [row["book_id"] for row in rows]

    if planted:
        db = SessionLocal()
        try:
            db.query(ReadingEvent).filter(ReadingEvent.book_id == paper).delete()
            db.commit()
        finally:
            db.close()


def test_a_research_document_does_not_count_toward_streaks(client, owner, paper):
    """Nothing about a research document should move the reading streak."""
    before = client.get("/streaks/me", headers=owner).json()
    client.post("/events", json={"event_type": "session_end", "book_id": paper}, headers=owner)
    after = client.get("/streaks/me", headers=owner).json()
    assert after["current_streak"] == before["current_streak"]


# ---------------------------------------------------------------------------
# the research export
# ---------------------------------------------------------------------------


def test_the_research_export_lists_this_users_sections(client, owner, paper):
    response = client.get("/research/export/sections.csv", headers=owner)
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    mine = [r for r in rows if r["document_id"] == str(paper)]
    assert mine
    assert {r["section_kind"] for r in mine} >= {"abstract", "body", "references"}
    assert mine[0]["doc_kind"] == "paper"


def test_the_research_export_is_per_user(client, owner, paper):
    stranger = register(client)
    rows = list(
        csv.DictReader(
            io.StringIO(client.get("/research/export/sections.csv", headers=stranger).text)
        )
    )
    assert str(paper) not in [r["document_id"] for r in rows]


# ---------------------------------------------------------------------------
# tagging
# ---------------------------------------------------------------------------


def test_tagging_is_off_without_consent(client, owner, paper, monkeypatch):
    monkeypatch.setattr(settings, "research_tagging_on_demand", True)
    status = client.get(f"/research/{paper}/tags/status", headers=owner).json()
    assert status["enabled"] is False
    assert "consent" in status["message"]


def test_tagging_is_off_when_the_server_switch_is_off(client, owner, paper, monkeypatch):
    monkeypatch.setattr(settings, "research_tagging_on_demand", False)
    client.put(f"/research/{paper}/consent", json={"consent": True}, headers=owner)
    status = client.get(f"/research/{paper}/tags/status", headers=owner).json()
    assert status["enabled"] is False
    assert "switched off" in status["message"]


def test_queueing_reports_progress_and_tags_get_stored(client, owner, paper, monkeypatch):
    monkeypatch.setattr(settings, "research_tagging_on_demand", True)
    monkeypatch.setattr(settings, "theme_call_gap_seconds", 0)
    monkeypatch.setattr(research_tags, "provider", lambda client_, text: '{"tags":[{"tag":"method","score":4}]}')
    monkeypatch.setattr(research_tags.themes, "make_client", lambda config=None: FakeHttpClient())

    client.put(f"/research/{paper}/consent", json={"consent": True}, headers=owner)
    response = client.post(f"/research/{paper}/tags/queue", headers=owner)
    assert response.status_code == 202

    status = client.get(f"/research/{paper}/tags/status", headers=owner).json()
    assert status["enabled"] is True
    assert status["done"] == status["total"] > 0
    assert status["failed"] == 0

    tags = client.get(f"/research/{paper}/tags", headers=owner).json()
    assert tags
    assert tags[0]["tags"][0]["tag"] == "method"
    assert tags[0]["tags"][0]["label"] == "Method"


def test_a_low_score_is_stored_but_never_shown(client, owner, paper, monkeypatch):
    monkeypatch.setattr(settings, "research_tagging_on_demand", True)
    monkeypatch.setattr(settings, "theme_call_gap_seconds", 0)
    monkeypatch.setattr(research_tags, "provider", lambda client_, text: '{"tags":[{"tag":"claim","score":2}]}')
    monkeypatch.setattr(research_tags.themes, "make_client", lambda config=None: FakeHttpClient())

    client.put(f"/research/{paper}/consent", json={"consent": True}, headers=owner)
    client.post(f"/research/{paper}/tags/queue", headers=owner)

    assert client.get(f"/research/{paper}/tags", headers=owner).json() == []
    db = SessionLocal()
    try:
        document = db.get(Book, paper)
        ids = research_tags.chunk_ids_of(document)
        stored = db.query(ResearchTag).filter(ResearchTag.micro_session_id.in_(ids)).count()
        assert stored > 0
    finally:
        db.close()


def test_a_bad_reply_fails_the_chunk_without_storing_anything(client, owner, paper, monkeypatch):
    monkeypatch.setattr(settings, "research_tagging_on_demand", True)
    monkeypatch.setattr(settings, "theme_call_gap_seconds", 0)
    monkeypatch.setattr(research_tags, "provider", lambda client_, text: "not json at all")
    monkeypatch.setattr(research_tags.themes, "make_client", lambda config=None: FakeHttpClient())

    client.put(f"/research/{paper}/consent", json={"consent": True}, headers=owner)
    client.post(f"/research/{paper}/tags/queue", headers=owner)

    status = client.get(f"/research/{paper}/tags/status", headers=owner).json()
    assert status["failed"] > 0
    assert status["done"] == 0
    assert client.get(f"/research/{paper}/tags", headers=owner).json() == []


def test_withdrawing_consent_deletes_the_tags(client, owner, paper, monkeypatch):
    monkeypatch.setattr(settings, "research_tagging_on_demand", True)
    monkeypatch.setattr(settings, "theme_call_gap_seconds", 0)
    monkeypatch.setattr(research_tags, "provider", lambda client_, text: '{"tags":[{"tag":"result","score":5}]}')
    monkeypatch.setattr(research_tags.themes, "make_client", lambda config=None: FakeHttpClient())

    client.put(f"/research/{paper}/consent", json={"consent": True}, headers=owner)
    client.post(f"/research/{paper}/tags/queue", headers=owner)
    assert client.get(f"/research/{paper}/tags", headers=owner).json()

    client.put(f"/research/{paper}/consent", json={"consent": False}, headers=owner)

    db = SessionLocal()
    try:
        document = db.get(Book, paper)
        ids = research_tags.chunk_ids_of(document)
        assert db.query(ResearchTag).filter(ResearchTag.micro_session_id.in_(ids)).count() == 0
        assert (
            db.query(ResearchTagging).filter(ResearchTagging.micro_session_id.in_(ids)).count()
            == 0
        )
    finally:
        db.close()


def test_literary_theme_tagging_never_applies_to_a_research_document(client, owner, paper):
    db = SessionLocal()
    try:
        document = db.get(Book, paper)
        from app.models import User
        from app.services.themes import tagging_enabled

        document.theme_tagging_consent = True
        db.commit()
        user = db.get(User, document.owner_user_id)
        assert tagging_enabled(db, user, document) is False
    finally:
        db.close()


def test_research_tags_are_not_in_the_pilot_theme_export(client, owner, paper, monkeypatch):
    monkeypatch.setattr(settings, "research_tagging_on_demand", True)
    monkeypatch.setattr(settings, "theme_call_gap_seconds", 0)
    monkeypatch.setattr(research_tags, "provider", lambda client_, text: '{"tags":[{"tag":"result","score":5}]}')
    monkeypatch.setattr(research_tags.themes, "make_client", lambda config=None: FakeHttpClient())
    client.put(f"/research/{paper}/consent", json={"consent": True}, headers=owner)
    client.post(f"/research/{paper}/tags/queue", headers=owner)

    response = client.get(f"/admin/export/themes.csv?token={settings.admin_token}")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert str(paper) not in [r["book_id"] for r in rows]
    assert "result" not in {r["theme"] for r in rows}


# ---------------------------------------------------------------------------
# key points
# ---------------------------------------------------------------------------


def test_key_points_are_off_by_default(client, owner, paper):
    detail = client.get(f"/research/{paper}", headers=owner).json()
    section_id = next(s["id"] for s in detail["sections"] if s["readable"])
    body = client.get(f"/research/{paper}/sections/{section_id}", headers=owner).json()
    assert body["key_points"] is None

    response = client.post(
        f"/research/{paper}/sections/{section_id}/key-points", headers=owner
    )
    assert response.status_code == 409


def test_key_points_are_generated_and_labelled(client, owner, paper, monkeypatch):
    monkeypatch.setattr(settings, "research_tagging_on_demand", True)
    monkeypatch.setattr(settings, "research_key_points_on_demand", True)
    monkeypatch.setattr(
        research_tags,
        "key_points_provider",
        lambda client_, text: '{"points":["Sessions lengthened by four minutes.","Comprehension held."]}',
    )
    monkeypatch.setattr(research_tags.themes, "make_client", lambda config=None: FakeHttpClient())

    client.put(f"/research/{paper}/consent", json={"consent": True}, headers=owner)
    detail = client.get(f"/research/{paper}", headers=owner).json()
    section_id = next(s["id"] for s in detail["sections"] if s["readable"])

    assert client.post(
        f"/research/{paper}/sections/{section_id}/key-points", headers=owner
    ).status_code == 202

    body = client.get(f"/research/{paper}/sections/{section_id}", headers=owner).json()
    assert body["key_points"]["status"] == "done"
    assert "Sessions lengthened" in body["key_points"]["text"]


def test_a_failed_key_points_call_shows_nothing(client, owner, paper, monkeypatch):
    monkeypatch.setattr(settings, "research_tagging_on_demand", True)
    monkeypatch.setattr(settings, "research_key_points_on_demand", True)
    monkeypatch.setattr(
        research_tags, "key_points_provider", lambda client_, text: "the model rambled"
    )
    monkeypatch.setattr(research_tags.themes, "make_client", lambda config=None: FakeHttpClient())

    client.put(f"/research/{paper}/consent", json={"consent": True}, headers=owner)
    detail = client.get(f"/research/{paper}", headers=owner).json()
    section_id = next(s["id"] for s in detail["sections"] if s["readable"])
    client.post(f"/research/{paper}/sections/{section_id}/key-points", headers=owner)

    body = client.get(f"/research/{paper}/sections/{section_id}", headers=owner).json()
    assert body["key_points"]["status"] == "failed"
    assert body["key_points"]["text"] == ""


# ---------------------------------------------------------------------------
# deletion
# ---------------------------------------------------------------------------


def test_deleting_a_document_removes_its_rows(client, owner):
    document_id = upload(client, owner, PAPER).json()["id"]
    db = SessionLocal()
    try:
        document = db.get(Book, document_id)
        chapter_ids = [c.id for c in document.chapters]
        chunk_ids = research_tags.chunk_ids_of(document)
    finally:
        db.close()
    assert chunk_ids

    assert client.delete(f"/research/{document_id}", headers=owner).status_code == 204

    db = SessionLocal()
    try:
        assert db.get(Book, document_id) is None
        assert db.query(MicroSession).filter(MicroSession.id.in_(chunk_ids)).count() == 0
        assert (
            db.query(SectionKeyPoints).filter(SectionKeyPoints.chapter_id.in_(chapter_ids)).count()
            == 0
        )
    finally:
        db.close()


def test_a_book_cannot_be_deleted_through_the_research_route(client, owner):
    assert client.delete("/research/1", headers=owner).status_code == 404


# ---------------------------------------------------------------------------
# highlights work on a research document
#
# Highlights are deliberately shared between the two tracks: they anchor to a
# micro-session and a research chunk is one. deps.annotatable_for_user is the
# single place that accepts both.
# ---------------------------------------------------------------------------


def _first_chunk(document_id: int) -> tuple[int, str]:
    db = SessionLocal()
    try:
        document = db.get(Book, document_id)
        chunk_id = research_tags.chunk_ids_of(document)[0]
        return chunk_id, db.get(MicroSession, chunk_id).text
    finally:
        db.close()


def test_a_passage_of_a_paper_can_be_highlighted(client, owner, paper):
    chunk_id, text = _first_chunk(paper)
    response = client.post(
        f"/books/{paper}/highlights",
        json={"micro_session_id": chunk_id, "start": 0, "end": 20, "color": "yellow",
              "comment": "worth quoting"},
        headers=owner,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["quote"] == text[:20]
    assert body["comment"] == "worth quoting"
    # Numbered across the readable sections, so a note on a paper is not blank.
    assert body["session_number"] == 1

    listed = client.get(f"/books/{paper}/highlights", headers=owner).json()
    assert [h["id"] for h in listed] == [body["id"]]


def test_another_user_cannot_highlight_or_read_a_paper(client, owner, paper):
    stranger = register(client)
    chunk_id, _ = _first_chunk(paper)
    assert client.get(f"/books/{paper}/highlights", headers=stranger).status_code == 404
    assert (
        client.post(
            f"/books/{paper}/highlights",
            json={"micro_session_id": chunk_id, "start": 0, "end": 10, "color": "blue"},
            headers=stranger,
        ).status_code
        == 404
    )


def test_a_highlight_on_a_paper_carries_its_research_tags(client, owner, paper, monkeypatch):
    """A note taken on a paper should be labelled "Method", not with a literary
    theme and not with nothing."""
    monkeypatch.setattr(settings, "research_tagging_on_demand", True)
    monkeypatch.setattr(settings, "theme_call_gap_seconds", 0)
    monkeypatch.setattr(
        research_tags, "provider", lambda client_, text: '{"tags":[{"tag":"method","score":5}]}'
    )
    monkeypatch.setattr(research_tags.themes, "make_client", lambda config=None: FakeHttpClient())
    client.put(f"/research/{paper}/consent", json={"consent": True}, headers=owner)
    client.post(f"/research/{paper}/tags/queue", headers=owner)

    chunk_id, _ = _first_chunk(paper)
    body = client.post(
        f"/books/{paper}/highlights",
        json={"micro_session_id": chunk_id, "start": 0, "end": 15, "color": "green"},
        headers=owner,
    ).json()
    assert [t["label"] for t in body["themes"]] == ["Method"]


# ---------------------------------------------------------------------------
# metadata that needs a person to look at it
# ---------------------------------------------------------------------------


def test_a_complete_paper_needs_no_review(client, owner, paper):
    detail = client.get(f"/research/{paper}", headers=owner).json()
    assert detail["needs_review"] == []
    assert detail["unverified"] == []


def test_a_document_with_no_author_says_which_fields_are_missing(client, owner):
    """The textbook fixture states no year, and its embedded author is a
    single name rather than a byline."""
    document_id = upload(client, owner, TEXTBOOK).json()["id"]
    try:
        detail = client.get(f"/research/{document_id}", headers=owner).json()
        assert "year" in detail["needs_review"]
        assert detail["no_date"] is False
    finally:
        client.delete(f"/research/{document_id}", headers=owner)


def test_filling_a_field_in_takes_it_off_the_list(client, owner):
    document_id = upload(client, owner, TEXTBOOK).json()["id"]
    try:
        before = client.get(f"/research/{document_id}", headers=owner).json()
        assert "year" in before["needs_review"]

        after = client.patch(
            f"/research/{document_id}", json={"year": 2019}, headers=owner
        ).json()
        assert "year" not in after["needs_review"]
    finally:
        client.delete(f"/research/{document_id}", headers=owner)


def test_a_document_can_be_declared_undated(client, owner):
    """"n.d." is only correct once somebody has confirmed there is no date."""
    document_id = upload(client, owner, TEXTBOOK).json()["id"]
    try:
        after = client.patch(
            f"/research/{document_id}", json={"no_date": True}, headers=owner
        ).json()
        assert after["no_date"] is True
        assert "year" not in after["needs_review"]
    finally:
        client.delete(f"/research/{document_id}", headers=owner)


def test_no_sentence_from_the_body_ever_reaches_the_author_field(client, owner, paper):
    """The failure this all comes from: the author field held a sentence out
    of the body of the paper, and every citation copied carried it."""
    detail = client.get(f"/research/{paper}", headers=owner).json()
    authors = detail["authors"]
    assert not authors.endswith(".")
    assert len(authors) <= 120
    assert " according to " not in authors


def test_the_section_list_has_no_title_page_entry(client, owner, paper):
    detail = client.get(f"/research/{paper}", headers=owner).json()
    assert "front_matter" not in [s["kind"] for s in detail["sections"]]
    for section in detail["sections"]:
        assert not section["title"].islower()
