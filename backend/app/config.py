from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://readback:readback@localhost:5433/readback"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    recap_gap_hours: int = 24
    checkpoint_interval: int = 10
    micro_session_min_words: int = 400
    micro_session_max_words: int = 600
    cors_origins: list[str] = ["http://localhost:5173"]

    class Config:
        env_file = ".env"


settings = Settings()
