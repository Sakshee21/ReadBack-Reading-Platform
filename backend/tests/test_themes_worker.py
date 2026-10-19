"""On-demand tagging for consented uploads: planning, claims, the worker, the route."""

import datetime as dt
import json
import logging
import threading

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Book, MicroSession, MicroSessionTagging, MicroSessionTheme
from app.security import create_access_token
from app.services import theme_worker, themes
from tests.test_themes_service import db, drop_book, make_book, make_user  # noqa: F401


def reply(*pairs):
    return json.dumps({"themes": [{"theme": t, "score": s} for t, s in pairs]})


class Stub:
    def __init__(self, content=None):
        self.content = content if content is not None else reply(("romance", 4))
        self.calls = []

    def __call__(self, client, text):
        self.calls.append(text)
        if isinstance(self.content, Exception):
            raise self.content
        return self.content


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture()
def upload(db):
    owner = make_user(db)
    book, chunks = make_book(db, owner=owner, consent=True, texts=tuple(f"Chunk number {i}." for i in range(8)))
    yield owner, book, chunks
    drop_book(db, book.id)


def status_of(db, ms):
    db.expire_all()
    row = db.get(MicroSessionTagging, ms.id)
    return row.status if row else None


# --------------------------------------------------------------------------
# planning and claims
# --------------------------------------------------------------------------


def test_plan_is_current_plus_four_untagged_in_order(db, upload):
    _, book, chunks = upload
    assert theme_worker.plan_prefetch(db, book, chunks[1].id) == [c.id for c in chunks[1:6]]
    assert theme_worker.plan_prefetch(db, book, chunks[6].id) == [chunks[6].id, chunks[7].id]


def test_plan_skips_tagged_pending_and_recently_failed(db, upload):
    _, book, chunks = upload
    now = dt.datetime.utcnow()
    themes.tag_chunk(db, chunks[0], client=None, provider=Stub())
    db.add(MicroSessionTagging(micro_session_id=chunks[1].id, status="pending", claimed_at=now))
    db.add(MicroSessionTagging(micro_session_id=chunks[2].id, status="failed", error="x", updated_at=now))
    db.add(MicroSessionTagging(micro_session_id=chunks[3].id, status="failed", error="x", updated_at=now - dt.timedelta(minutes=20)))
    db.commit()
    assert theme_worker.plan_prefetch(db, book, chunks[0].id) == [chunks[3].id, chunks[4].id]


def test_expired_claims_are_retaken(db, upload):
    _, book, chunks = upload
    old = dt.datetime.utcnow() - dt.timedelta(minutes=30)
    db.add(MicroSessionTagging(micro_session_id=chunks[0].id, status="pending", claimed_at=old))
    db.commit()
    assert chunks[0].id in theme_worker.plan_prefetch(db, book, chunks[0].id)
    assert theme_worker.claim(db, [chunks[0].id]) == [chunks[0].id]
    assert status_of(db, chunks[0]) == "pending"


def test_claim_refuses_a_finished_chunk_whatever_its_versions(db, upload):
    _, book, chunks = upload
    themes.tag_chunk(db, chunks[0], client=None, provider=Stub())
    row = db.get(MicroSessionTagging, chunks[0].id)
    row.prompt_version, row.theme_list_version = 0, 0
    db.commit()
    assert theme_worker.claim(db, [chunks[0].id]) == []
    assert theme_worker.plan_prefetch(db, book, chunks[0].id)[0] != chunks[0].id


def test_claim_refuses_live_claims_and_finished_chunks(db, upload):
    _, book, chunks = upload
    assert theme_worker.claim(db, [chunks[0].id, chunks[1].id]) == [chunks[0].id, chunks[1].id]
    assert theme_worker.claim(db, [chunks[0].id, chunks[2].id]) == [chunks[2].id]
    themes.tag_chunk(db, chunks[3], client=None, provider=Stub())
    assert theme_worker.claim(db, [chunks[3].id]) == []


