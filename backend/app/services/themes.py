"""Theme tagging: label a reading chunk with themes from a closed list.

The only place that talks to an LLM for themes. It is used by the offline batch
script (scripts/tag_themes.py) and by the background worker for consented
uploads (services/theme_worker.py); the running request path only reads the
stored tags. Replies are validated hard: nothing outside the closed list, no
more than 3 themes, scores 1 to 5, or it is not stored.
"""

import json
import logging
import math
import time
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Book,
    Chapter,
    MicroSession,
    MicroSessionTagging,
    MicroSessionTheme,
    ReadingSession,
    User,
    UserBookProgress,
)
from app.services.progression import build_block, ordered_micro_sessions

log = logging.getLogger(__name__)

THEMES: dict[str, str] = {
    "mystery_detection": "Mystery & detection",
    "romance": "Romance & courtship",
    "grief_loss_death": "Grief, loss & death",
    "fear_supernatural": "Fear & the supernatural",
    "adventure_travel": "Adventure & travel",
    "war_conflict": "War & conflict",
    "family_childhood": "Family & childhood",
    "class_money": "Class & money",
    "gender_womens_roles": "Gender & women's roles",
    "justice_morality": "Justice & morality",
    "nature_place": "Nature & place",
    "identity_self": "Identity & self",
    "humour_satire": "Humour & satire",
    "madness_mind": "Madness & the mind",
}
THEME_LIST_VERSION = 1
PROMPT_VERSION = 1
MIN_SHOWN_SCORE = 3
MAX_THEMES = 3

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_ATTEMPTS = 5
MAX_WAIT_SECONDS = 60.0  # longer waits (a daily limit) are not worth holding a worker for
_sleep = time.sleep  # tests replace this


class ThemeReplyError(ValueError):
    """The model's reply is not a valid tagging."""


class ThemeProviderError(RuntimeError):
    """The model could not be reached or kept failing."""


# --------------------------------------------------------------------------
# prompt, schema, validation
# --------------------------------------------------------------------------


