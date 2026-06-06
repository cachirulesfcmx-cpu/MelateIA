"""MelateAI Pro — FastAPI application entrypoint."""
import os
import shutil

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db, SessionLocal, is_sqlite
from .routers import auth, draws, predictions, evaluation, earnings, ml, dashboard
from .schemas import BacktestRequest
from .auth import get_current_user
from .models import User


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

origins = ["*"] if settings.cors_origins == "*" else [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "MelateAI Pro"}


@app.get("/api/_diag")
def diag(db: Session = Depends(get_db)):
    """Temporary diagnostics for the live deployment."""
    import os as _os
    from .models import User as _User, Draw as _Draw
    template = _os.path.join(_os.path.dirname(__file__), "..", "data", "seed.db")
    target = settings.database_url.split("sqlite:///")[-1] if settings.database_url.startswith("sqlite") else None
    info = {
        "db_dialect": settings.database_url.split(":", 1)[0],
        "db_schema": settings.db_schema,
        "bootstrap_error": BOOTSTRAP_ERROR,
        "secret_is_default": settings.secret_key == "change-me-in-production-melateai-pro-secret",
        "template_path": _os.path.abspath(template),
        "template_exists": _os.path.exists(template),
        "target_db": target,
        "target_exists": _os.path.exists(target) if target else None,
        "cwd": _os.getcwd(),
    }
    try:
        info["data_dir_listing"] = sorted(_os.listdir(_os.path.dirname(template)))
    except Exception as e:
        info["data_dir_listing"] = f"err: {e}"
    try:
        info["user_count"] = db.query(_User).count()
        info["draw_count"] = db.query(_Draw).count()
        demo = db.query(_User).filter(_User.email == "demo@melateai.pro").first()
        info["demo_user_id"] = demo.id if demo else None
    except Exception as e:
        info["db_error"] = str(e)
    return info


# Spec alias: GET /api/backtesting
@app.post("/api/backtesting")
def backtesting_alias(payload: BacktestRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return evaluation.backtesting(payload, db, user)
