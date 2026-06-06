"""Application configuration loaded from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite for local/dev, override with DATABASE_URL for PostgreSQL in prod
    database_url: str = "sqlite:///./melateai.db"

    # Optional Postgres schema to isolate tables (set DB_SCHEMA=melateai in prod)
    db_schema: str = ""

    secret_key: str = "change-me-in-production-melateai-pro-secret"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    algorithm: str = "HS256"

    cors_origins: str = "*"


settings = Settings()