def build_messages(text: str) -> list[dict]:
    listing = "; ".join(f"{theme_id} ({label})" for theme_id, label in THEMES.items())
    system = (
        "You label passages of novels with themes. Choose at most "
        f"{MAX_THEMES} themes from this closed list, and only themes the passage clearly deals "
        f"with: {listing}. Score each from 1 (slight) to 5 (central to the passage). "
        "Judge only the passage you are given, not the book it comes from. "
        'Reply with JSON only: {"themes":[{"theme":"<id>","score":<1-5>}]}. '
        'If no theme clearly applies, reply {"themes":[]}.'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def response_schema() -> dict:
    return {
        "name": "passage_themes",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "themes": {
                    "type": "array",
                    "maxItems": MAX_THEMES,
                    "items": {
                        "type": "object",
                        "properties": {
                            "theme": {"type": "string", "enum": list(THEMES)},
                            "score": {"type": "integer", "minimum": 1, "maximum": 5},
                        },
                        "required": ["theme", "score"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["themes"],
            "additionalProperties": False,
        },
    }


def parse_reply(content: str | None) -> list[tuple[str, int]]:
    """Validate a model reply; return [(theme, score)] or raise ThemeReplyError."""
    if not isinstance(content, str) or not content.strip():
        raise ThemeReplyError("empty reply")
    text = content.strip()
    if text.startswith("```"):  # some models fence the JSON despite being told not to
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(text)
    except ValueError as err:
        raise ThemeReplyError("reply is not JSON") from err
    items = data.get("themes") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ThemeReplyError("reply has no themes list")
    out: list[tuple[str, int]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ThemeReplyError("theme entry is not an object")
        theme, score = item.get("theme"), item.get("score")
        if theme not in THEMES:
            raise ThemeReplyError("theme is not in the list")
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
            raise ThemeReplyError("score is not an integer from 1 to 5")
        if theme in seen:
            raise ThemeReplyError("duplicate theme")
        seen.add(theme)
        out.append((theme, score))
    # Some models list more than asked; keep the strongest (ties keep the model's order).
    return sorted(out, key=lambda pair: -pair[1])[:MAX_THEMES]


# --------------------------------------------------------------------------
# the model call
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    url: str
    api_key: str
    model: str

    @property
    def key_name(self) -> str:
        return "OLLAMA_API_KEY" if self.provider == "ollama" else "OP_API_KEY"

    @property
    def model_name(self) -> str:
        return "OLLAMA_MODEL" if self.provider == "ollama" else "OP_MODEL"


def current_config(provider: str | None = None) -> LLMConfig:
    """The provider settings in effect (``provider`` overrides LLM_PROVIDER)."""
    provider = provider or settings.llm_provider
    if provider == "ollama":
        return LLMConfig("ollama", settings.ollama_url, settings.ollama_api_key, settings.ollama_model)
    return LLMConfig("openrouter", OPENROUTER_URL, settings.op_api_key, settings.op_model)


def make_client(config: LLMConfig | None = None) -> httpx.Client:
    config = config or current_config()
    if not config.api_key:
        raise ThemeProviderError(f"{config.key_name} is not set")
    if not config.model:
        raise ThemeProviderError(f"{config.model_name} is not set")
    return httpx.Client(
        headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
        timeout=120,
    )


def _payload(config: LLMConfig, text: str) -> dict:
    if config.provider == "ollama":
        # Ollama's own chat API: the JSON schema goes in "format".
        return {
            "model": config.model,
            "messages": build_messages(text),
            "stream": False,
            "format": response_schema()["schema"],
            "options": {"temperature": 0.1, "num_predict": 1500},
        }
    return {
        "model": config.model,
        "messages": build_messages(text),
        "temperature": 0.1,
        "max_tokens": 1500,
        "response_format": {"type": "json_schema", "json_schema": response_schema()},
    }


def _content_of(body) -> str:
    """The reply text from either provider's response body."""
    if isinstance(body, dict) and isinstance(body.get("message"), dict):
        return body["message"]["content"]
    return body["choices"][0]["message"]["content"]


def call_model(
    client: httpx.Client,
    text: str,
    config: LLMConfig | None = None,
    payload_for=None,
) -> str:
    """One chat completion; returns the reply content. Retries rate limits,
    server errors and dropped connections with backoff, then raises
    ThemeProviderError. Never puts the key or the passage in an error or log.

    ``payload_for`` is the request builder, defaulting to theme tagging. The
    research tagger passes its own so that the transport - backoff, Retry-After
    handling, both providers response shapes - has one implementation rather
    than two.
    """
    config = config or current_config()
    payload = (payload_for or _payload)(config, text)
    last = "no attempt"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        wait = min(5.0 * attempt, 30.0)
        try:
            resp = client.post(config.url, json=payload)
        except httpx.TransportError as err:
            last = f"network error ({type(err).__name__})"
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last = f"HTTP {resp.status_code}"
                try:
                    asked = float(resp.headers.get("retry-after", ""))
                except ValueError:
                    asked = None
                if asked is not None and math.isfinite(asked) and asked >= 0:
                    if asked > MAX_WAIT_SECONDS:
                        raise ThemeProviderError(f"{last}, retry wanted after {int(asked)}s")
                    wait = asked
            elif resp.status_code != 200:
                raise ThemeProviderError(f"HTTP {resp.status_code}")
            else:
                try:
                    body = resp.json()
                except ValueError as err:
                    raise ThemeProviderError("unexpected response shape") from err
                if isinstance(body, dict) and body.get("error") and not (body.get("choices") or body.get("message")):
                    last = "provider error in a 200 reply"  # upstream failure; worth another try
                else:
                    try:
                        return _content_of(body)
                    except (KeyError, IndexError, TypeError) as err:
                        raise ThemeProviderError("unexpected response shape") from err
        if attempt < MAX_ATTEMPTS:
            _sleep(wait)
    log.warning("theme model gave up after %s attempts: %s", MAX_ATTEMPTS, last)
    raise ThemeProviderError(f"gave up after {MAX_ATTEMPTS} attempts ({last})")


provider = call_model  # tests and callers may pass their own


# --------------------------------------------------------------------------
# storing tags
# --------------------------------------------------------------------------


def needs_tagging(db: Session, micro_session_id: int) -> bool:
    """A chunk is tagged once, for good. Whatever model or prompt made its tags,
    a finished chunk is never queued again; only never-tagged and failed chunks
    are. (Theme ids are append-only, so old tags always stay valid.)"""
    row = db.get(MicroSessionTagging, micro_session_id)
    return not (row is not None and row.status == "done")


def _set_tagging(db: Session, micro_session_id: int, status: str, error: str | None) -> None:
    row = db.get(MicroSessionTagging, micro_session_id)
    if row is None:
        row = MicroSessionTagging(micro_session_id=micro_session_id)
        db.add(row)
    row.status = status
    row.model = settings.llm_model
    row.prompt_version = PROMPT_VERSION
    row.theme_list_version = THEME_LIST_VERSION
    row.error = error
    row.claimed_at = None


def tag_chunk(db: Session, micro_session: MicroSession, *, client, provider=None, source: str = "llm") -> str:
    """Tag one chunk. Returns "done" or "failed"; never raises for model
    problems. On failure the earlier tags (if any) are left alone."""
    if source == "llm" and not needs_tagging(db, micro_session.id):
        return "done"  # tags are permanent: never ask again, never overwrite
    ask = provider or globals()["provider"]
    try:
        pairs = parse_reply(ask(client, micro_session.text))
    except ThemeReplyError as err:
        # Only the validation reason is kept, never the model's reply or the passage.
        _set_tagging(db, micro_session.id, "failed", f"invalid reply: {err}"[:200])
        db.commit()
        return "failed"
    except (ThemeProviderError, httpx.HTTPError) as err:
        _set_tagging(db, micro_session.id, "failed", f"model unavailable: {err}"[:200])
        db.commit()
        return "failed"

    db.query(MicroSessionTheme).filter(
        MicroSessionTheme.micro_session_id == micro_session.id,
        MicroSessionTheme.source == source,
    ).delete(synchronize_session=False)
    for theme, score in pairs:
        db.add(
            MicroSessionTheme(
                micro_session_id=micro_session.id,
                theme=theme,
                score=score,
                source=source,
                model=settings.llm_model,
                prompt_version=PROMPT_VERSION,
                theme_list_version=THEME_LIST_VERSION,
            )
        )
    _set_tagging(db, micro_session.id, "done", None)
    db.commit()
    return "done"


# --------------------------------------------------------------------------
# what a reader may see
# --------------------------------------------------------------------------


def tagging_enabled(db: Session, user: User, book: Book) -> bool:
    """Is on-demand tagging switched on for this reader and book? Only for the
    owner's own upload, and only with their consent. Seeded books ship with their
    tags and are never tagged on demand, and a research document is tagged from
    its own list by services/research_tags - never from the literary one."""
    if (book.source_type or "") == "research":
        return False
    return bool(book.is_user_uploaded and book.theme_tagging_consent and book.owner_user_id == user.id)


def reached_micro_session_ids(db: Session, user: User, book: Book) -> set[int]:
    """Chunks the reader has reached: everything up to and including the block
    they are on, or their furthest completed session, whichever is later. Tags
    on later chunks could give the plot away, so nothing beyond is ever shown."""
    ordered = ordered_micro_sessions(book)
    if not ordered:
        return set()
    order_of = {ms.id: i for i, ms in enumerate(ordered)}

    progress = (
        db.query(UserBookProgress)
        .filter(UserBookProgress.user_id == user.id, UserBookProgress.book_id == book.id)
        .first()
    )
    anchors: list[int] = []
    if progress and progress.current_micro_session_id in order_of:
        anchors.append(progress.current_micro_session_id)
    else:
        anchors.append(ordered[0].id)  # not started: only the opening chunk

    completed = [
        (row[0], row[1] or 0)
        for row in db.query(ReadingSession.micro_session_id, ReadingSession.words_read).filter(
            ReadingSession.user_id == user.id,
            ReadingSession.book_id == book.id,
            ReadingSession.completed.is_(True),
            ReadingSession.micro_session_id.isnot(None),
        )
        if row[0] in order_of
    ]
    size = max(1, user.session_size_level or 1)
    furthest = 0
    # A finished session covers as many chunks as the words the reader actually
    # read, which stays true if their session size has changed since.
    for start_id, words_read in completed:
        start = order_of[start_id]
        if words_read <= 0:
            anchors.append(start_id)  # no record of the extent: assume today's size
            continue
        end, total = start, ordered[start].word_count
        while total < words_read and end + 1 < len(ordered):
            end += 1
            total += ordered[end].word_count
        furthest = max(furthest, end)
    for anchor in anchors:
        block, _ = build_block(ordered, anchor, size)
        end = order_of[block[-1].id] if block else order_of[anchor]
        furthest = max(furthest, end)
    return {ms.id for ms in ordered[: furthest + 1]}
