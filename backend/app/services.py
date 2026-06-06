"""Service layer: bridges the database with the prediction engine."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Draw, Prediction, PredictionResult
from .engine.game_config import get_game, GameConfig
from .engine.data_engine import str_to_numbers, build_stats_from_draws
from .engine.features import GameStats
from .engine import bandit


def load_draw_rows(db: Session, game_type: str) -> list[dict]:
    rows = (
        db.query(Draw)
        .filter(Draw.game_type == game_type)
        .order_by(Draw.draw_number.asc())
        .all()
    )
    return [
        {
            "id": d.id,
            "draw_number": d.draw_number,
            "draw_date": d.draw_date,
            "numbers": str_to_numbers(d.numbers),
            "additional": d.additional,
        }
        for d in rows
    ]


def build_stats(db: Session, game_type: str) -> tuple[GameStats, GameConfig]:
    cfg = get_game(game_type)
    rows = load_draw_rows(db, game_type)
    return build_stats_from_draws(rows, cfg), cfg


def evaluate_prediction_against_draw(db: Session, pred: Prediction, draw: Draw) -> PredictionResult | None:
    """Compare a prediction to a draw, persist the result, update bandit weights."""
    # avoid double-evaluating the same pair
    existing = (
        db.query(PredictionResult)
        .filter(PredictionResult.prediction_id == pred.id, PredictionResult.draw_id == draw.id)
        .first()
    )
    if existing:
        return existing

    pred_nums = set(str_to_numbers(pred.numbers))
    draw_nums = set(str_to_numbers(draw.numbers))
    matched = sorted(pred_nums & draw_nums)
    missed = sorted(pred_nums - draw_nums)
    hits = len(matched)

    result = PredictionResult(
        prediction_id=pred.id,
        draw_id=draw.id,
        hits=hits,
        matched_numbers=",".join(map(str, matched)),
        missed_numbers=",".join(map(str, missed)),
    )
    db.add(result)

    if pred.status == "pendiente":
        pred.status = "comparada"

    # reinforcement learning update
    bandit.update_on_result(db, pred.strategy, pred.game_type, hits)
    db.flush()
    return result


def evaluate_new_draw(db: Session, draw: Draw) -> list[dict]:
    """Critical flow: when a new real draw is added, evaluate all pending
    predictions of the same game type that were created before this draw."""
    pending = (
        db.query(Prediction)
        .filter(
            Prediction.game_type == draw.game_type,
            Prediction.status.in_(["pendiente", "usada"]),
        )
        .all()
    )
    new_hits = []
    for pred in pending:
        # only evaluate predictions made before the draw existed
        already = (
            db.query(PredictionResult)
            .filter(PredictionResult.prediction_id == pred.id, PredictionResult.draw_id == draw.id)
            .first()
        )
        if already:
            continue
        result = evaluate_prediction_against_draw(db, pred, draw)
        if result and result.hits >= 2:
            new_hits.append({
                "prediction_id": pred.id,
                "strategy": pred.strategy,
                "hits": result.hits,
                "matched": str_to_numbers(result.matched_numbers) if result.matched_numbers else [],
            })
    db.commit()
    return new_hits
