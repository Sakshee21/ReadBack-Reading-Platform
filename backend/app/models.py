import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
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
    gutenberg_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    total_word_count: Mapped[int] = mapped_column(Integer, default=0)

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
