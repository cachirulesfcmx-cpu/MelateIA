"""v8 — Research meta-learner.

Learns which families of models have been worth the effort, and prioritizes the
experiment budget accordingly. Rule 24 is absolute: it orders spending, it never
moves alpha, BH, permutation, the Golden Holdout or the Champion Gate. Deciding
where to look is a different power from deciding what counts as a finding.

Two differences from the reference implementation:

  * It reads the experiments ALREADY recorded in the database instead of a
    `defaultdict` that empties on restart. A "continuous learning" system that
    forgets everything between deploys learns nothing.
  * With no history for a family the priority is 1.0 — deliberately optimistic,
    so an untried family gets a first chance instead of being starved by a
    score of zero.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

FAMILIES = ("statistical", "classical_ml", "deep_learning", "qnn", "portfolio")


def family_of(model_name: str) -> str:
    name = (model_name or "").lower()
    if name.startswith("ml_"):
        return "classical_ml"
    if name.startswith("worker_qnn") or name == "qnn":
        return "qnn"
    if name.startswith("worker_"):
        return "deep_learning"
    if name in ("ensemble_genius", "random_baseline"):
        return "statistical"
    return "statistical"


def _useful(metrics: dict) -> bool:
    """An experiment 'paid off' only if it survived correction."""
    q = metrics.get("q_value", metrics.get("bh_q", 1.0))
    try:
        q = float(q)
    except (TypeError, ValueError):
        q = 1.0
    return q < 0.05


def learn(db: Session, game_type: str | None = None, limit: int = 400) -> dict:
    """Aggregate the recorded experiments into per-family statistics."""
    from ..models import Experiment

    q = db.query(Experiment)
    if game_type:
        q = q.filter(Experiment.game_type == game_type)
    rows = q.order_by(Experiment.created_at.desc(), Experiment.id.desc()).limit(limit).all()

    stats: dict[str, dict] = {f: {"n": 0, "wins": 0, "replications": 0} for f in FAMILIES}
    for r in rows:
        fam = family_of(r.model_name)
        if fam not in stats:
            continue
        try:
            metrics = json.loads(r.metrics or "{}")
        except Exception:
            metrics = {}
        s = stats[fam]
        s["n"] += 1
        s["wins"] += int(_useful(metrics))
        s["replications"] += int(r.status in ("champion", "candidate"))

    priorities = {}
    for fam, s in stats.items():
        if not s["n"]:
            priorities[fam] = 1.0            # never tried: give it a chance
        else:
            priorities[fam] = round((s["wins"] + 0.5 * s["replications"]) / s["n"], 4)

    ranked = sorted(priorities.items(), key=lambda kv: kv[1], reverse=True)
    tried = {f: s for f, s in stats.items() if s["n"]}
    barren = [f for f, s in tried.items() if s["wins"] == 0]
    return {
        "experiments_considered": len(rows),
        "stats": stats,
        "priorities": priorities,
        "ranking": [f for f, _ in ranked],
        "reading": (
            (f"{len(tried)} familia(s) con historial; "
             + (f"ninguna ha producido un resultado que sobreviva la corrección "
                f"({', '.join(barren)})." if len(barren) == len(tried) and tried
                else f"{len(tried) - len(barren)} con al menos un resultado corregido."))
            if tried else "Sin historial todavía: todas las familias parten iguales."),
        "authority": ("El meta-learner prioriza presupuesto. No modifica alfa, BH, "
                      "permutación, Golden Holdout ni la compuerta de Champion."),
    }


def allocate(db: Session, game_type: str | None = None, budget=None) -> dict:
    """Budget report weighted by what has historically been worth trying."""
    from .continuous import ExperimentBudget

    meta = learn(db, game_type)
    eb = budget or ExperimentBudget()
    base = eb.allocation()
    priorities = meta["priorities"]
    total_priority = sum(priorities.values()) or 1.0
    total_budget = sum(base.values())
    suggested = {
        f: max(1, round(total_budget * (priorities.get(f, 1.0) / total_priority)))
        for f in base
    }
    return {
        **eb.report(priorities),
        "suggested_allocation": suggested,
        "meta": meta,
        "note": ("La reasignación sugerida cambia dónde se gasta esfuerzo, nunca "
                 "el umbral que un modelo debe superar para promoverse."),
    }
