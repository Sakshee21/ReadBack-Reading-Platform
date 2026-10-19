"""On-demand theme tagging for a reader's own, consented upload.

Seeded books are tagged in one offline batch (scripts/tag_themes.py) so the
study data is one model and one prompt. An uploaded book has no such batch, so
while its owner reads, the chunks ahead of them are tagged in the background.
Reading never waits on this, and every failure here is swallowed.

A chunk is "claimed" in one atomic statement before it is sent anywhere, so two
tabs or readers never tag the same chunk twice; claims expire so a crash cannot
leave a chunk stuck.
"""

import datetime as dt
import logging
import threading
import time

from sqlalchemy import and_, not_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Book, MicroSession, MicroSessionTagging, MicroSessionTheme
from app.services import themes
from app.services.progression import ordered_micro_sessions
from app.services.themes import ThemeProviderError

log = logging.getLogger(__name__)

AHEAD = 4
CLAIM_TTL = dt.timedelta(minutes=20)  # comfortably longer than one model call can take
FAIL_COOLDOWN = dt.timedelta(minutes=15)


_book_locks: dict[int, threading.Lock] = {}
_book_locks_guard = threading.Lock()


def _book_lock(book_id: int) -> threading.Lock:
    """One run per book at a time: block changes fire often and parallel runs
    would only fight over the free tier's rate limit."""
    with _book_locks_guard:
        return _book_locks.setdefault(book_id, threading.Lock())


def _now() -> dt.datetime:
    return dt.datetime.utcnow()


def plan_prefetch(db: Session, book: Book, current_micro_session_id: int, ahead: int = AHEAD) -> list[int]:
    """The current chunk plus the next ``ahead`` that still need tags, skipping
    chunks being tagged right now or that failed recently."""
    ordered = ordered_micro_sessions(book)
    start = next((i for i, ms in enumerate(ordered) if ms.id == current_micro_session_id), None)
    if start is None:
        return []
    now = _now()
    plan = []
    for ms in ordered[start : start + 1 + ahead]:
        row = db.get(MicroSessionTagging, ms.id)
        if row is not None:
            if row.status == "pending" and row.claimed_at and now - row.claimed_at < CLAIM_TTL:
                continue
            if row.status == "failed" and row.updated_at and now - row.updated_at < FAIL_COOLDOWN:
                continue
        if themes.needs_tagging(db, ms.id):
            plan.append(ms.id)
    return plan


def claim(db: Session, ids: list[int], stamp: dt.datetime | None = None) -> list[int]:
    """Atomically mark chunks as pending; returns the ones this caller won.
    ``stamp`` is the claim time, which identifies this run's claims later."""
    now = stamp or _now()
    won: list[int] = []
    for micro_session_id in ids:
        stmt = insert(MicroSessionTagging).values(
            micro_session_id=micro_session_id,
            status="pending",
            model=settings.llm_model,
            prompt_version=themes.PROMPT_VERSION,
            theme_list_version=themes.THEME_LIST_VERSION,
            claimed_at=now,
            updated_at=now,
        )
        table = MicroSessionTagging.__table__
        finished = table.c.status == "done"  # finished chunks are permanent, any version
        live = and_(table.c.status == "pending", table.c.claimed_at > now - CLAIM_TTL)
        stmt = stmt.on_conflict_do_update(
            index_elements=[table.c.micro_session_id],
            set_={"status": "pending", "claimed_at": now, "updated_at": now, "error": None},
            where=not_(finished) & not_(live),
        ).returning(table.c.micro_session_id)
        if db.execute(stmt).first() is not None:
            won.append(micro_session_id)
    db.commit()
    return won


