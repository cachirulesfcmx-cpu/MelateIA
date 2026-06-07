"""Web Push (VAPID) sending. Optional: disabled gracefully if not configured."""
import json

from sqlalchemy.orm import Session

from .config import settings
from .models import PushSubscription


def push_enabled() -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def _send_one(sub: PushSubscription, payload: dict) -> str:
    try:
        from pywebpush import webpush, WebPushException
    except Exception:
        return "no_lib"
    info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
    try:
        webpush(
            subscription_info=info,
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            timeout=10,
        )
        return "ok"
    except WebPushException as e:  # type: ignore
        status = getattr(getattr(e, "response", None), "status_code", None)
        return "gone" if status in (404, 410) else "error"
    except Exception:
        return "error"


def notify_user(db: Session, user_id: int, payload: dict) -> int:
    """Send a push to all of a user's subscriptions. Prunes expired ones."""
    if not push_enabled():
        return 0
    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    sent = 0
    for s in subs:
        r = _send_one(s, payload)
        if r == "ok":
            sent += 1
        elif r == "gone":
            db.delete(s)
    if sent or any(True for _ in subs):
        try:
            db.commit()
        except Exception:
            db.rollback()
    return sent
