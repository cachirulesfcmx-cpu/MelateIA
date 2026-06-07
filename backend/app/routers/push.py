"""Web Push subscription endpoints."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User, PushSubscription
from ..auth import get_current_user
from ..push_util import push_enabled, notify_user

router = APIRouter(prefix="/api/push", tags=["push"])


class Keys(BaseModel):
    p256dh: str
    auth: str


class Sub(BaseModel):
    endpoint: str
    keys: Keys


class Unsub(BaseModel):
    endpoint: str


@router.get("/vapid")
def vapid(user: User = Depends(get_current_user)):
    return {"enabled": push_enabled(), "public_key": settings.vapid_public_key}


@router.post("/subscribe")
def subscribe(payload: Sub, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == payload.endpoint).first()
    if existing:
        existing.user_id = user.id
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
    else:
        db.add(PushSubscription(
            user_id=user.id, endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh, auth=payload.keys.auth,
        ))
    db.commit()
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(payload: Unsub, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint, PushSubscription.user_id == user.id
    ).delete()
    db.commit()
    return {"ok": True}


@router.post("/test")
def test(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = notify_user(db, user.id, {
        "title": "MelateAI Pro",
        "body": "🔔 Notificaciones activadas correctamente.",
        "url": "/",
    })
    return {"sent": n, "enabled": push_enabled()}
