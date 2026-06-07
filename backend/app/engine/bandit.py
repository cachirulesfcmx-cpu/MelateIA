"""Reinforcement learning: multi-armed bandit over strategies.

Each strategy is an arm. When a real draw evaluates a prediction, the strategy
that produced it is rewarded in proportion to the hits it achieved. Weights are
updated with an exponential-recency rule and persisted in ``model_performance``.
The weights bias which strategies the "híbrida" recommender trusts and are shown
to the user as the evolving system performance.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import ModelPerformance, LearningLog


REWARD_TABLE = {0: -0.05, 1: -0.02, 2: 0.15, 3: 0.5, 4: 1.5, 5: 4.0, 6: 10.0}
ALPHA = 0.15  # learning rate


def get_or_create(db: Session, strategy: str, game_type: str) -> ModelPerformance:
    perf = (
        db.query(ModelPerformance)
        .filter(ModelPerformance.strategy == strategy, ModelPerformance.game_type == game_type)
        .first()
    )
    if perf is None:
        perf = ModelPerformance(strategy=strategy, game_type=game_type, weight=1.0)
        db.add(perf)
        db.flush()
    return perf


def update_on_result(db: Session, strategy: str, game_type: str, hits: int) -> ModelPerformance:
    perf = get_or_create(db, strategy, game_type)
    perf.total_predictions = (perf.total_predictions or 0) + 1
    perf.total_hits = (perf.total_hits or 0) + hits
    perf.average_hits = round(perf.total_hits / perf.total_predictions, 4)
    perf.best_hits = max(perf.best_hits or 0, hits)

    reward = REWARD_TABLE.get(hits, 0.0)
    # exponential update, clamped to a sane band
    new_weight = perf.weight * (1 - ALPHA) + (perf.weight + reward) * ALPHA
    perf.weight = max(0.1, min(8.0, round(new_weight, 4)))

    # append an evolution snapshot for the analytics timeline
    db.add(LearningLog(
        strategy=strategy, game_type=game_type, hits=hits,
        weight=perf.weight, average_hits=perf.average_hits,
    ))
    db.flush()
    return perf


def normalized_weights(db: Session, game_type: str) -> dict[str, float]:
    rows = db.query(ModelPerformance).filter(ModelPerformance.game_type == game_type).all()
    total = sum(r.weight for r in rows) or 1.0
    return {r.strategy: round(r.weight / total, 4) for r in rows}
