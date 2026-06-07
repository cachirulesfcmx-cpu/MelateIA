"""MelateAI Pro — FastAPI application entrypoint."""
import os
import shutil

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db, SessionLocal, is_sqlite
from .routers import auth, draws, predictions, evaluation, earnings, ml, dashboard, admin, assistant, push
from .schemas import BacktestRequest
from .auth import get_current_user
from .models import User

# Optional error monitoring
if settings.sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)
    except Exception:
        pass


def _bootstrap():
    """Prepare the database on startup.

    On ephemeral serverless (DB at /tmp), restore from the bundled read-only
    seed template if present for a fast cold start; otherwise seed from CSVs.
    """
    url = settings.database_url
    if url.startswith("sqlite") and "/tmp/" in url:
        target = url.split("sqlite:///")[-1]
        if not os.path.exists(target):
            template = os.path.join(os.path.dirname(__file__), "..", "data", "seed.db")
            if os.path.exists(template):
                os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
                try:
                    shutil.copy(template, target)
                except OSError:
                    pass

    # Ensure the dedicated schema exists (Postgres), then create tables + seed.
    try:
        if not is_sqlite and settings.db_schema:
            from sqlalchemy import text
            with engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"'))
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            from .seed_data import seed_if_empty
            seed_if_empty(db)
        finally:
            db.close()
    except Exception as e:
        # Never crash the whole function on DB/bootstrap issues; routes that
        # need the DB will surface errors, and /api/_diag reports the reason.
        global BOOTSTRAP_ERROR
        BOOTSTRAP_ERROR = repr(e)


BOOTSTRAP_ERROR = None
_bootstrap()

app = FastAPI(
    title="MelateAI Pro API",
    description="Motor híbrido matemático-predictivo para Melate, Revancha, Melate Retro y Revanchita. "
                "Melate es un juego de azar; ninguna IA puede garantizar premios.",
    version="1.0.0",
)

_KNOWN_ORIGINS = [
    "https://melastia.com",
    "https://www.melastia.com",
    "https://melate-ia.vercel.app",
]
if settings.cors_origins == "*":
    origins = ["*"]
else:
    origins = sorted({
        *(o.strip() for o in settings.cors_origins.split(",") if o.strip()),
        *_KNOWN_ORIGINS,
    })
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(draws.router)
app.include_router(predictions.router)
app.include_router(evaluation.router)
app.include_router(earnings.router)
app.include_router(ml.router)
app.include_router(admin.router)
app.include_router(assistant.router)
app.include_router(push.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "MelateAI Pro"}


# Spec alias: GET /api/backtesting
@app.post("/api/backtesting")
def backtesting_alias(payload: BacktestRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return evaluation.backtesting(payload, db, user)
