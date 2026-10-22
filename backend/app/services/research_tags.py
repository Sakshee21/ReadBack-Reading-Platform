"""Rhetorical tagging for research documents, and per-section key points.

Separate from the literary themes in every way that matters. The two lists mean
different things - a novel passage is *about* grief, a paper paragraph *is* a
claim - so they have their own closed list, their own tables and their own
version numbers. A research document can therefore never appear in the pilot
theme export, and a change to one list cannot invalidate the other.

Everything else follows the rules the theme tagger already established, because
they were the right rules:

* at most 3 tags per chunk, each scored 1-5;
* a score below 3 is stored for analysis and never shown or exported;
* a stored tag is never overwritten, whatever model or prompt produced it;
* nothing is sent anywhere without the owner's consent, re-checked around
  every call, and withdrawing consent deletes what was written;
* all of it runs in the background and never blocks a reader.

The transport (retries, backoff, Retry-After, both provider response shapes)
is ``themes.call_model``, which takes the request builder as an argument. Only
the prompt and the validation live here.
"""

import datetime as dt
import json
import logging
import threading
import time

from sqlalchemy import and_, not_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import (
    Book,
    Chapter,
    MicroSession,
    ResearchTag,
    ResearchTagging,
    SectionKeyPoints,
)
from app.schemas import KeyPointsOut, ResearchChunkTagsOut, ResearchTagOut, ResearchTagStatusOut
from app.services import themes
from app.services.research_extract import READABLE_KINDS
from app.services.themes import ThemeProviderError, ThemeReplyError

log = logging.getLogger(__name__)

RESEARCH_TAGS: dict[str, str] = {
    "problem_motivation": "Problem & motivation",
    "claim": "Claim",
    "method": "Method",
    "dataset": "Dataset",
    "result": "Result",
    "limitation": "Limitation",
    "definition": "Definition",
    "future_work": "Future work",
    "related_work": "Related work",
}
TAG_LIST_VERSION = 1
PROMPT_VERSION = 1
MIN_SHOWN_SCORE = 3
MAX_TAGS = 3

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"

CLAIM_TTL = dt.timedelta(minutes=20)
FAIL_COOLDOWN = dt.timedelta(minutes=15)

MAX_KEY_POINTS = 5
MAX_KEY_POINT_CHARS = 240

_document_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _document_lock(document_id: int) -> threading.Lock:
    """One run per document: parallel runs would only fight over the free
    tier's rate limit."""
    with _locks_guard:
        return _document_locks.setdefault(document_id, threading.Lock())


def _now() -> dt.datetime:
    return dt.datetime.utcnow()


# ---------------------------------------------------------------------------
# prompt and validation
# ---------------------------------------------------------------------------


def build_messages(text: str) -> list[dict]:
    listing = "; ".join(f"{tag} ({label})" for tag, label in RESEARCH_TAGS.items())
    system = (
        "You label paragraphs from academic papers and textbooks by the role they "
        f"play in the argument. Choose at most {MAX_TAGS} labels from this closed "
        f"list, and only ones the paragraph clearly performs: {listing}. "
        "Score each from 1 (slight) to 5 (the paragraph is mainly this). "
        "Judge only the paragraph you are given; do not infer from the rest of the "
        "document. Label the role, not the subject matter. "
        'Reply with JSON only: {"tags":[{"tag":"<id>","score":<1-5>}]}. '
        'If no label clearly applies, reply {"tags":[]}.'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def response_schema() -> dict:
    return {
        "name": "paragraph_roles",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "maxItems": MAX_TAGS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "tag": {"type": "string", "enum": list(RESEARCH_TAGS)},
                            "score": {"type": "integer", "minimum": 1, "maximum": 5},
                        },
                        "required": ["tag", "score"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["tags"],
            "additionalProperties": False,
        },
    }


def _strip_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return text


