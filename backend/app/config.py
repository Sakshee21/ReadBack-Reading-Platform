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
    # Unused since the recap script moved to OpenRouter (OP_API_KEY / OP_MODEL).
    # Kept so an old .env that still has GROQ_* lines keeps loading.
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    # OpenRouter, used offline by the theme-tagging script only (never at
    # request time). Set OP_API_KEY and OP_MODEL in backend/.env.
    op_api_key: str = ""
    op_model: str = ""
    # Which provider the offline scripts and the on-demand worker use:
    # "openrouter" (OP_*) or "ollama" (OLLAMA_*, e.g. gemma4:31b on Ollama cloud).
    llm_provider: str = "openrouter"
    ollama_api_key: str = ""
    ollama_model: str = ""
    ollama_url: str = "https://ollama.com/api/chat"
    # On-demand theme tagging for consented uploads (off unless switched on).
    theme_tagging_on_demand: bool = False
    # Pause between model calls, to respect free-tier rate limits.
    theme_call_gap_seconds: float = 4.0
    micro_session_min_words: int = 400
    micro_session_max_words: int = 600
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def llm_api_key(self) -> str:
        return self.ollama_api_key if self.llm_provider == "ollama" else self.op_api_key

    @property
    def llm_model(self) -> str:
        return self.ollama_model if self.llm_provider == "ollama" else self.op_model

    class Config:
        env_file = ".env"


settings = Settings()
