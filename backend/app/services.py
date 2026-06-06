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


def evaluate_new_draw(db: Session, draw: Draw) -> dict:
    """Critical flow: when a new real (official) draw is added, evaluate the
    pending predictions of the same game type **for every user**, record the
    results, update the reinforcement-learning weights, and retrain the system.
    """
    pending = (
        db.query(Prediction)
        .filter(
            Prediction.game_type == draw.game_type,
            Prediction.status.in_(["pendiente", "usada"]),
        )
        .all()
    )
    new_hits = []
    users_affected = set()
    evaluated = 0
    for pred in pending:
        already = (
            db.query(PredictionResult)
            .filter(PredictionResult.prediction_id == pred.id, PredictionResult.draw_id == draw.id)
            .first()
        )
        if already:
            continue
        result = evaluate_prediction_against_draw(db, pred, draw)
        if result is None:
            continue
        evaluated += 1
        users_affected.add(pred.user_id)
        if result.hits >= 2:
            new_hits.append({
                "prediction_id": pred.id,
                "user_id": pred.user_id,
                "strategy": pred.strategy,
                "hits": result.hits,
                "matched": str_to_numbers(result.matched_numbers) if result.matched_numbers else [],
            })
    db.commit()

    # Retrain the system with the new official result (refresh ML models so the
    # next predictions/backtests include this draw; bandit weights were already
    # updated incrementally during evaluation).
    retrained = retrain_system(draw.game_type, db)

    return {
        "draw_number": draw.draw_number,
        "evaluated": evaluated,
        "users_affected": len(users_affected),
        "new_hits": new_hits,
        "retrained": retrained,
    }


def retrain_system(game_type: str, db: Session) -> dict:
    """Refresh the predictive models for a game after a new official result.

    Clears the cached ML model and refits it (where scikit-learn is available);
    otherwise the heuristic engine already uses the latest data. Always cheap
    and safe to call after each official draw.
    """
    from .engine.game_config import get_game
    from .engine.models_ml import get_model
    try:
        cfg = get_game(game_type)
        history = [r["numbers"] for r in load_draw_rows(db, game_type)]
        model = get_model(game_type, cfg.max_number, history, force=True)
        return {"game_type": game_type, "trained": model.trained, "backend": model.backend,
                "draws": len(history)}
    except Exception as e:
        return {"game_type": game_type, "trained": False, "error": str(e)}