def parse_reply(content: str | None) -> list[tuple[str, int]]:
    """Validate a model reply; return [(tag, score)] or raise ThemeReplyError."""
    if not isinstance(content, str) or not content.strip():
        raise ThemeReplyError("empty reply")
    try:
        data = json.loads(_strip_fence(content))
    except ValueError as err:
        raise ThemeReplyError("reply is not JSON") from err
    items = data.get("tags") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ThemeReplyError("reply has no tags list")

    out: list[tuple[str, int]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ThemeReplyError("tag entry is not an object")
        tag, score = item.get("tag"), item.get("score")
        if tag not in RESEARCH_TAGS:
            raise ThemeReplyError("tag is not in the list")
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
            raise ThemeReplyError("score is not an integer from 1 to 5")
        if tag in seen:
            raise ThemeReplyError("duplicate tag")
        seen.add(tag)
        out.append((tag, score))
    return sorted(out, key=lambda pair: -pair[1])[:MAX_TAGS]


def _tag_payload(config, text: str) -> dict:
    if config.provider == "ollama":
        return {
            "model": config.model,
            "messages": build_messages(text),
            "stream": False,
            "format": response_schema()["schema"],
            "options": {"temperature": 0.1, "num_predict": 800},
        }
    return {
        "model": config.model,
        "messages": build_messages(text),
        "temperature": 0.1,
        "max_tokens": 800,
        "response_format": {"type": "json_schema", "json_schema": response_schema()},
    }


def ask_model(client, text: str) -> str:
    """The replaceable provider call. Tests and callers may substitute their own."""
    return themes.call_model(client, text, payload_for=_tag_payload)


provider = ask_model


# ---------------------------------------------------------------------------
# consent
# ---------------------------------------------------------------------------


def tagging_enabled(document: Book) -> bool:
    """Only a research document whose owner has consented, and only when the
    feature is switched on at all."""
    return bool(
        settings.research_tagging_on_demand
        and (document.source_type or "") == "research"
        and document.theme_tagging_consent
    )


def _consented(db: Session, document_id: int) -> bool:
    db.expire_all()
    document = db.get(Book, document_id)
    return bool(document and tagging_enabled(document))


def chunk_ids_of(document: Book) -> list[int]:
    """Every taggable chunk of a document, in reading order."""
    return [
        ms.id
        for chapter in sorted(document.chapters, key=lambda c: c.index)
        if chapter.section_kind in READABLE_KINDS
        for ms in sorted(chapter.micro_sessions, key=lambda m: m.index)
    ]


def purge(db: Session, document: Book) -> int:
    """Consent withdrawn: delete every tag and queue row for this document."""
    ids = chunk_ids_of(document)
    chapter_ids = [c.id for c in document.chapters]
    removed = 0
    if ids:
        removed = (
            db.query(ResearchTag)
            .filter(ResearchTag.micro_session_id.in_(ids))
            .delete(synchronize_session=False)
        )
        db.query(ResearchTagging).filter(ResearchTagging.micro_session_id.in_(ids)).delete(
            synchronize_session=False
        )
    if chapter_ids:
        db.query(SectionKeyPoints).filter(SectionKeyPoints.chapter_id.in_(chapter_ids)).delete(
            synchronize_session=False
        )
    db.commit()
    return removed


# ---------------------------------------------------------------------------
# storing tags
# ---------------------------------------------------------------------------


def needs_tagging(db: Session, chunk_id: int) -> bool:
    """A chunk is tagged once, for good."""
    row = db.get(ResearchTagging, chunk_id)
    return not (row is not None and row.status == DONE)


def _set_status(db: Session, chunk_id: int, status: str, error: str | None) -> None:
    row = db.get(ResearchTagging, chunk_id)
    if row is None:
        row = ResearchTagging(micro_session_id=chunk_id)
        db.add(row)
    row.status = status
    row.model = settings.llm_model
    row.prompt_version = PROMPT_VERSION
    row.tag_list_version = TAG_LIST_VERSION
    row.error = error
    row.claimed_at = None


def tag_chunk(db: Session, chunk: MicroSession, *, client, ask=None, source: str = "llm") -> str:
    """Tag one chunk. Returns "done" or "failed"; never raises for model
    problems. On failure any earlier tags are left alone."""
    if source == "llm" and not needs_tagging(db, chunk.id):
        return DONE
    call = ask or globals()["provider"]
    try:
        pairs = parse_reply(call(client, chunk.text))
    except ThemeReplyError as err:
        # Only the validation reason is kept - never the reply, never the text.
        _set_status(db, chunk.id, FAILED, f"invalid reply: {err}"[:200])
        db.commit()
        return FAILED
    except ThemeProviderError as err:
        _set_status(db, chunk.id, FAILED, f"model unavailable: {err}"[:200])
        db.commit()
        return FAILED

    db.query(ResearchTag).filter(
        ResearchTag.micro_session_id == chunk.id, ResearchTag.source == source
    ).delete(synchronize_session=False)
    for tag, score in pairs:
        db.add(
            ResearchTag(
                micro_session_id=chunk.id,
                tag=tag,
                score=score,
                source=source,
                model=settings.llm_model,
                prompt_version=PROMPT_VERSION,
                tag_list_version=TAG_LIST_VERSION,
            )
        )
    _set_status(db, chunk.id, DONE, None)
    db.commit()
    return DONE


# ---------------------------------------------------------------------------
# the queue
# ---------------------------------------------------------------------------


def plan_queue(db: Session, document: Book) -> list[int]:
    """Chunks still wanting tags, skipping ones in flight or lately failed."""
    now = _now()
    plan: list[int] = []
    for chunk_id in chunk_ids_of(document):
        row = db.get(ResearchTagging, chunk_id)
        if row is not None:
            if row.status == DONE:
                continue
            if row.status == RUNNING and row.claimed_at and now - row.claimed_at < CLAIM_TTL:
                continue
            if row.status == FAILED and row.updated_at and now - row.updated_at < FAIL_COOLDOWN:
                continue
        plan.append(chunk_id)
    return plan


def claim(db: Session, ids: list[int], stamp: dt.datetime | None = None) -> list[int]:
    """Atomically mark chunks as running; returns the ones this caller won."""
    now = stamp or _now()
    won: list[int] = []
    table = ResearchTagging.__table__
    for chunk_id in ids:
        stmt = (
            insert(ResearchTagging)
            .values(
                micro_session_id=chunk_id,
                status=RUNNING,
                model=settings.llm_model,
                prompt_version=PROMPT_VERSION,
                tag_list_version=TAG_LIST_VERSION,
                claimed_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[table.c.micro_session_id],
                set_={"status": RUNNING, "claimed_at": now, "updated_at": now, "error": None},
                where=not_(table.c.status == DONE)
                & not_(and_(table.c.status == RUNNING, table.c.claimed_at > now - CLAIM_TTL)),
            )
            .returning(table.c.micro_session_id)
        )
        if db.execute(stmt).first() is not None:
            won.append(chunk_id)
    db.commit()
    return won


def mark_queued(db: Session, ids: list[int]) -> int:
    """Put chunks in the queue so the reader can see work is pending.

    Done before any model call, so the status indicator is truthful from the
    moment the request returns rather than only once a worker picks it up.
    """
    now = _now()
    table = ResearchTagging.__table__
    queued = 0
    for chunk_id in ids:
        stmt = (
            insert(ResearchTagging)
            .values(
                micro_session_id=chunk_id,
                status=QUEUED,
                model=settings.llm_model,
                prompt_version=PROMPT_VERSION,
                tag_list_version=TAG_LIST_VERSION,
                claimed_at=None,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[table.c.micro_session_id],
                set_={"status": QUEUED, "updated_at": now, "error": None, "claimed_at": None},
                where=not_(table.c.status == DONE)
                & not_(and_(table.c.status == RUNNING, table.c.claimed_at > now - CLAIM_TTL)),
            )
            .returning(table.c.micro_session_id)
        )
        if db.execute(stmt).first() is not None:
            queued += 1
    db.commit()
    return queued


def run_queue(document_id: int, *, ask=None, sleep=time.sleep, client=None, limit: int | None = None) -> None:
    """Work through a document's queue. Runs in the background; never raises.

    Resumable by construction: the queue lives in the database, each chunk is
    claimed atomically before it is sent anywhere, and a claim expires so a
    crashed run cannot leave a chunk stuck.
    """
    with _document_lock(document_id):
        _run_queue(document_id, ask=ask, sleep=sleep, client=client, limit=limit)


def _run_queue(document_id: int, *, ask, sleep, client, limit) -> None:
    db = SessionLocal()
    own_client = client is None
    try:
        if not _consented(db, document_id):
            return
        document = db.get(Book, document_id)
        if document is None:
            return
        pending = plan_queue(db, document)
        if limit is not None:
            pending = pending[:limit]
        if not pending:
            return
        if own_client:
            client = themes.make_client()

        for chunk_id in pending:
            if not _consented(db, document_id):
                document = db.get(Book, document_id)
                if document is not None:
                    purge(db, document)
                return
            if not claim(db, [chunk_id]):
                continue  # another run has it
            chunk = db.get(MicroSession, chunk_id)
            if chunk is None:
                continue
            tag_chunk(db, chunk, client=client, ask=ask)
            if not _consented(db, document_id):  # withdrawn while the model worked
                document = db.get(Book, document_id)
                if document is not None:
                    purge(db, document)
                return
            sleep(settings.theme_call_gap_seconds)
    except ThemeProviderError as err:
        log.warning("research tagging could not start: %s", err)
        _release_running(db, document_id)
    except Exception as err:  # noqa: BLE001 - background work must never surface
        log.warning("research tagging stopped: %s", type(err).__name__)
        _release_running(db, document_id)
    finally:
        db.close()
        if own_client and client is not None:
            client.close()


def _release_running(db: Session, document_id: int) -> None:
    """Put this document's in-flight claims back in the queue."""
    try:
        db.rollback()
        document = db.get(Book, document_id)
        if document is None:
            return
        ids = chunk_ids_of(document)
        if ids:
            db.query(ResearchTagging).filter(
                ResearchTagging.micro_session_id.in_(ids),
                ResearchTagging.status == RUNNING,
            ).update({"status": QUEUED, "claimed_at": None}, synchronize_session=False)
            db.commit()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# what the reader sees
# ---------------------------------------------------------------------------


def tags_for_chunks(db: Session, document: Book, chunk_ids: list[int]) -> list[ResearchChunkTagsOut]:
    """Shown tags for these chunks, strongest first.

    There is no spoiler rule here, unlike the novel themes: a paper has no plot
    to give away, and a researcher skimming to the Results section is using the
    tool as intended.
    """
    if not chunk_ids or not tagging_enabled(document):
        return []
    rows = (
        db.query(ResearchTag)
        .filter(
            ResearchTag.micro_session_id.in_(chunk_ids),
            ResearchTag.score >= MIN_SHOWN_SCORE,
        )
        .all()
    )
    grouped: dict[int, list[ResearchTag]] = {}
    for row in rows:
        grouped.setdefault(row.micro_session_id, []).append(row)
    out: list[ResearchChunkTagsOut] = []
    for chunk_id in chunk_ids:
        found = sorted(grouped.get(chunk_id, []), key=lambda r: -r.score)
        if not found:
            continue
        out.append(
            ResearchChunkTagsOut(
                micro_session_id=chunk_id,
                tags=[
                    ResearchTagOut(tag=r.tag, label=RESEARCH_TAGS[r.tag], score=r.score)
                    for r in found
                    if r.tag in RESEARCH_TAGS
                ],
            )
        )
    return out


def queue_status(db: Session, document: Book) -> ResearchTagStatusOut:
    """Counts behind the visible status indicator."""
    ids = chunk_ids_of(document)
    status = ResearchTagStatusOut(enabled=tagging_enabled(document), total=len(ids))
    if not ids:
        status.message = "This document has no taggable sections."
        return status

    rows = (
        db.query(ResearchTagging)
        .filter(ResearchTagging.micro_session_id.in_(ids))
        .all()
    )
    by_status = {QUEUED: 0, RUNNING: 0, DONE: 0, FAILED: 0}
    for row in rows:
        if row.status in by_status:
            by_status[row.status] += 1
    status.queued = by_status[QUEUED]
    status.running = by_status[RUNNING]
    status.done = by_status[DONE]
    status.failed = by_status[FAILED]
    status.untagged = len(ids) - len(rows)

    if not status.enabled:
        if (document.source_type or "") != "research":
            status.message = "Tagging applies to research documents only."
        elif not document.theme_tagging_consent:
            status.message = "Tagging is off: you have not given consent for this document."
        else:
            status.message = "Tagging is switched off on this server."
    elif status.running:
        status.message = f"Tagging {status.running} of {status.total} sections now."
    elif status.queued:
        status.message = f"{status.queued} sections queued."
    elif status.done == status.total:
        status.message = "All sections tagged."
    elif status.failed:
        status.message = f"{status.failed} sections could not be tagged; they will be retried."
    else:
        status.message = f"{status.done} of {status.total} sections tagged."
    return status


# ---------------------------------------------------------------------------
# key points
# ---------------------------------------------------------------------------


def key_points_messages(text: str) -> list[dict]:
    system = (
        f"Summarise this section of an academic document as at most {MAX_KEY_POINTS} "
        "short key points. Use only what the text says: do not add context, do not "
        "infer results it does not state, and do not explain the field. If the "
        "section is too short or says too little to summarise, reply with an empty "
        'list. Reply with JSON only: {"points":["...","..."]}.'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def key_points_schema() -> dict:
    return {
        "name": "section_key_points",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "points": {
                    "type": "array",
                    "maxItems": MAX_KEY_POINTS,
                    "items": {"type": "string"},
                }
            },
            "required": ["points"],
            "additionalProperties": False,
        },
    }


