"""Lightweight DB-backed rate limiting (sliding window).

Works across serverless instances because the counter lives in the shared
database. Call ``enforce_rate_limit`` at the start of sensitive endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .models import RateLimit


def client_ip(request: Request | None) -> str:
    if request is None:
        return "unknown"
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(db: Session, bucket: str, limit: int, window_seconds: int):
    """Raise HTTP 429 if ``bucket`` exceeded ``limit`` hits within the window."""
    if not settings.rate_limit_enabled:
        return
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    try:
        # opportunistic cleanup of this bucket's stale rows
        db.query(RateLimit).filter(RateLimit.bucket == bucket, RateLimit.created_at < cutoff).delete()
        count = db.query(RateLimit).filter(RateLimit.bucket == bucket, RateLimit.created_at >= cutoff).count()
        if count >= limit:
            raise HTTPException(status_code=429, detail="Demasiados intentos. Espera unos minutos e inténtalo de nuevo.")
        db.add(RateLimit(bucket=bucket, created_at=now))
        db.commit()
    except HTTPException:
        raise
    except Exception:
        # never block a request because the limiter itself failed
        db.rollback()
