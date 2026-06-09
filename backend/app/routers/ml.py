"""ML training / performance endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ModelPerformance, User, Prediction, PredictionResult, LearningLog, StrategyContextPerf
from ..engine.context import regime
from ..engine.features import GameStats
from ..auth import get_current_user
from ..engine.game_config import GAME_KEYS, get_game
from ..engine.strategies import STRATEGIES
from ..engine.models_ml import get_model
from ..engine import bandit
from ..services import load_draw_rows

router = APIRouter(prefix="/api/ml", tags=["ml"])


def _train(db: Session, game_type: str, force: bool):
    cfg = get_game(game_type)
    if cfg.kind == "positional":
        return {"game_type": game_type, "trained": False, "backend": "positional",
                "reason": "Tris usa un motor posicional estadístico (sin modelo de combinación)."}
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


@router.get("/probabilities")
def probabilities(game_type: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Per-number probability of appearing in the next draw, from the trained
    ML model (XGBoost/GradientBoosting where available, heuristic otherwise)."""
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    cfg = get_game(game_type)
    history = [r["numbers"] for r in load_draw_rows(db, game_type)]
    if len(history) < 30:
        raise HTTPException(status_code=400, detail="Historial insuficiente")
    if cfg.kind == "positional":
        from ..engine.positional import PositionalStats, pos_probabilities
        out = pos_probabilities(PositionalStats(cfg, history))
        out.update({"game_type": game_type, "kind": "positional", "backend": "positional", "trained": True})
        return out
    model = get_model(game_type, cfg.max_number, history)
    probs = model.probabilities(history)
    mx = max(probs.values()) or 1.0
    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "game_type": game_type,
        "max_number": cfg.max_number,
        "pick": cfg.pick,
        "backend": model.backend,
        "trained": model.trained,
        "numbers": [
            {"number": n, "prob": round(probs[n], 4), "rel": round(probs[n] / mx, 3)}
            for n in range(1, cfg.max_number + 1)
        ],
        "top": [{"number": n, "prob": round(p, 4), "rel": round(p / mx, 3)} for n, p in ranked[: cfg.pick * 2]],
    }


@router.get("/analytics")
def analytics(game_type: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Performance & AI-evolution analytics for charts.

    Returns: per-strategy learning (bandit weight + avg hits, aggregated across
    games or filtered), and the current user's accuracy distribution + timeline.
    """
    # ---- strategy learning (system-wide) ----
    pq = db.query(ModelPerformance)
    if game_type:
        pq = pq.filter(ModelPerformance.game_type == game_type)
    rows = pq.all()
    agg: dict[str, dict] = {}
    for r in rows:
        a = agg.setdefault(r.strategy, {"total": 0, "hits": 0.0, "best": 0, "weight": 0.0, "n": 0})
        a["total"] += r.total_predictions or 0
        a["hits"] += (r.average_hits or 0) * (r.total_predictions or 0)
        a["best"] = max(a["best"], r.best_hits or 0)
        a["weight"] += r.weight or 0
        a["n"] += 1
    strategies = []
    for key, cfg in STRATEGIES.items():
        a = agg.get(key)
        total = a["total"] if a else 0
        strategies.append({
            "strategy": key,
            "label": cfg["label"],
            "total_predictions": total,
            "average_hits": round(a["hits"] / total, 3) if a and total else 0.0,
            "best_hits": a["best"] if a else 0,
            "weight": round(a["weight"] / a["n"], 3) if a and a["n"] else 1.0,
        })
    wsum = sum(s["weight"] for s in strategies) or 1.0
    for s in strategies:
        s["normalized_weight"] = round(s["weight"] / wsum, 4)

    # ---- user accuracy ----
    base = (
        db.query(PredictionResult, Prediction)
        .join(Prediction, Prediction.id == PredictionResult.prediction_id)
        .filter(Prediction.user_id == user.id)
    )
    if game_type:
        base = base.filter(Prediction.game_type == game_type)
    results = base.all()
    dist = {str(k): 0 for k in range(7)}
    for r, _ in results:
        dist[str(min(6, r.hits))] += 1

    # timeline grouped by day
    tq = (
        db.query(
            func.date(PredictionResult.evaluated_at).label("d"),
            func.avg(PredictionResult.hits),
            func.count(PredictionResult.id),
        )
        .join(Prediction, Prediction.id == PredictionResult.prediction_id)
        .filter(Prediction.user_id == user.id)
    )
    if game_type:
        tq = tq.filter(Prediction.game_type == game_type)
    tq = tq.group_by("d").order_by("d")
    timeline = [
        {"date": str(d), "avg_hits": round(float(avg), 3), "count": int(cnt)}
        for d, avg, cnt in tq.all()
    ]

    # ---- learning evolution over time (reinforcement) ----
    lq = db.query(LearningLog)
    if game_type:
        lq = lq.filter(LearningLog.game_type == game_type)
    logs = lq.order_by(LearningLog.created_at.asc()).all()
    evolution = []
    run_sum = 0
    for i, lg in enumerate(logs[-120:], start=1):
        run_sum += lg.hits or 0
        evolution.append({
            "i": i,
            "cum_avg_hits": round(run_sum / i, 3),
            "weight": round(lg.weight or 0, 3),
            "strategy": lg.strategy,
            "hits": lg.hits or 0,
        })

    # ---- contextual bandit (regime) ----
    current_context = None
    contextual = []
    if game_type:
        cfg = get_game(game_type)
        seqs = [r["numbers"] for r in load_draw_rows(db, game_type)]
        if seqs:
            if cfg.kind == "positional":
                from ..engine.positional import PositionalStats, pos_regime
                current_context = pos_regime(PositionalStats(cfg, seqs))
            else:
                current_context = regime(GameStats(max_number=cfg.max_number, draws=seqs, pick=cfg.pick))
        crows = db.query(StrategyContextPerf).filter(StrategyContextPerf.game_type == game_type).all()
        by_ctx: dict[str, list] = {}
        for r in crows:
            by_ctx.setdefault(r.context, []).append(r)
        for ctx, rs in sorted(by_ctx.items()):
            tot = sum(x.weight for x in rs) or 1.0
            contextual.append({
                "context": ctx,
                "strategies": sorted(
                    [{"strategy": x.strategy, "weight": round(x.weight, 3),
                      "normalized": round(x.weight / tot, 4), "evaluations": x.total_predictions,
                      "average_hits": x.average_hits} for x in rs],
                    key=lambda s: -s["weight"],
                ),
            })

    total_eval = len(results)
    total_hits = sum(r.hits for r, _ in results)
    return {
        "game_type": game_type,
        "strategies": strategies,
        "evolution": evolution,
        "learning_events": len(logs),
        "current_context": current_context,
        "contextual": contextual,
        "user": {
            "hits_distribution": dist,
            "timeline": timeline,
            "total_predictions": db.query(Prediction).filter(Prediction.user_id == user.id).count(),
            "total_evaluations": total_eval,
            "average_hits": round(total_hits / total_eval, 3) if total_eval else 0.0,
            "best_hits": max([r.hits for r, _ in results], default=0),
        },
    }