def parse_key_points(content: str | None) -> list[str]:
    if not isinstance(content, str) or not content.strip():
        raise ThemeReplyError("empty reply")
    try:
        data = json.loads(_strip_fence(content))
    except ValueError as err:
        raise ThemeReplyError("reply is not JSON") from err
    points = data.get("points") if isinstance(data, dict) else None
    if not isinstance(points, list):
        raise ThemeReplyError("reply has no points list")
    out: list[str] = []
    for point in points[:MAX_KEY_POINTS]:
        if not isinstance(point, str):
            raise ThemeReplyError("a point is not a string")
        cleaned = " ".join(point.split())[:MAX_KEY_POINT_CHARS].strip()
        if cleaned:
            out.append(cleaned)
    return out


def _key_points_payload(config, text: str) -> dict:
    if config.provider == "ollama":
        return {
            "model": config.model,
            "messages": key_points_messages(text),
            "stream": False,
            "format": key_points_schema()["schema"],
            "options": {"temperature": 0.1, "num_predict": 700},
        }
    return {
        "model": config.model,
        "messages": key_points_messages(text),
        "temperature": 0.1,
        "max_tokens": 700,
        "response_format": {"type": "json_schema", "json_schema": key_points_schema()},
    }


def ask_key_points(client, text: str) -> str:
    return themes.call_model(client, text, payload_for=_key_points_payload)


