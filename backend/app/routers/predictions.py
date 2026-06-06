"""Prediction endpoints: generate, save, history, mark-used, delete, export."""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Prediction, PredictionResult, Draw, User
from ..schemas import (
    PredictionGenerate, PredictionGenerateOut, PredictionSave, PredictionOut,
)
from ..auth import get_current_user
from ..engine.game_config import get_game, validate_combination, GAME_KEYS
from ..engine.strategies import STRATEGIES, STRATEGY_KEYS
from ..engine.generator import generate
from ..engine.models_ml import get_model
from ..engine.data_engine import numbers_to_str, str_to_numbers
from ..services import build_stats, load_draw_rows

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("/strategies")
def list_strategies():
    return [
        {"key": k, "label": v["label"], "desc": v["desc"]}
        for k, v in STRATEGIES.items()
    ]


@router.post("/generate", response_model=PredictionGenerateOut)
def generate_predictions(payload: PredictionGenerate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    if payload.strategy not in STRATEGY_KEYS:
        raise HTTPException(status_code=400, detail="Estrategia inválida")

    stats, cfg = build_stats(db, payload.game_type)
    if not stats.draws:
        raise HTTPException(status_code=400, detail="No hay sorteos cargados para este juego. Carga el CSV primero.")

    history = [r["numbers"] for r in load_draw_rows(db, payload.game_type)]
    model = get_model(payload.game_type, cfg.max_number, history)
    scorer = model.make_scorer(history)

    combos = generate(stats, payload.strategy, payload.count, ml_scorer=scorer)
    return {"game_type": payload.game_type, "strategy": payload.strategy, "combos": combos}


@router.post("/save", response_model=PredictionOut)
def save_prediction(payload: PredictionSave, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    if payload.strategy not in STRATEGY_KEYS:
        raise HTTPException(status_code=400, detail="Estrategia inválida")
    numbers = validate_combination(payload.game_type, payload.numbers)
    pred = Prediction(
        user_id=user.id,
        game_type=payload.game_type,
        strategy=payload.strategy,
        numbers=numbers_to_str(numbers),
        score=payload.score,
        explanation=payload.explanation,
        status="pendiente",
    )
    db.add(pred)
    db.commit()
    db.refresh(pred)
    return _pred_out(pred)


def _pred_out(p: Prediction) -> dict:
    results = []
    best = 0
    for r in p.results:
        results.append({
            "hits": r.hits,
            "matched_numbers": str_to_numbers(r.matched_numbers) if r.matched_numbers else [],
            "missed_numbers": str_to_numbers(r.missed_numbers) if r.missed_numbers else [],
            "draw_id": r.draw_id,
            "draw_number": 0,  # filled below by router that has db
            "evaluated_at": r.evaluated_at,
        })
        best = max(best, r.hits)
    return {
        "id": p.id,
        "game_type": p.game_type,
        "strategy": p.strategy,
        "numbers": str_to_numbers(p.numbers),
        "score": p.score,
        "explanation": p.explanation,
        "status": p.status,
        "used": p.used,
        "created_at": p.created_at,
        "results": results,
        "best_hits": best,
    }


def _pred_out_full(p: Prediction, db: Session) -> dict:
    out = _pred_out(p)
    # enrich result draw numbers
    for r in out["results"]:
        draw = db.query(Draw).filter(Draw.id == r["draw_id"]).first()
        if draw:
            r["draw_number"] = draw.draw_number
    return out


@router.get("/history")
def history(game_type: str | None = None, status: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Prediction).filter(Prediction.user_id == user.id)
    if game_type:
        q = q.filter(Prediction.game_type == game_type)
    if status:
        q = q.filter(Prediction.status == status)
    preds = q.order_by(Prediction.created_at.desc()).all()
    return [_pred_out_full(p, db) for p in preds]


@router.post("/{pred_id}/mark-used", response_model=PredictionOut)
def mark_used(pred_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pred = db.query(Prediction).filter(Prediction.id == pred_id, Prediction.user_id == user.id).first()
    if not pred:
        raise HTTPException(status_code=404, detail="Predicción no encontrada")
    pred.used = True
    if pred.status == "pendiente":
        pred.status = "usada"
    db.commit()
    db.refresh(pred)
    return _pred_out_full(pred, db)


@router.delete("/{pred_id}")
def delete_prediction(pred_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pred = db.query(Prediction).filter(Prediction.id == pred_id, Prediction.user_id == user.id).first()
    if not pred:
        raise HTTPException(status_code=404, detail="Predicción no encontrada")
    db.delete(pred)
    db.commit()
    return {"deleted": pred_id}


@router.get("/export")
def export_csv(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    preds = db.query(Prediction).filter(Prediction.user_id == user.id).order_by(Prediction.created_at.desc()).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "game_type", "strategy", "numbers", "score", "status", "used", "best_hits", "created_at"])
    for p in preds:
        best = max([r.hits for r in p.results], default=0)
        w.writerow([
            p.id, p.game_type, p.strategy, p.numbers, p.score, p.status, p.used, best,
            p.created_at.isoformat() if p.created_at else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=predicciones_melateai.csv"},
    )
