"""Dashboard summary endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import Draw, Prediction, PredictionResult, ModelPerformance, User
from ..auth import get_current_user
from ..engine.game_config import GAMES
from ..engine.data_engine import str_to_numbers

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # latest draw per game
    latest = {}
    next_draws = {}
    for key, cfg in GAMES.items():
        d = db.query(Draw).filter(Draw.game_type == key).order_by(Draw.draw_number.desc()).first()
        if d:
            latest[key] = {
                "label": cfg.label,
                "draw_number": d.draw_number,
                "draw_date": d.draw_date,
                "numbers": str_to_numbers(d.numbers),
                "additional": d.additional,
            }
            next_draws[key] = {"label": cfg.label, "draw_number": d.draw_number + 1}

    total_draws = db.query(Draw).count()
    active = (
        db.query(Prediction)
        .filter(Prediction.user_id == user.id, Prediction.status.in_(["pendiente", "usada"]))
        .count()
    )
    total_predictions = db.query(Prediction).filter(Prediction.user_id == user.id).count()

    # best combination by hits
    best_result = (
        db.query(PredictionResult, Prediction)
        .join(Prediction, Prediction.id == PredictionResult.prediction_id)
        .filter(Prediction.user_id == user.id)
        .order_by(PredictionResult.hits.desc())
        .first()
    )
    best_combo = None
    if best_result:
        res, pred = best_result
        best_combo = {
            "numbers": str_to_numbers(pred.numbers),
            "strategy": pred.strategy,
            "game_type": pred.game_type,
            "hits": res.hits,
            "matched": str_to_numbers(res.matched_numbers) if res.matched_numbers else [],
        }

    # recent hits
    recent_hits = (
        db.query(PredictionResult, Prediction)
        .join(Prediction, Prediction.id == PredictionResult.prediction_id)
        .filter(Prediction.user_id == user.id, PredictionResult.hits >= 2)
        .order_by(PredictionResult.evaluated_at.desc())
        .limit(5)
        .all()
    )
    recent = [
        {
            "game_type": p.game_type,
            "strategy": p.strategy,
            "hits": r.hits,
            "numbers": str_to_numbers(p.numbers),
            "matched": str_to_numbers(r.matched_numbers) if r.matched_numbers else [],
            "evaluated_at": r.evaluated_at,
        }
        for r, p in recent_hits
    ]

    # system performance avg
    perf = db.query(func.avg(PredictionResult.hits)).join(
        Prediction, Prediction.id == PredictionResult.prediction_id
    ).filter(Prediction.user_id == user.id).scalar()

    best_strategy = (
        db.query(ModelPerformance)
        .order_by(ModelPerformance.weight.desc())
        .first()
    )

    return {
        "latest_draws": latest,
        "next_draws": next_draws,
        "total_draws": total_draws,
        "total_predictions": total_predictions,
        "active_predictions": active,
        "best_combination": best_combo,
        "recent_hits": recent,
        "system_average_hits": round(perf, 3) if perf else 0,
        "top_strategy": best_strategy.strategy if best_strategy else None,
    }
