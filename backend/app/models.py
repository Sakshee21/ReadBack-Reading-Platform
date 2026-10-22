import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_read_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # Progressive session length: 1 = single micro-session, 2/3 = that many
    # merged at read time once the user has completed enough sessions.
    session_size_level: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    progress: Mapped[list["UserBookProgress"]] = relationship(back_populates="user")
    sessions: Mapped[list["ReadingSession"]] = relationship(back_populates="user")


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Null for user uploads, which have no Gutenberg origin.
    gutenberg_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    # Year of first publication, used in citations. Null for uploads.
    published_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    total_word_count: Mapped[int] = mapped_column(Integer, default=0)

    # Ownership. A null owner means a shared seeded book that everyone sees;
    # anything else is private to that user. Enforced by deps.book_for_user,
    # which 404s rather than 403s so ids can't be probed.
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    is_user_uploaded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # seeded | gutenberg | upload - carried into the events CSV so uploaded
    # books can be excluded from pilot analysis.
    source_type: Mapped[str] = mapped_column(String(16), default="seeded", server_default="seeded")
    # ready | processing | failed. Conversion runs in a background task, so an
    # uploaded book exists before its chapters do.
    status: Mapped[str] = mapped_column(String(16), default="ready", server_default="ready")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Decorative mood tint only - never scene imagery. Must be one of the
    # themes defined in frontend/src/styles/themes.css; tests check that every
    # theme keeps text contrast at WCAG AA.
    theme: Mapped[str] = mapped_column(String(32), default="parchment", server_default="parchment")
    # Uploads only: the owner agreed that the text may be sent to an AI service
    # to tag passages with themes. Without it the tagging code never reads the book.
    theme_tagging_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    theme_tagging_consent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    # --- research documents only (source_type == "research") ---------------
    # paper | textbook. Null for everything in the reading-habit track.
    doc_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Citation fields the research extractor reads out of the document, or that
    # the owner corrects by hand. Null means "not found", never a guess.
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # {"captions": [...], "warnings": [...]} from the extractor, kept so the
    # document page can be honest about what it could not handle.
    research_notes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="book", order_by="Chapter.index", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("book_id", "index", name="uq_chapter_book_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    is_cliffhanger_break: Mapped[bool] = mapped_column(Boolean, default=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    # Recap cache, all generated offline at seed time - never at request time.
    # recap_source records which of manual/llm/extractive the effective recap
    # comes from; see services/recap.effective_recap for the precedence.
    recap_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    story_so_far: Mapped[str | None] = mapped_column(Text, nullable=True)
    recap_source: Mapped[str] = mapped_column(
        String(16), default="extractive", server_default="extractive"
    )
    # story | front_matter | back_matter. Non-story sections are kept so they
    # can be inspected, but are excluded from the reading flow, progress and
    # word counts. Seeded books are all 'story'.
    section_kind: Mapped[str] = mapped_column(
        String(16), default="story", server_default="story"
    )

    book: Mapped["Book"] = relationship(back_populates="chapters")
    micro_sessions: Mapped[list["MicroSession"]] = relationship(
        back_populates="chapter", order_by="MicroSession.index", cascade="all, delete-orphan"
    )


class MicroSession(Base):
    """A ~2-3 minute reading chunk within a chapter (the `Segment` unit)."""

    __tablename__ = "micro_sessions"
    __table_args__ = (UniqueConstraint("chapter_id", "index", name="uq_microsession_chapter_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    is_cliffhanger_break: Mapped[bool] = mapped_column(Boolean, default=False)
    # Flags a "Picture this scene" checkpoint. There is no artwork: the reveal
    # was removed deliberately so nothing supplies the imagery the reader is
    # meant to generate (see CLAUDE.md section 8).
    has_visualization_prompt: Mapped[bool] = mapped_column(Boolean, default=False)

    chapter: Mapped["Chapter"] = relationship(back_populates="micro_sessions")


class ReadingSession(Base):
    __tablename__ = "reading_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    micro_session_id: Mapped[int | None] = mapped_column(ForeignKey("micro_sessions.id"), nullable=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    words_read: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="sessions")


class UserBookProgress(Base):
    __tablename__ = "user_book_progress"
    __table_args__ = (UniqueConstraint("user_id", "book_id", name="uq_progress_user_book"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    current_chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    current_micro_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("micro_sessions.id"), nullable=True
    )
    last_read_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="progress")
    book: Mapped["Book"] = relationship()


class ComprehensionCheckpoint(Base):
    __tablename__ = "comprehension_checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    chapter_index_trigger: Mapped[int] = mapped_column(Integer, nullable=False)
    questions: Mapped[list] = mapped_column(JSON, nullable=False)


class CheckpointAttempt(Base):
    __tablename__ = "checkpoint_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    checkpoint_id: Mapped[int] = mapped_column(ForeignKey("comprehension_checkpoints.id"), nullable=False)
    score: Mapped[float] = mapped_column(Integer, default=0)
    answered_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class ReadingEvent(Base):
    """Instrumentation log for the pilot. One row per user-facing interaction
    (session start/end, autoplay, recap, RSVP, visualization, quiz, streak).
    book/chapter/micro-session are nullable so events without a full reading
    context (e.g. a quiz answered between chapters) still log cleanly.

    The free-form payload column is named ``event_metadata`` because SQLAlchemy
    reserves the ``metadata`` attribute on declarative models.
    """

    __tablename__ = "reading_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    micro_session_id: Mapped[int | None] = mapped_column(ForeignKey("micro_sessions.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    event_metadata: Mapped[dict | None] = mapped_column("event_metadata", JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


class Highlight(Base):
    """A reader's private highlight of a passage. start/end are Unicode code
    point offsets into MicroSession.text; the quote and its context are cut
    from that text by the server, never taken from the client. Rows go away
    with their book or micro-session (database-level cascade)."""

    __tablename__ = "highlights"
    __table_args__ = (Index("ix_highlights_user_book", "user_id", "book_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    micro_session_id: Mapped[int] = mapped_column(
        ForeignKey("micro_sessions.id", ondelete="CASCADE"), nullable=False
    )
    start: Mapped[int] = mapped_column(Integer, nullable=False)
    end: Mapped[int] = mapped_column(Integer, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    context_before: Mapped[str] = mapped_column(Text, default="")
    context_after: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )


class MicroSessionTheme(Base):
    """One theme tag on one reading chunk. Scores below 3 are kept for analysis
    but never shown to readers or exported."""

    __tablename__ = "micro_session_themes"

    id: Mapped[int] = mapped_column(primary_key=True)
    micro_session_id: Mapped[int] = mapped_column(
        ForeignKey("micro_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    theme: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(8), default="llm", server_default="llm")
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt_version: Mapped[int] = mapped_column(Integer, default=1)
    theme_list_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    __table_args__ = (UniqueConstraint("micro_session_id", "theme", "source", name="uq_msthemes_chunk_theme_source"),)


class Shelf(Base):
    """A reader's own grouping of books - "Crime", "To read".

    Purely organisational: a shelf holds references, so putting a book on one
    changes nothing about the book, and taking it off a shelf (or deleting the
    shelf) leaves it in the library.
    """

    __tablename__ = "shelves"
    __table_args__ = (
        UniqueConstraint("user_id", "name_key", name="uq_shelf_user_name"),
        Index("ix_shelves_user_position", "user_id", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    # The name folded for comparison, so "Crime" and "crime" cannot both
    # exist. Stored rather than indexed as an expression, so the constraint
    # does not depend on the database collation.
    name_key: Mapped[str] = mapped_column(String(40), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    books: Mapped[list["ShelfBook"]] = relationship(
        back_populates="shelf",
        cascade="all, delete-orphan",
        order_by="ShelfBook.position",
    )


class ShelfBook(Base):
    """One book on one shelf. A book may be on several shelves at once."""

    __tablename__ = "shelf_books"

    shelf_id: Mapped[int] = mapped_column(
        ForeignKey("shelves.id", ondelete="CASCADE"), primary_key=True
    )
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    shelf: Mapped["Shelf"] = relationship(back_populates="books")


class ResearchTag(Base):
    """One rhetorical tag on one chunk of a research document.

    Kept in its own table rather than alongside the literary themes: the two
    lists mean different things (a novel passage is *about* grief; a paper
    paragraph *is* a claim), they version independently, and a research
    document must never appear in the pilot theme export. Same rules
    otherwise - scores below 3 are stored for analysis but never shown, and a
    stored tag is never overwritten.
    """

    __tablename__ = "research_tags"
    __table_args__ = (
        UniqueConstraint("micro_session_id", "tag", "source", name="uq_research_tags_chunk_tag_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    micro_session_id: Mapped[int] = mapped_column(
        ForeignKey("micro_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tag: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(8), default="llm", server_default="llm")
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt_version: Mapped[int] = mapped_column(Integer, default=1)
    tag_list_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class ResearchTagging(Base):
    """Queue state for one chunk of a research document: queued, running, done
    or failed. The status the reader sees comes from counting these."""

    __tablename__ = "research_tagging"

    micro_session_id: Mapped[int] = mapped_column(
        ForeignKey("micro_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt_version: Mapped[int] = mapped_column(Integer, default=1)
    tag_list_version: Mapped[int] = mapped_column(Integer, default=1)
    claimed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)


class SectionKeyPoints(Base):
    """Machine-generated key points for one section of a research document.

    Always labelled as generated in the UI. ``text`` is empty until the model
    has answered, and stays empty when it fails - a failed call shows nothing
    rather than a guess.
    """

    __tablename__ = "section_key_points"

    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt_version: Mapped[int] = mapped_column(Integer, default=1)
    claimed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)


class MicroSessionTagging(Base):
    """Tagging status of a chunk: pending (claimed), done, or failed. A chunk
    with status done and no theme rows simply has no clear theme."""

    __tablename__ = "micro_session_tagging"

    micro_session_id: Mapped[int] = mapped_column(
        ForeignKey("micro_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt_version: Mapped[int] = mapped_column(Integer, default=1)
    theme_list_version: Mapped[int] = mapped_column(Integer, default=1)
    claimed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
