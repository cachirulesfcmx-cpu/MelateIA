"""Evaluation & backtesting endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Prediction, PredictionResult, Draw, User
from ..schemas import BacktestRequest
from ..auth import get_current_user
from ..engine.game_config import get_game, GAME_KEYS
from ..engine.data_engine import str_to_numbers
from ..engine.backtesting import run_backtest
from ..services import load_draw_rows, evaluate_prediction_against_draw

router = APIRouter(prefix="/api/evaluate", tags=["evaluation"])


@router.post("/new-draw")
def reevaluate_against_latest(game_type: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Manually trigger evaluation of pending predictions vs the latest draw."""
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    draw = (
        db.query(Draw)
        .filter(Draw.game_type == game_type)
        .order_by(Draw.draw_number.desc())
        .first()
    )
    if not draw:
        raise HTTPException(status_code=404, detail="No hay sorteos para este juego")
    from ..services import evaluate_new_draw
    new_hits = evaluate_new_draw(db, draw)
    return {"draw_number": draw.draw_number, "evaluated": len(new_hits), "new_hits": new_hits}


@router.get("/prediction/{pred_id}")
def evaluate_single(pred_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Re-analyse a prediction against the most recent draw of its game type."""
    pred = db.query(Prediction).filter(Prediction.id == pred_id, Prediction.user_id == user.id).first()
    if not pred:
        raise HTTPException(status_code=404, detail="Predicción no encontrada")
    draw = (
        db.query(Draw)
        .filter(Draw.game_type == pred.game_type)
        .order_by(Draw.draw_number.desc())
        .first()
    )
    if not draw:
        raise HTTPException(status_code=404, detail="No hay sorteos para comparar")
    result = evaluate_prediction_against_draw(db, pred, draw)
    db.commit()
    return {
        "prediction_id": pred.id,
        "draw_number": draw.draw_number,
        "actual": str_to_numbers(draw.numbers),
        "prediction": str_to_numbers(pred.numbers),
        "hits": result.hits,
        "matched": str_to_numbers(result.matched_numbers) if result.matched_numbers else [],
        "missed": str_to_numbers(result.missed_numbers) if result.missed_numbers else [],
    }


@router.post("/backtesting")
def backtesting(payload: BacktestRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    cfg = get_game(payload.game_type)
    rows = load_draw_rows(db, payload.game_type)
    if len(rows) < 40:
        raise HTTPException(status_code=400, detail="Historial insuficiente para backtesting (mínimo 40 sorteos)")
    result = run_backtest(
        cfg, rows, payload.strategy, payload.last_n, payload.combos_per_draw, payload.cost_per_combination
    )
    return result