def test_two_concurrent_claims_never_overlap(upload):
    _, book, chunks = upload
    ids = [c.id for c in chunks]
    results = []
    barrier = threading.Barrier(6)

    def attempt():
        session = SessionLocal()
        try:
            barrier.wait()
            results.append(theme_worker.claim(session, ids))
        finally:
            session.close()

    threads = [threading.Thread(target=attempt) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    claimed = [i for r in results for i in r]
    assert sorted(claimed) == sorted(ids)  # every chunk claimed exactly once


# --------------------------------------------------------------------------
# the worker
# --------------------------------------------------------------------------


def test_run_prefetch_tags_with_gap_between_calls(db, upload, monkeypatch):
    monkeypatch.setattr(settings, "theme_call_gap_seconds", 4.0)
    _, book, chunks = upload
    ids = theme_worker.claim(db, [c.id for c in chunks[:3]])
    sleeps, stub = [], Stub()
    theme_worker.run_prefetch(book.id, ids, provider=stub, sleep=sleeps.append, client=object())
    assert len(stub.calls) == 3 and sleeps == [4.0, 4.0]
    assert all(status_of(db, c) == "done" for c in chunks[:3])
    assert db.query(MicroSessionTheme).filter_by(micro_session_id=chunks[0].id).count() == 1


def test_run_prefetch_swallows_errors_and_releases_the_claim(db, upload):
    _, book, chunks = upload
    ids = theme_worker.claim(db, [c.id for c in chunks[:2]])
    stub = Stub(RuntimeError("boom"))
    theme_worker.run_prefetch(book.id, ids, provider=stub, sleep=lambda s: None, client=object())
    # an unexpected error ends the run; nothing is left pending
    assert all(status_of(db, c) in (None, "failed") for c in chunks[:2])


def test_a_model_failure_marks_failed_and_continues(db, upload):
    _, book, chunks = upload
    ids = theme_worker.claim(db, [c.id for c in chunks[:2]])
    calls = iter([themes.ThemeProviderError("down"), reply(("romance", 4))])

    def provider(client, text):
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item

    theme_worker.run_prefetch(book.id, ids, provider=provider, sleep=lambda s: None, client=object())
    assert status_of(db, chunks[0]) == "failed" and status_of(db, chunks[1]) == "done"


def test_withdrawing_consent_stops_further_calls_and_leaves_nothing(db, upload):
    _, book, chunks = upload
    ids = theme_worker.claim(db, [c.id for c in chunks[:3]])
    stub = Stub()

    def withdraw_after_first(seconds):
        other = SessionLocal()
        try:
            b = other.get(Book, book.id)
            b.theme_tagging_consent = False
            other.commit()
        finally:
            other.close()

    theme_worker.run_prefetch(book.id, ids, provider=stub, sleep=withdraw_after_first, client=object())
    assert len(stub.calls) == 1
    db.expire_all()
    assert db.query(MicroSessionTheme).filter(MicroSessionTheme.micro_session_id.in_([c.id for c in chunks])).count() == 0
    assert db.query(MicroSessionTagging).filter(MicroSessionTagging.micro_session_id.in_([c.id for c in chunks])).count() == 0


def test_run_prefetch_does_nothing_without_consent(db, upload):
    _, book, chunks = upload
    book.theme_tagging_consent = False
    db.commit()
    stub = Stub()
    theme_worker.run_prefetch(book.id, [c.id for c in chunks[:2]], provider=stub, sleep=lambda s: None, client=object())
    assert stub.calls == []


def test_no_text_is_logged_on_failure(db, upload, caplog):
    _, book, chunks = upload
    ids = theme_worker.claim(db, [chunks[0].id])
    with caplog.at_level(logging.DEBUG):
        theme_worker.run_prefetch(book.id, ids, provider=Stub(RuntimeError("Chunk number 0.")), sleep=lambda s: None, client=object())
    assert "Chunk number" not in caplog.text


def test_a_long_run_keeps_its_later_claims_alive(db, upload):
    """Claims are refreshed while the run works, so a slow call cannot let the
    later chunks expire and be tagged a second time."""
    _, book, chunks = upload
    ids = theme_worker.claim(db, [c.id for c in chunks[:3]])
    stale = dt.datetime.utcnow() - theme_worker.CLAIM_TTL - dt.timedelta(minutes=1)
    db.query(MicroSessionTagging).filter(MicroSessionTagging.micro_session_id.in_(ids)).update(
        {"claimed_at": stale}, synchronize_session=False
    )
    db.commit()
    taken = []

    def provider(client, text):
        other = SessionLocal()
        try:
            taken.append(theme_worker.claim(other, [chunks[2].id]))
        finally:
            other.close()
        return reply(("romance", 4))

    theme_worker.run_prefetch(book.id, ids, provider=provider, sleep=lambda s: None, client=object())
    assert taken[0] == []  # still held by the running prefetch


def test_a_failed_run_never_releases_a_claim_another_run_took_over(db, upload):
    _, book, chunks = upload
    ids = theme_worker.claim(db, [chunks[0].id, chunks[1].id])
    newer = dt.datetime.utcnow() + dt.timedelta(minutes=1)

    def provider(client, text):
        other = SessionLocal()
        try:
            other.query(MicroSessionTagging).filter_by(micro_session_id=chunks[1].id).update({"claimed_at": newer})
            other.commit()
        finally:
            other.close()
        raise RuntimeError("boom")

    theme_worker.run_prefetch(book.id, ids, provider=provider, sleep=lambda s: None, client=object())
    assert status_of(db, chunks[0]) is None
    assert status_of(db, chunks[1]) == "pending"  # the other run's claim survives


def test_a_chunk_cannot_hold_the_same_theme_twice(db, upload):
    from sqlalchemy.exc import IntegrityError

    _, book, chunks = upload
    for _ in range(2):
        db.add(MicroSessionTheme(micro_session_id=chunks[0].id, theme="romance", score=4, source="llm"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_tags_written_before_an_error_are_purged_if_consent_was_withdrawn(db, upload):
    _, book, chunks = upload
    ids = theme_worker.claim(db, [c.id for c in chunks[:2]])

    def withdraw_then_crash(seconds):
        other = SessionLocal()
        try:
            other.get(Book, book.id).theme_tagging_consent = False
            other.commit()
        finally:
            other.close()
        raise RuntimeError("db hiccup")

    theme_worker.run_prefetch(book.id, ids, provider=Stub(), sleep=withdraw_then_crash, client=object())
    db.expire_all()
    assert db.query(MicroSessionTheme).filter(MicroSessionTheme.micro_session_id.in_([c.id for c in chunks])).count() == 0


def test_a_run_whose_claims_were_taken_over_makes_no_calls(db, upload):
    """Withdraw then re-grant deletes the old claims; a new prefetch claims the
    same chunks. The old run must stand down, not tag them in parallel."""
    _, book, chunks = upload
    old_stamp = dt.datetime.utcnow()
    ids = theme_worker.claim(db, [c.id for c in chunks[:2]], stamp=old_stamp)
    db.query(MicroSessionTagging).filter(MicroSessionTagging.micro_session_id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    assert theme_worker.claim(db, ids) == ids  # the new run's claim
    stub = Stub()
    theme_worker.run_prefetch(book.id, ids, provider=stub, sleep=lambda s: None, client=object(), stamp=old_stamp)
    assert stub.calls == []
    assert all(status_of(db, c) == "pending" for c in chunks[:2])


def test_runs_for_the_same_book_never_overlap(db, upload):
    _, book, chunks = upload
    a = theme_worker.claim(db, [chunks[0].id, chunks[1].id])
    b = theme_worker.claim(db, [chunks[2].id, chunks[3].id])
    active, peak, lock = [0], [0], threading.Lock()

    def provider(client, text):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        threading.Event().wait(0.05)
        with lock:
            active[0] -= 1
        return reply(("romance", 4))

    threads = [
        threading.Thread(target=theme_worker.run_prefetch, args=(book.id, ids),
                         kwargs=dict(provider=provider, sleep=lambda s: None, client=object()))
        for ids in (a, b)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] == 1
    assert all(status_of(db, c) == "done" for c in chunks[:4])


# --------------------------------------------------------------------------
# the route
# --------------------------------------------------------------------------


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "theme_tagging_on_demand", True)
    monkeypatch.setattr(settings, "op_api_key", "k")
    monkeypatch.setattr(settings, "op_model", "m")
    started = []
    monkeypatch.setattr(theme_worker, "run_prefetch", lambda book_id, ids, **kw: started.append((book_id, list(ids))))
    return started


def prefetch(client, headers, book, ms):
    return client.post(f"/books/{book.id}/themes/prefetch", json={"micro_session_id": ms.id}, headers=headers)


def test_route_returns_202_and_starts_the_current_plus_four(client, db, upload, enabled):
    owner, book, chunks = upload
    resp = prefetch(client, auth(owner), book, chunks[2])
    assert resp.status_code == 202 and resp.json() == {"queued": 5}
    assert enabled == [(book.id, [c.id for c in chunks[2:7]])]
    assert all(status_of(db, c) == "pending" for c in chunks[2:7])
    again = prefetch(client, auth(owner), book, chunks[2])
    assert again.json() == {"queued": 0} and len(enabled) == 1  # already claimed


def test_route_403_without_consent_and_404_for_others(client, db, upload, enabled):
    owner, book, chunks = upload
    stranger = make_user(db)
    assert prefetch(client, auth(stranger), book, chunks[0]).status_code == 404
    book.theme_tagging_consent = False
    db.commit()
    assert prefetch(client, auth(owner), book, chunks[0]).status_code == 403
    assert enabled == []


def test_route_noop_for_seeded_books_and_when_disabled(client, db, upload, enabled, monkeypatch):
    owner, book, chunks = upload
    seeded, (s0, _) = make_book(db)
    try:
        assert prefetch(client, auth(owner), seeded, s0).json() == {"queued": 0}
        monkeypatch.setattr(settings, "theme_tagging_on_demand", False)
        assert prefetch(client, auth(owner), book, chunks[0]).json() == {"queued": 0}
        monkeypatch.setattr(settings, "theme_tagging_on_demand", True)
        monkeypatch.setattr(settings, "op_api_key", "")
        assert prefetch(client, auth(owner), book, chunks[0]).json() == {"queued": 0}
        assert enabled == []
        assert db.query(MicroSessionTagging).filter_by(micro_session_id=s0.id).count() == 0
    finally:
        drop_book(db, seeded.id)


def test_route_422_for_a_micro_session_of_another_book(client, db, upload, enabled):
    owner, book, _ = upload
    other, (o0, _) = make_book(db)
    try:
        assert prefetch(client, auth(owner), book, o0).status_code == 422
    finally:
        drop_book(db, other.id)


def test_route_requires_auth(client, upload, enabled):
    _, book, chunks = upload
    assert client.post(f"/books/{book.id}/themes/prefetch", json={"micro_session_id": chunks[0].id}).status_code == 401
