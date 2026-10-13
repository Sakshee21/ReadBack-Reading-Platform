from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://readback:readback@localhost:5433/readback"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    admin_token: str = "readback-admin-dev"
    recap_gap_hours: int = 24
    # Gap after which the stitched "story so far" replaces the last-few-chapters
    # recap (default 7 days).
    recap_long_gap_hours: int = 24 * 7
    checkpoint_interval: int = 10
    # Serve an authored checkpoint only at chapters where index % N == 0.
    # 1 = every authored checkpoint fires.
    quiz_every_n_chapters: int = 1
    # Days away before the in-app "pick up where you left off" nudge appears.
    nudge_away_days: int = 3

    # User book uploads. Uploads are private to the uploader and excluded from
    # pilot analysis; these caps keep a single user from filling the database.
    upload_max_bytes: int = 10 * 1024 * 1024
    upload_max_words: int = 500_000
    upload_min_words: int = 200
    uploads_per_user: int = 5
    # Story-flag policy for uploaded books. The scene-shift and every-3rd
    # heuristics were tuned on five curated Gutenberg books and misfire on
    # arbitrary uploads, so uploads get conservative cliffhangers and no
    # visualization prompts. Flip either here to change it everywhere.
    upload_conservative_cliffhangers: bool = True
    # Visualization prompts are on for uploads but placed sparingly: only on
    # story sections, never on a chapter's first or last session, and only
    # every Nth session rather than at every cliffhanger.
    upload_visualization_prompts: bool = True
    upload_visualization_every: int = 5
    # Groq is used offline by scripts/generate_recaps.py only. The app never
    # calls an LLM at request time, so an empty key is fine at runtime.
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    micro_session_min_words: int = 400
    micro_session_max_words: int = 600
    cors_origins: list[str] = ["http://localhost:5173"]

    class Config:
        env_file = ".env"


settings = Settings()
