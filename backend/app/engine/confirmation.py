"""Confirmation Queue — replication gate between Golden Holdout and Champion.

    GOLDEN HOLDOUT → CONFIRMATION QUEUE → CHALLENGER / CHAMPION

A candidate that clears every statistical gate still does not become Champion on
the strength of a single run. It enters this queue and has to repeat the result
in independent runs (different seeds). Requiring replication is what separates a
finding from a fluke, and it is the last thing standing between "this model won
once" and "this model is deployed".

A candidate that later fails is not silently forgotten: it is marked as
discarded, with the run that broke it recorded.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

REQUIRED_CONFIRMATIONS = 2


def _load(raw: str | None, default):
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def submit(db: Session, game_type: str, model_name: str, run_id: str, seed: int,
           evidence: dict, required: int = REQUIRED_CONFIRMATIONS) -> dict:
    """Register a passing candidate, or add a confirmation if already queued."""
    from ..models import ConfirmationQueue

    row = (db.query(ConfirmationQueue)
           .filter(ConfirmationQueue.game_type == game_type,
                   ConfirmationQueue.model_name == model_name)
           .first())
    if row is None:
        row = ConfirmationQueue(
            game_type=game_type, model_name=model_name, status="pendiente",
            confirmations=1, required=required, first_run_id=run_id,
            last_run_id=run_id, seeds=json.dumps([seed]),
            evidence=json.dumps(evidence, default=str),
        )
        db.add(row)
        db.commit()
        return _out(row, "encolado",
                    f"Candidato encolado: necesita {required} confirmaciones independientes, tiene 1.")

    if row.status in ("promovido", "descartado"):
        # a previously resolved entry starts a fresh replication cycle
        row.status = "pendiente"
        row.confirmations = 1
        row.seeds = json.dumps([seed])
    else:
        seeds = _load(row.seeds, [])
        if seed not in seeds:       # only INDEPENDENT runs count
            seeds.append(seed)
            row.confirmations = (row.confirmations or 0) + 1
            row.seeds = json.dumps(seeds)
    row.last_run_id = run_id
    row.evidence = json.dumps(evidence, default=str)

    if (row.confirmations or 0) >= (row.required or required):
        row.status = "confirmado"
        db.commit()
        return _out(row, "confirmado",
                    f"Replicado en {row.confirmations} corridas independientes: "
                    f"puede promoverse a Champion.")
    db.commit()
    return _out(row, "pendiente",
                f"Confirmaciones {row.confirmations}/{row.required}: aún no se promueve.")


def fail(db: Session, game_type: str, model_name: str, run_id: str, reason: str) -> dict | None:
    """A queued candidate that stopped passing is discarded, not forgotten."""
    from ..models import ConfirmationQueue

    row = (db.query(ConfirmationQueue)
           .filter(ConfirmationQueue.game_type == game_type,
                   ConfirmationQueue.model_name == model_name)
           .first())
    if row is None or row.status in ("descartado", "promovido"):
        return None
    row.status = "descartado"
    row.last_run_id = run_id
    ev = _load(row.evidence, {})
    ev["discarded_reason"] = reason
    row.evidence = json.dumps(ev, default=str)
    db.commit()
    return _out(row, "descartado", reason)


def mark_promoted(db: Session, game_type: str, model_name: str) -> None:
    from ..models import ConfirmationQueue
    row = (db.query(ConfirmationQueue)
           .filter(ConfirmationQueue.game_type == game_type,
                   ConfirmationQueue.model_name == model_name)
           .first())
    if row is not None:
        row.status = "promovido"
        db.commit()


def listing(db: Session, game_type: str | None = None, limit: int = 50) -> list[dict]:
    from ..models import ConfirmationQueue
    q = db.query(ConfirmationQueue)
    if game_type:
        q = q.filter(ConfirmationQueue.game_type == game_type)
    rows = q.order_by(ConfirmationQueue.updated_at.desc()).limit(limit).all()
    return [{
        "game_type": r.game_type, "model_name": r.model_name, "status": r.status,
        "confirmations": r.confirmations, "required": r.required,
        "seeds": _load(r.seeds, []), "first_run_id": r.first_run_id,
        "last_run_id": r.last_run_id, "evidence": _load(r.evidence, {}),
        "updated_at": r.updated_at,
    } for r in rows]


def _out(row, action: str, message: str) -> dict:
    return {
        "action": action,
        "message": message,
        "model_name": row.model_name,
        "status": row.status,
        "confirmations": row.confirmations,
        "required": row.required,
        "ready_to_promote": row.status == "confirmado",
    }
