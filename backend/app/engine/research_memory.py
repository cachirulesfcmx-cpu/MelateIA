"""Research Memory 2.0 — persistent, so it actually prevents repetition.

An experiment is identified by a SHA-256 of (game, hypothesis, params). Asking
the same question again with the same settings is not new evidence; it is
another draw from the same lottery of p-values, and repeating it is how a
"finding" eventually appears by chance. The memory is stored in the database
rather than a process dict, because a memory that empties on restart prevents
nothing across cycles.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session


def fingerprint(game: str, hypothesis: str, params: dict | None = None) -> str:
    payload = json.dumps([game, hypothesis.strip().lower(), params or {}],
                         sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def seen_equivalent(db: Session, game: str, hypothesis: str,
                    params: dict | None = None) -> bool:
    from ..models import ResearchMemory

    fp = fingerprint(game, hypothesis, params)
    return db.query(ResearchMemory).filter(ResearchMemory.fingerprint == fp).first() is not None


def remember(db: Session, game: str, hypothesis: str, params: dict | None = None,
             result: dict | None = None) -> dict:
    """Record an experiment, or bump the counter if it was already asked."""
    from ..models import ResearchMemory

    fp = fingerprint(game, hypothesis, params)
    row = db.query(ResearchMemory).filter(ResearchMemory.fingerprint == fp).first()
    if row is None:
        row = ResearchMemory(
            fingerprint=fp, game_type=game, hypothesis=hypothesis,
            params=json.dumps(params or {}, default=str),
            result=json.dumps(result or {}, default=str), times_seen=1,
        )
        db.add(row)
        db.commit()
        return {"fingerprint": fp, "new": True, "times_seen": 1}
    row.times_seen = (row.times_seen or 0) + 1
    if result:
        row.result = json.dumps(result, default=str)
    db.commit()
    return {"fingerprint": fp, "new": False, "times_seen": row.times_seen}


def filter_new(db: Session, game: str, hypotheses: list[str],
               params: dict | None = None) -> dict:
    """Split a candidate list into genuinely new questions and repeats."""
    new, repeats = [], []
    for h in hypotheses:
        (repeats if seen_equivalent(db, game, h, params) else new).append(h)
    return {"new": new, "already_asked": repeats,
            "note": ("Repetir una hipótesis equivalente no aporta evidencia nueva: "
                     "solo añade otra oportunidad de que el azar produzca un "
                     "resultado llamativo.")}


def listing(db: Session, game_type: str | None = None, limit: int = 50) -> list[dict]:
    from ..models import ResearchMemory

    q = db.query(ResearchMemory)
    if game_type:
        q = q.filter(ResearchMemory.game_type == game_type)
    rows = q.order_by(ResearchMemory.updated_at.desc()).limit(limit).all()
    out = []
    for r in rows:
        try:
            params = json.loads(r.params or "{}")
            result = json.loads(r.result or "{}")
        except Exception:
            params, result = {}, {}
        out.append({
            "fingerprint": r.fingerprint[:16], "game_type": r.game_type,
            "hypothesis": r.hypothesis, "params": params, "result": result,
            "times_seen": r.times_seen, "updated_at": r.updated_at,
        })
    return out


def summary(db: Session, game_type: str | None = None) -> dict:
    from ..models import ResearchMemory

    q = db.query(ResearchMemory)
    if game_type:
        q = q.filter(ResearchMemory.game_type == game_type)
    rows = q.all()
    repeated = sum(1 for r in rows if (r.times_seen or 0) > 1)
    return {"experiments": len(rows), "repeated_attempts": repeated,
            "total_asks": sum((r.times_seen or 1) for r in rows)}
