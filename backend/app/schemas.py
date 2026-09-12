import datetime as dt

from pydantic import BaseModel, EmailStr


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
    gutenberg_id: int
    title: str
    author: str
    total_word_count: int
    chapter_count: int

    class Config:
        from_attributes = True


class MicroSessionOut(BaseModel):
    id: int
    index: int
    text: str
    word_count: int
    is_cliffhanger_break: bool
    has_visualization_prompt: bool

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


class CheckpointOut(BaseModel):
    id: int
    book_id: int
    chapter_index_trigger: int
    questions: list[dict]

    class Config:
        from_attributes = True


class CheckpointSubmit(BaseModel):
    checkpoint_id: int
    answers: dict[str, str]


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


ReaderPositionOut.model_rebuild()
NextSessionOut.model_rebuild()
