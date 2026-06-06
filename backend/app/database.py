"""Database engine and session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from .config import settings

is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

# Serverless/Postgres: use NullPool so connections aren't reused across
# short-lived function invocations (works with Supabase/pgbouncer poolers).
engine_kwargs = {"connect_args": connect_args, "pool_pre_ping": True}
if not is_sqlite:
    engine_kwargs["poolclass"] = NullPool

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Isolate all tables in a dedicated Postgres schema (e.g. "melateai") so every
# statement is schema-qualified — no reliance on search_path through the pooler,
# and no collision with other apps' tables in `public`. SQLite ignores this.
if settings.db_schema and not is_sqlite:
    Base.metadata.schema = settings.db_schema


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
