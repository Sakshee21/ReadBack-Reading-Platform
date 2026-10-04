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
