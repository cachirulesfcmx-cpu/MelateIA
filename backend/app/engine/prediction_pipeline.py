"""The research layer applied to the predictions the user actually plays.

Everything built across v3–v9 lives in the research cycle. This module is what
connects it to the Predicciones tab, so generating tickets with ANY strategy —
Agresiva, Evolutiva, Conservadora, Adaptativa… — goes through the same
machinery.

What it changes, honestly:

  * **Risk filter** — drops calendar-only tickets (every number ≤31), long
    consecutive runs and duplicates. These are worse bets not because they are
    less likely to come out, but because far more people play them, so a prize
    gets split more ways.
  * **Diversification** — caps how much two suggested tickets overlap. Playing
    six near-identical tickets wastes five of them.
  * **Live audit** — each generated set is recorded before the draw with its
    model, seed and data snapshot (rules 30 and 41).
  * **Evidence context** — the current NO_EDGE/EDGE state, this strategy's real
    live record, and the sequential reading, attached to the response.

What it does NOT change: the odds. No filter, ranking or diversification makes
a ticket more likely to win. It buys coverage and avoids shared prizes; the
response says so and the UI repeats it.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from . import live_intelligence as li
from . import portfolio as pf
from . import track_record as trec
from .agents import RiskAgent
from .game_config import GameConfig
from .research_lab import theoretical_random_mean_hits

_risk = RiskAgent()


def apply_research(db: Session, cfg: GameConfig, combos: list[dict], *,
                   strategy: str, seed: int = 42, overlap_limit: int = 4,
                   audit: bool = True, data_snapshot: str = "") -> dict:
    """Filter, diversify, audit and contextualise a batch of generated combos.

    Returns the surviving combos plus a `research` block. Never returns fewer
    than one combo: if the filters would empty the list, the originals are kept
    and the reason is reported — the user asked for suggestions, not for an
    empty screen.
    """
    original = list(combos)
    requested = len(original)
    if not original:
        return {"combos": [], "research": {"applied": False,
                                           "reason": "sin combinaciones que procesar"}}

    # 1. risk filter — same rules the research cycle uses for its candidates
    checked = _risk.validate([c["numbers"] for c in original], cfg)
    accepted = {tuple(n) for n in checked["accepted"]}
    survivors = [c for c in original if tuple(sorted(c["numbers"])) in accepted]

    # 2. diversification — cap the overlap between suggestions
    engine = pf.PortfolioEngine(cfg)
    cands = [pf.Candidate(tuple(sorted(c["numbers"])), float(c.get("score", 0.0)),
                          c.get("strategy", strategy)) for c in survivors]
    chosen = engine.diversify(cands, size=requested, overlap_limit=overlap_limit)
    chosen_keys = [tuple(c.numbers) for c in chosen]
    by_key = {tuple(sorted(c["numbers"])): c for c in survivors}
    final = [by_key[k] for k in chosen_keys if k in by_key]

    fallback_reason = None
    if not final:
        final = original
        fallback_reason = ("Los filtros habrían dejado la lista vacía; se conservan "
                           "las combinaciones originales.")

    coverage = engine.coverage([pf.Candidate(tuple(sorted(c["numbers"])),
                                             float(c.get("score", 0.0)), strategy)
                                for c in final])

    # 3. live audit (rules 30 and 41)
    run_id = uuid.uuid4().hex[:12]
    audited = 0
    if audit and db is not None:
        for c in final:
            try:
                trec.record_audit(
                    db, run_id=run_id, game_type=cfg.key, model=strategy,
                    model_version=f"{strategy}-{run_id}", seed=seed,
                    data_snapshot=data_snapshot, numbers=c["numbers"],
                    source="predictions")
                audited += 1
            except Exception:
                break

    # 4. evidence context — what the research layer currently knows
    evidence = _evidence(db, cfg, strategy)

    return {
        "combos": final,
        "research": {
            "applied": True,
            "run_id": run_id,
            "requested": requested,
            "returned": len(final),
            "risk_filter": {k: v for k, v in checked.items() if k != "accepted"},
            "diversification": {
                "overlap_limit": overlap_limit,
                "mean_overlap": coverage["mean_overlap"],
                "max_overlap": coverage["max_overlap"],
                "distinct_numbers": coverage["distinct_numbers"],
                "coverage_share": coverage["coverage_share"],
            },
            "audited_predictions": audited,
            "fallback_reason": fallback_reason,
            **evidence,
            "disclaimer": (
                "Filtrar y diversificar NO aumenta la probabilidad de ganar. Evita "
                "combinaciones que mucha gente juega (y con las que compartirías el "
                "premio) y evita repetir números entre tus boletos. La probabilidad "
                "de cada boleto sigue siendo la misma."),
        },
    }


def _evidence(db: Session, cfg: GameConfig, strategy: str) -> dict:
    """Current evidence state plus this strategy's real live record."""
    out: dict = {"edge_mode": "NO_EDGE", "edge_message": None,
                 "live": None, "sequential": None}
    if db is None:
        return out

    # NO_EDGE / EDGE_CANDIDATE from the recorded model cards
    try:
        from ..models import ModelCard

        rows = (db.query(ModelCard)
                .filter(ModelCard.game_type == cfg.key)
                .order_by(ModelCard.created_at.desc(), ModelCard.id.desc())
                .limit(30).all())
        ev = [{
            "model": r.model_name,
            "q_value": r.bh_q if r.bh_q is not None else 1.0,
            "permutation_p": r.permutation_p if r.permutation_p is not None else 1.0,
            "golden_holdout_delta": ((r.golden_holdout_score or 0.0) - (r.random_baseline or 0.0))
            if r.golden_holdout_score is not None else 0.0,
            "replicated": bool(r.replication_passed),
            "base_rate_warning": bool(r.looks_like_base_rate),
            "score": r.observed_delta or 0.0,
        } for r in rows]
        edge = pf.evaluate_edge(ev)
        out["edge_mode"] = edge["mode"]
        out["edge_message"] = edge["message"]
    except Exception:
        pass

    # this strategy's own live record, with the sequential reading
    try:
        record = trec.live_track_record(db, cfg.key)
        if record.get("games"):
            block = (record.get("by_strategy") or {}).get(strategy)
            out["live"] = {
                "overall_games": record["games"],
                "overall_mean_hits": record["mean_hits"],
                "random_mean_hits": record["random_mean_hits"],
                "strategy_games": (block or {}).get("games", 0),
                "strategy_mean_hits": (block or {}).get("mean_hits"),
                "strategy_edge": (block or {}).get("edge_vs_random"),
                "reading": record.get("reading"),
            }
            hits = _strategy_hits(db, cfg.key, strategy)
            if len(hits) >= 2:
                baseline = theoretical_random_mean_hits(cfg.max_number, cfg.pick)
                # every draw is another look at the same record, so the interval
                # is widened accordingly instead of being read fresh each time
                out["sequential"] = li.analyze(hits, baseline,
                                               looks=max(1, len(hits))).as_dict()
    except Exception:
        pass
    return out


def _strategy_hits(db: Session, game_type: str, strategy: str) -> list[int]:
    from ..models import Prediction, PredictionResult

    rows = (db.query(PredictionResult.hits)
            .join(Prediction, PredictionResult.prediction_id == Prediction.id)
            .filter(Prediction.game_type == game_type,
                    Prediction.strategy == strategy)
            .order_by(PredictionResult.evaluated_at.asc())
            .all())
    return [int(r[0] or 0) for r in rows]
