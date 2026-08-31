"""v8 — Live track record and prediction audit.

Rule 31: the live record stays SEPARATE from the backtest. A backtest is what a
model would have done on history it was tuned against; the live record is what
the app actually predicted before the draw happened. Mixing them is how a
system ends up believing its own rehearsal.

The reference package starts an empty in-memory counter. This app has been
saving real predictions and comparing them against real draws for its whole
life, so the live record is built from THAT — the honest number, computed from
what actually happened, against the exact random baseline.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .game_config import get_game
from .research_lab import empirical_random_baseline, theoretical_random_mean_hits


def live_track_record(db: Session, game_type: str | None = None,
                      by_strategy: bool = True) -> dict:
    """Real performance of the predictions this app made, before the draws."""
    from ..models import Prediction, PredictionResult

    q = (db.query(PredictionResult, Prediction)
         .join(Prediction, PredictionResult.prediction_id == Prediction.id))
    if game_type:
        q = q.filter(Prediction.game_type == game_type)
    rows = q.all()

    if not rows:
        return {"source": "live", "games": 0,
                "message": ("Todavía no hay predicciones evaluadas contra sorteos "
                            "reales para este juego."),
                "separate_from_backtest": True}

    overall: Counter = Counter()
    per_strategy: dict[str, Counter] = {}
    per_game: dict[str, Counter] = {}
    total_hits = 0
    for result, pred in rows:
        h = int(result.hits or 0)
        overall[h] += 1
        total_hits += h
        per_strategy.setdefault(pred.strategy or "?", Counter())[h] += 1
        per_game.setdefault(pred.game_type, Counter())[h] += 1

    n = sum(overall.values())
    mean_hits = total_hits / n

    def _block(counter: Counter, game_key: str | None) -> dict:
        cnt = sum(counter.values())
        hits = sum(k * v for k, v in counter.items())
        cfg = get_game(game_key) if game_key else None
        rand = (theoretical_random_mean_hits(cfg.max_number, cfg.pick)
                if cfg and cfg.kind == "combination" else None)
        return {
            "games": cnt,
            "mean_hits": round(hits / cnt, 4) if cnt else 0.0,
            "distribution": {str(k): counter.get(k, 0) for k in sorted(counter)},
            "random_mean_hits": round(rand, 4) if rand is not None else None,
            "edge_vs_random": (round(hits / cnt - rand, 4)
                               if cnt and rand is not None else None),
        }

    cfg = get_game(game_type) if game_type else None
    random_mean = (theoretical_random_mean_hits(cfg.max_number, cfg.pick)
                   if cfg and cfg.kind == "combination" else None)
    exact = (empirical_random_baseline(n, cfg.max_number, cfg.pick)
             if cfg and cfg.kind == "combination" else None)

    reading = None
    if random_mean is not None and exact:
        edge = mean_hits - random_mean
        inside = exact["ci95_low"] <= mean_hits <= exact["ci95_high"]
        reading = (
            f"{n} predicciones evaluadas: {mean_hits:.4f} aciertos de media frente a "
            f"{random_mean:.4f} del azar exacto ({edge:+.4f}). "
            + ("Está dentro del intervalo del 95% del azar, así que no se distingue "
               "de jugar al azar." if inside else
               "Queda fuera del intervalo del 95% del azar — merece una mirada, "
               "pero un tramo corto puede desviarse sin que haya ventaja."))

    return {
        "source": "live",
        "separate_from_backtest": True,
        "game_type": game_type,
        "games": n,
        "mean_hits": round(mean_hits, 4),
        "distribution": {str(k): overall.get(k, 0) for k in sorted(overall)},
        "random_mean_hits": round(random_mean, 4) if random_mean is not None else None,
        "edge_vs_random": (round(mean_hits - random_mean, 4)
                           if random_mean is not None else None),
        "random_ci95": ([exact["ci95_low"], exact["ci95_high"]] if exact else None),
        "by_strategy": ({k: _block(v, game_type) for k, v in
                         sorted(per_strategy.items(), key=lambda kv: -sum(kv[1].values()))}
                        if by_strategy else {}),
        "by_game": {k: _block(v, k) for k, v in per_game.items()} if not game_type else {},
        "reading": reading,
        "note": ("Este es el historial REAL de la app: predicciones hechas antes del "
                 "sorteo. No se mezcla con el backtest, que evalúa modelos sobre "
                 "datos que ya conocían."),
    }


def record_audit(db: Session, *, run_id: str, game_type: str, model: str,
                 model_version: str, seed: int | None, data_snapshot: str,
                 numbers: list[int], source: str = "portfolio") -> dict:
    """Persist an auditable record of a live prediction (rule 30)."""
    from ..models import LivePredictionAudit

    row = LivePredictionAudit(
        run_id=run_id, game_type=game_type, model=model,
        model_version=model_version, seed=seed, data_snapshot=data_snapshot,
        numbers=",".join(str(int(n)) for n in numbers), source=source,
        generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(row)
    db.commit()
    return {"audited": True, "run_id": run_id, "model_version": model_version,
            "numbers": list(numbers)}


def audit_listing(db: Session, game_type: str | None = None, limit: int = 50) -> list[dict]:
    from ..models import LivePredictionAudit

    q = db.query(LivePredictionAudit)
    if game_type:
        q = q.filter(LivePredictionAudit.game_type == game_type)
    rows = q.order_by(LivePredictionAudit.generated_at.desc(),
                      LivePredictionAudit.id.desc()).limit(limit).all()
    return [{
        "run_id": r.run_id, "game_type": r.game_type, "model": r.model,
        "model_version": r.model_version, "seed": r.seed,
        "data_snapshot": (r.data_snapshot or "")[:16],
        "numbers": [int(x) for x in (r.numbers or "").split(",") if x],
        "hits": r.hits, "source": r.source, "generated_at": r.generated_at,
    } for r in rows]


def settle_audits(db: Session, game_type: str, winning_numbers: list[int]) -> dict:
    """Score any pending audited predictions against a real draw."""
    from ..models import LivePredictionAudit

    winners = {int(n) for n in winning_numbers}
    rows = (db.query(LivePredictionAudit)
            .filter(LivePredictionAudit.game_type == game_type,
                    LivePredictionAudit.hits.is_(None))
            .all())
    settled = 0
    for r in rows:
        nums = {int(x) for x in (r.numbers or "").split(",") if x}
        r.hits = len(nums & winners)
        settled += 1
    if settled:
        db.commit()
    return {"settled": settled, "game_type": game_type}