key_points_provider = ask_key_points


def key_points_for(db: Session, section: Chapter) -> KeyPointsOut | None:
    """The stored key points for a section, or None when the feature is off."""
    if not settings.research_key_points_on_demand:
        return None
    row = db.get(SectionKeyPoints, section.id)
    if row is None:
        return KeyPointsOut(status="none")
    return KeyPointsOut(status=row.status, text=row.text or "", model=row.model or "")


def generate_key_points(section_id: int, *, ask=None, client=None) -> None:
    """Generate key points for one section, in the background.

    A failed call stores nothing. Showing an empty panel is correct; showing an
    invented summary of a paper the reader is about to cite is not.
    """
    db = SessionLocal()
    own_client = client is None
    try:
        section = db.get(Chapter, section_id)
        if section is None:
            return
        document = db.get(Book, section.book_id)
        if document is None or not tagging_enabled(document):
            return

        row = db.get(SectionKeyPoints, section_id)
        if row is None:
            row = SectionKeyPoints(chapter_id=section_id, status=RUNNING)
            db.add(row)
        row.status = RUNNING
        row.claimed_at = _now()
        row.model = settings.llm_model
        row.prompt_version = PROMPT_VERSION
        row.error = None
        db.commit()

        if own_client:
            client = themes.make_client()
        call = ask or globals()["key_points_provider"]
        try:
            points = parse_key_points(call(client, section.text))
        except (ThemeReplyError, ThemeProviderError) as err:
            row.status = FAILED
            row.text = ""
            row.error = str(err)[:200]
            row.claimed_at = None
            db.commit()
            return

        row.status = DONE
        row.text = "\n".join(points)
        row.error = None
        row.claimed_at = None
        db.commit()
    except Exception as err:  # noqa: BLE001 - background work must never surface
        log.warning("key points stopped: %s", type(err).__name__)
        db.rollback()
    finally:
        db.close()
        if own_client and client is not None:
            client.close()