def _heartbeat(db: Session, ids: list[int], held: dt.datetime | None = None) -> tuple[dt.datetime, set[int]]:
    """Re-stamp the claims this run still holds so a slow call cannot let them
    expire and be taken by another run. With ``held`` (the stamp the claims
    carry), only rows still carrying it are refreshed. Returns the new stamp and
    the chunk ids this run still owns."""
    db.rollback()
    stamp = _now()
    owned: set[int] = set()
    if ids:
        query = db.query(MicroSessionTagging).filter(
            MicroSessionTagging.micro_session_id.in_(ids), MicroSessionTagging.status == "pending"
        )
        if held is not None:
            query = query.filter(MicroSessionTagging.claimed_at == held)
        owned = {row.micro_session_id for row in query}
        if owned:
            db.query(MicroSessionTagging).filter(MicroSessionTagging.micro_session_id.in_(owned)).update(
                {"claimed_at": stamp}, synchronize_session=False
            )
        db.commit()
    return stamp, owned


def _release(db: Session, ids: list[int], stamp: dt.datetime | None = None) -> None:
    """Drop claims this run still holds. With a stamp, only rows still carrying
    it, so a claim another run has since taken over is left alone."""
    db.rollback()
    if ids:
        query = db.query(MicroSessionTagging).filter(
            MicroSessionTagging.micro_session_id.in_(ids), MicroSessionTagging.status == "pending"
        )
        if stamp is not None:
            query = query.filter(MicroSessionTagging.claimed_at == stamp)
        query.delete(synchronize_session=False)
        db.commit()


def _purge(db: Session, ids: list[int]) -> None:
    """Consent was withdrawn: remove what this run wrote."""
    db.rollback()
    if ids:
        db.query(MicroSessionTheme).filter(MicroSessionTheme.micro_session_id.in_(ids)).delete(
            synchronize_session=False
        )
        db.query(MicroSessionTagging).filter(MicroSessionTagging.micro_session_id.in_(ids)).delete(
            synchronize_session=False
        )
        db.commit()


def _consented(db: Session, book_id: int) -> bool:
    """Is tagging still wanted? Only an upload whose owner has consented."""
    db.expire_all()
    book = db.get(Book, book_id)
    return bool(book and book.is_user_uploaded and book.theme_tagging_consent)


def run_prefetch(
    book_id: int,
    ids: list[int],
    *,
    provider=None,
    sleep=time.sleep,
    client=None,
    stamp: dt.datetime | None = None,
) -> None:
    """Tag the claimed chunks one after another. Runs in the background; never
    raises, and never logs passage text. ``stamp`` is the time the chunks were
    claimed with; a chunk whose claim has since been taken over is left alone."""
    with _book_lock(book_id):
        _run_prefetch(book_id, ids, provider=provider, sleep=sleep, client=client, stamp=stamp)


def _run_prefetch(book_id, ids, *, provider, sleep, client, stamp) -> None:
    db = SessionLocal()
    own_client = client is None
    pending = list(ids)
    try:
        if not _consented(db, book_id):
            _release(db, pending)
            return
        if own_client:
            client = themes.make_client()
        for micro_session_id in list(pending):
            if not _consented(db, book_id):
                _purge(db, ids)
                return
            stamp, owned = _heartbeat(db, pending, stamp)
            if micro_session_id not in owned:  # another run took this chunk over
                pending.remove(micro_session_id)
                continue
            chunk = db.get(MicroSession, micro_session_id)
            if chunk is not None:
                themes.tag_chunk(db, chunk, client=client, provider=provider)
            pending.remove(micro_session_id)
            if not _consented(db, book_id):  # withdrawn while the model was working
                _purge(db, ids)
                return
            if pending:
                sleep(settings.theme_call_gap_seconds)
    except ThemeProviderError as err:
        log.warning("theme prefetch could not start: %s", err)
        _release(db, pending, stamp)
    except Exception as err:  # noqa: BLE001 - background work must never surface
        log.warning("theme prefetch stopped: %s", type(err).__name__)
        _release(db, pending, stamp)
        try:
            if not _consented(db, book_id):  # tags may have been written after a withdrawal
                _purge(db, ids)
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()
        if own_client and client is not None:
            client.close()
