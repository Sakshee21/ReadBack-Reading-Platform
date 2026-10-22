import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    current_streak: int
    longest_streak: int
    last_read_date: dt.date | None

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class BookOut(BaseModel):
    id: int
    gutenberg_id: int | None = None
    title: str
    author: str
    total_word_count: int
    chapter_count: int
    theme: str = "parchment"
    is_user_uploaded: bool = False
    source_type: str = "seeded"
    status: str = "ready"
    failure_reason: str | None = None
    theme_tagging_consent: bool = False
    published_year: int | None = None
    theme_tagging_enabled: bool = False  # on-demand tagging is on (an upload with its owner's consent)

    class Config:
        from_attributes = True


class BookStatusOut(BaseModel):
    """Polled by the frontend while a newly uploaded book is converting."""

    id: int
    status: str
    failure_reason: str | None = None
    title: str
    chapter_count: int = 0
    micro_session_count: int = 0
    total_word_count: int = 0


class MicroSessionPart(BaseModel):
    """One micro-session inside a served block. Highlights attach to these,
    not to the merged block, so each keeps its own text offsets."""

    id: int
    text: str


class MicroSessionOut(BaseModel):
    id: int
    index: int
    text: str
    word_count: int
    is_cliffhanger_break: bool
    has_visualization_prompt: bool
    parts: list[MicroSessionPart] = []

    class Config:
        from_attributes = True


class MicroSessionListItemOut(BaseModel):
    id: int
    session_number: int
    chapter_index: int
    chapter_title: str
    preview: str
    completed: bool
    is_current: bool


class JumpRequest(BaseModel):
    micro_session_id: int


class ChapterOut(BaseModel):
    id: int
    index: int
    title: str
    word_count: int
    micro_session_count: int

    class Config:
        from_attributes = True


class ReaderPositionOut(BaseModel):
    book: BookOut
    micro_session: MicroSessionOut
    chapter_id: int
    chapter_index: int
    chapter_title: str
    is_first_in_book: bool
    recap: str | None
    checkpoint_due: "CheckpointOut | None"
    progress_pct: float


class SessionStart(BaseModel):
    book_id: int
    micro_session_id: int


class SessionOut(BaseModel):
    id: int
    book_id: int
    chapter_id: int
    micro_session_id: int | None
    started_at: dt.datetime
    ended_at: dt.datetime | None
    words_read: int
    completed: bool

    class Config:
        from_attributes = True


class SessionComplete(BaseModel):
    session_id: int


class NextSessionOut(BaseModel):
    finished_book: bool
    next_micro_session: MicroSessionOut | None
    checkpoint_due: "CheckpointOut | None"
    streak: "StreakOut"
    session_size_level: int
    session_size_changed: bool


class CheckpointOut(BaseModel):
    id: int
    book_id: int
    chapter_index_trigger: int
    questions: list[dict]

    class Config:
        from_attributes = True


class CheckpointSubmit(BaseModel):
    checkpoint_id: int
    # str for inference, list[str] for sequencing, dict[str, str] for relationship
    answers: dict[str, Any]


class CheckpointResultOut(BaseModel):
    checkpoint_id: int
    score: float
    correct: int
    total: int


class StreakOut(BaseModel):
    current_streak: int
    longest_streak: int
    last_read_date: dt.date | None


class ProgressOut(BaseModel):
    book_id: int
    words_read: int
    total_words: int
    progress_pct: float


class NudgeOut(BaseModel):
    kind: str | None
    message: str | None
    book_id: int | None
    book_title: str | None
    days_away: int


class PaceOut(BaseModel):
    wpm_recent: float | None
    wpm_average: float | None
    sessions_counted: int
    trend: str
    is_estimate: bool
    words_left: int | None = None
    minutes_left_book: float | None = None


class EventIn(BaseModel):
    event_type: str
    book_id: int | None = None
    chapter_id: int | None = None
    micro_session_id: int | None = None
    metadata: dict | None = None


ReaderPositionOut.model_rebuild()
NextSessionOut.model_rebuild()


# --- Highlights ---------------------------------------------------------------

HighlightColor = Literal["yellow", "green", "blue", "pink", "orange", "purple"]
MAX_HIGHLIGHT_CHARS = 2000
MAX_HIGHLIGHT_COMMENT = 2000


class HighlightIn(BaseModel):
    micro_session_id: int
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    color: HighlightColor
    comment: str | None = Field(default=None, max_length=MAX_HIGHLIGHT_COMMENT)

    @field_validator("comment")
    @classmethod
    def _blank_comment_is_none(cls, value):
        return (value.strip() or None) if value is not None else None

    @model_validator(mode="after")
    def _range_is_sane(self):
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if self.end - self.start > MAX_HIGHLIGHT_CHARS:
            raise ValueError(f"a highlight can be at most {MAX_HIGHLIGHT_CHARS} characters")
        return self


