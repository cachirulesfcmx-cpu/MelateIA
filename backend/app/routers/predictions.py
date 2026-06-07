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
from ..engine.strategies import STRATEGIES, STRATEGY_KEYS, build_profile
from ..engine.generator import generate
from ..engine.models_ml import get_model
from ..engine.symbolic import score_combination
from ..engine.features import combination_features, is_prime
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

    # "Adaptativa" = contextual bandit: route to the best strategy learned for
    # the CURRENT regime, falling back to the global best, then the hybrid engine.
    effective = payload.strategy
    routed = None
    ctx = None
    if payload.strategy == "adaptativa":
        from ..engine import bandit
        from ..engine.context import regime
        ctx = regime(stats)
        effective = bandit.best_strategy_for_context(db, payload.game_type, ctx)
        if not effective:
            weights = bandit.normalized_weights(db, payload.game_type)
            concrete = {s: w for s, w in weights.items() if s in STRATEGIES and s != "adaptativa"}
            effective = max(concrete, key=concrete.get) if concrete else "hibrida"
        routed = effective

    combos = generate(stats, effective, payload.count, ml_scorer=scorer)
    if payload.strategy == "adaptativa":
        for c in combos:
            c["strategy"] = "adaptativa"
            c["explanation"] = f"Adaptativa (IA · régimen {ctx}) → estrategia mejor evaluada: {STRATEGIES[effective]['label']}. " + c["explanation"]
    return {"game_type": payload.game_type, "strategy": payload.strategy, "combos": combos, "routed_to": routed, "context": ctx}


from pydantic import BaseModel  # noqa: E402


class ScoreRequest(BaseModel):
    game_type: str
    numbers: list[int]
    strategy: str = "balanceada"


def _tips(f: dict, cfg) -> list[str]:
    tips = []
    ideal_sum = cfg.pick * (cfg.max_number + 1) / 2
    if f["odd"] <= 1 or f["odd"] >= cfg.pick - 1:
        tips.append(f"Equilibra pares e impares (ideal ~{cfg.pick // 2}/{cfg.pick - cfg.pick // 2}).")
    if f["sum"] < ideal_sum * 0.62:
        tips.append("La suma es baja: considera algunos números más altos.")
    elif f["sum"] > ideal_sum * 1.38:
        tips.append("La suma es alta: considera algunos números más bajos.")
    if f["consecutive"] >= 3:
        tips.append("Demasiados consecutivos; rómpelos para un patrón menos obvio.")
    if 0 in (f["low"], f["mid"], f["high"]):
        tips.append("Distribuye en los tres tercios (bajos/medios/altos).")
    if f["low"] == cfg.pick:
        tips.append("Solo números ≤ tercio bajo; evita el sesgo de calendario.")
    if f["primes"] == 0:
        tips.append("Sin primos; agrega 1-2 para diversificar.")
    if f["popularity"] >= 0.6:
        tips.append("Patrón muy 'humano/popular'; algo más contrario reduce compartir premio.")
    if not tips:
        tips.append("Combinación bien equilibrada ✦")
    return tips


@router.post("/score")
def score_combo(payload: ScoreRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    try:
        numbers = validate_combination(payload.game_type, payload.numbers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    stats, cfg = build_stats(db, payload.game_type)
    if not stats.draws:
        raise HTTPException(status_code=400, detail="Sin datos para este juego")
    strategy = payload.strategy if payload.strategy in STRATEGY_KEYS else "balanceada"
    profile = build_profile(strategy, stats)
    s, comps = score_combination(numbers, stats, profile)
    feats = combination_features(numbers, stats)
    history = [r["numbers"] for r in load_draw_rows(db, payload.game_type)]
    model = get_model(payload.game_type, cfg.max_number, history)
    probs = model.probabilities(history)
    mx = max(probs.values()) or 1.0
    return {
        "game_type": payload.game_type,
        "numbers": numbers,
        "score": s,
        "components": {k: round(v, 3) for k, v in comps.items()},
        "features": feats,
        "number_probs": [{"number": n, "prob": round(probs[n], 4), "rel": round(probs[n] / mx, 3)} for n in numbers],
        "tips": _tips(feats, cfg),
    }


@router.post("/save", response_model=PredictionOut)
def save_prediction(payload: PredictionSave, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    if payload.strategy not in STRATEGY_KEYS:
        raise HTTPException(status_code=400, detail="Estrategia inválida")
    try:
        numbers = validate_combination(payload.game_type, payload.numbers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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

    # Latest official draw number per game, so the UI can offer
    # "Evaluar con sorteo #xxxx" for still-pending predictions.
    from sqlalchemy import func as _func
    latest_rows = (
        db.query(Draw.game_type, _func.max(Draw.draw_number))
        .group_by(Draw.game_type)
        .all()
    )
    latest_by_game = {gt: n for gt, n in latest_rows}

    out = []
    for p in preds:
        d = _pred_out_full(p, db)
        latest = latest_by_game.get(p.game_type)
        d["latest_draw_number"] = latest
        evaluated_draws = {r["draw_number"] for r in d["results"]}
        # can still be evaluated against a newer official draw it hasn't seen
        d["can_evaluate"] = latest is not None and latest not in evaluated_draws
        out.append(d)
    return out


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
