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

    # Public app URL (used to build password-reset links)
    app_url: str = "https://melate-ia.vercel.app"

    # Email delivery for password recovery (optional).
    # Preferred: Resend HTTP API. Fallback: SMTP. If neither is configured the
    # reset token is returned directly (demo mode).
    email_from: str = "MelateAI Pro <onboarding@resend.dev>"
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # AI assistant (Claude). Leave key empty to disable the assistant.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # Error monitoring (optional)
    sentry_dsn: str = ""

    # Rate limiting
    rate_limit_enabled: bool = True

    # Web Push (VAPID). Leave empty to disable push notifications.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:no-reply@melastia.com"


settings = Settings()
