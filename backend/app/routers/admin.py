"""Admin endpoints: user management and per-user analytics.

All routes require an administrator (``is_admin``). Exposes the registered users
with aggregated performance: predictions, hits, best combination, etc.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Prediction, PredictionResult, Draw
from ..auth import get_current_admin, hash_password
from ..schemas import AdminSetPassword, AdminCreateUser
from ..engine.data_engine import str_to_numbers

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _user_stats(db: Session, user: User) -> dict:
    total_predictions = db.query(Prediction).filter(Prediction.user_id == user.id).count()
    total_draws = db.query(Draw).filter(Draw.created_by == user.id).count()

    # hits aggregation across this user's prediction results
    agg = (
        db.query(func.max(PredictionResult.hits), func.avg(PredictionResult.hits), func.count(PredictionResult.id))
        .join(Prediction, Prediction.id == PredictionResult.prediction_id)
        .filter(Prediction.user_id == user.id)
        .first()
    )
    best_hits = int(agg[0]) if agg and agg[0] is not None else 0
    avg_hits = round(float(agg[1]), 3) if agg and agg[1] is not None else 0.0
    evaluated = int(agg[2]) if agg and agg[2] is not None else 0

    # best combination
    best = (
        db.query(PredictionResult, Prediction)
        .join(Prediction, Prediction.id == PredictionResult.prediction_id)
        .filter(Prediction.user_id == user.id)
        .order_by(PredictionResult.hits.desc())
        .first()
    )
    best_combo = None
    if best:
        res, pred = best
        best_combo = {
            "numbers": str_to_numbers(pred.numbers),
            "game_type": pred.game_type,
            "strategy": pred.strategy,
            "hits": res.hits,
            "matched": str_to_numbers(res.matched_numbers) if res.matched_numbers else [],
        }

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_admin": user.is_admin,
        "created_at": user.created_at,
        "total_predictions": total_predictions,
        "total_draws_added": total_draws,
        "evaluated_predictions": evaluated,
        "best_hits": best_hits,
        "average_hits": avg_hits,
        "best_combination": best_combo,
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return {
        "total_users": db.query(User).count(),
        "total_admins": db.query(User).filter(User.is_admin.is_(True)).count(),
        "total_predictions": db.query(Prediction).count(),
        "total_draws": db.query(Draw).count(),
        "total_evaluations": db.query(PredictionResult).count(),
        "best_hits_global": db.query(func.max(PredictionResult.hits)).scalar() or 0,
    }


@router.get("/users")
def list_users(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    users = db.query(User).order_by(User.created_at.asc()).all()
    return {"users": [_user_stats(db, u) for u in users]}


@router.post("/users")
def create_user(payload: AdminCreateUser, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    user = User(
        name=payload.name.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_stats(db, user)


@router.get("/users/{user_id}")
def user_detail(user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    stats = _user_stats(db, user)
    preds = (
        db.query(Prediction)
        .filter(Prediction.user_id == user_id)
        .order_by(Prediction.created_at.desc())
        .limit(100)
        .all()
    )
    predictions = []
    for p in preds:
        best = max([r.hits for r in p.results], default=0)
        predictions.append({
            "id": p.id,
            "game_type": p.game_type,
            "strategy": p.strategy,
            "numbers": str_to_numbers(p.numbers),
            "score": p.score,
            "status": p.status,
            "used": p.used,
            "best_hits": best,
            "created_at": p.created_at,
        })
    stats["predictions"] = predictions
    return stats


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="No se puede eliminar a un administrador")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta")
    # Keep the historical draws this user added; just detach authorship to avoid
    # a foreign-key violation (draws.created_by has no ON DELETE rule).
    db.query(Draw).filter(Draw.created_by == user.id).update({Draw.created_by: None})
    db.delete(user)  # cascades the user's predictions + their results
    db.commit()
    return {"deleted": user_id}


@router.post("/email-test")
def email_test(email: str, admin: User = Depends(get_current_admin)):
    """Temporary: diagnose the Resend email integration."""
    import json as _json, urllib.request, urllib.error
    from ..config import settings
    from ..email_util import email_configured
    info = {
        "configured": email_configured(),
        "from": settings.email_from,
        "has_key": bool(settings.resend_api_key),
        "key_prefix": settings.resend_api_key[:6] if settings.resend_api_key else None,
        "app_url": settings.app_url,
    }
    if not settings.resend_api_key:
        return info
    try:
        payload = _json.dumps({
            "from": settings.email_from, "to": [email],
            "subject": "Test MelateAI Pro", "html": "<p>Prueba de integración.</p>",
        }).encode()
        req = urllib.request.Request(
            "https://api.resend.com/emails", data=payload,
            headers={"Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            info["status"] = r.status
            info["body"] = r.read().decode()[:300]
    except urllib.error.HTTPError as e:
        info["error"] = f"HTTP {e.code}"
        try:
            info["http_body"] = e.read().decode()[:300]
        except Exception:
            pass
    except Exception as e:
        info["error"] = repr(e)
    return info


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, payload: AdminSetPassword, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": f"Contraseña de {user.email} actualizada"}