class HighlightPatch(BaseModel):
    color: HighlightColor | None = None
    comment: str | None = Field(default=None, max_length=MAX_HIGHLIGHT_COMMENT)

    @field_validator("comment")
    @classmethod
    def _blank_comment_is_none(cls, value):
        return (value.strip() or None) if value is not None else None

    @model_validator(mode="after")
    def _colour_cannot_be_cleared(self):
        if "color" in self.model_fields_set and self.color is None:
            raise ValueError("color cannot be null")
        return self


class ThemeRef(BaseModel):
    theme: str
    label: str


class HighlightOut(BaseModel):
    id: int
    book_id: int
    micro_session_id: int
    chapter_index: int
    chapter_title: str
    session_index: int
    # The reader-facing "Session N", the same numbering as the Sessions drawer;
    # null only for a passage outside the readable story (front/back matter).
    session_number: int | None
    start: int
    end: int
    quote: str
    context_before: str
    context_after: str
    color: str
    comment: str | None
    # Themes of the passage (score 3 or more, best first), for citing and export.
    themes: list[ThemeRef] = []
    created_at: dt.datetime
    updated_at: dt.datetime


# ---------------------------------------------------------------------------
# Research documents
#
# A separate track from the reading-habit pilot: papers and textbooks, read by
# section, private to the uploader. Every metadata field is optional because a
# document that does not state its year must come back blank rather than
# guessed - the uploader fills those in by hand.
# ---------------------------------------------------------------------------

ResearchDocKind = Literal["paper", "textbook"]
ResearchSectionKind = Literal["abstract", "body", "references", "appendix", "front_matter"]


class ResearchMetadataIn(BaseModel):
    """Metadata the uploader supplies or corrects. Blank means "leave as is"."""

    title: str | None = Field(default=None, max_length=500)
    authors: str | None = Field(default=None, max_length=255)
    year: int | None = Field(default=None, ge=1400, le=2200)
    venue: str | None = Field(default=None, max_length=300)
    doi: str | None = Field(default=None, max_length=200)

    no_date: bool | None = None

    @field_validator("title", "authors", "venue", "doi")
    @classmethod
    def _blank_is_none(cls, value):
        return (value.strip() or None) if value is not None else None


class ResearchSectionOut(BaseModel):
    id: int
    index: int
    title: str
    kind: ResearchSectionKind
    word_count: int
    chunk_count: int
    # Whether this section is part of the reading flow. References and the
    # title block are stored and viewable but not read through.
    readable: bool


class ResearchDocumentOut(BaseModel):
    id: int
    title: str
    authors: str
    doc_kind: ResearchDocKind | None
    year: int | None
    venue: str | None
    doi: str | None
    page_count: int | None
    word_count: int
    section_count: int
    status: str
    failure_reason: str | None = None
    tagging_consent: bool
    tagging_enabled: bool
    # Fields a citation needs that are blank or still only a guess. The panel
    # names them and the citation shows a placeholder, so a wrong citation
    # cannot be copied into a paper without the gap being visible.
    needs_review: list[str] = []
    unverified: list[str] = []
    # Set by the uploader to say the document genuinely has no date, which is
    # the only thing that turns a missing year into a citable "n.d.".
    no_date: bool = False
    created_at: dt.datetime | None = None


class ResearchDocumentDetailOut(ResearchDocumentOut):
    sections: list[ResearchSectionOut] = []
    captions: list[str] = []
    # What the extractor could not do with this document, verbatim.
    warnings: list[str] = []


class ResearchChunkOut(BaseModel):
    id: int
    index: int
    text: str
    word_count: int


class ResearchTagOut(BaseModel):
    tag: str
    label: str
    score: int


class ResearchChunkTagsOut(BaseModel):
    micro_session_id: int
    tags: list[ResearchTagOut] = []


class KeyPointsOut(BaseModel):
    status: Literal["none", "queued", "running", "done", "failed"]
    # Always presented as machine-generated in the UI; empty unless done.
    text: str = ""
    model: str = ""


class ResearchSectionReadOut(BaseModel):
    """One whole section, the unit the research reader shows."""

    document_id: int
    section: ResearchSectionOut
    chunks: list[ResearchChunkOut]
    previous_section_id: int | None = None
    next_section_id: int | None = None
    tags: list[ResearchChunkTagsOut] = []
    key_points: KeyPointsOut | None = None


class ResearchTagStatusOut(BaseModel):
    """Queue state for a document, for the visible status indicator."""

    enabled: bool
    queued: int = 0
    running: int = 0
    done: int = 0
    failed: int = 0
    untagged: int = 0
    total: int = 0
    message: str = ""


class ConsentIn(BaseModel):
    consent: bool
