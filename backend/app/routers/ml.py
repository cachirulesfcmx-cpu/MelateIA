"""ML training / performance endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ModelPerformance, User
from ..auth import get_current_user
from ..engine.game_config import GAME_KEYS, get_game
from ..engine.models_ml import get_model
from ..engine import bandit
from ..services import load_draw_rows

router = APIRouter(prefix="/api/ml", tags=["ml"])


def _train(db: Session, game_type: str, force: bool):
    cfg = get_game(game_type)
    history = [r["numbers"] for r in load_draw_rows(db, game_type)]
    if len(history) < 60:
        return {"game_type": game_type, "trained": False, "reason": "Historial insuficiente (mínimo 60 sorteos)"}
    model = get_model(game_type, cfg.max_number, history, force=force)
    return {
        "game_type": game_type,
        "trained": model.trained,
        "backend": model.backend,
        "metrics": model.metrics,
    }


@router.post("/train")
def train(game_type: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    return _train(db, game_type, force=False)


@router.post("/retrain")
def retrain(game_type: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    return _train(db, game_type, force=True)


@router.get("/performance")
def performance(game_type: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(ModelPerformance)
    if game_type:
        q = q.filter(ModelPerformance.game_type == game_type)
    rows = q.order_by(ModelPerformance.average_hits.desc()).all()
    weights = {}
    if game_type:
        weights = bandit.normalized_weights(db, game_type)
    return {
        "performance": [
            {
                "strategy": r.strategy,
                "game_type": r.game_type,
                "total_predictions": r.total_predictions,
                "average_hits": r.average_hits,
                "best_hits": r.best_hits,
                "weight": r.weight,
                "normalized_weight": weights.get(r.strategy),
                "updated_at": r.updated_at,
            }
            for r in rows
        ]
    }
