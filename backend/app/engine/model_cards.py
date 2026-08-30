"""Model cards — the provenance record of every evaluated model.

A card answers, for one model, the question "why is it where it is": what data
it saw, how it scored, which gate stopped it, and the resulting decision. The
reference package defines the dataclass; here the cards are also generated
automatically from a research run, persisted, and served.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class ModelCardData:
    model: str
    version: str
    game: str
    role: str = "challenger"
    data_snapshot: str = ""
    train_samples: int = 0
    validation_samples: int = 0
    walk_forward_mean_hits: float | None = None
    random_baseline: float | None = None
    observed_delta: float | None = None
    permutation_p: float | None = None
    bootstrap_low: float | None = None
    bootstrap_high: float | None = None
    bh_q: float | None = None
    golden_holdout_score: float | None = None
    replication_passed: bool = False
    looks_like_base_rate: bool = False
    stability_verdict: str = ""
    decision: str = "CHALLENGER"
    blocked_by: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)


def card_from_run(run: dict, arm: dict) -> ModelCardData:
    """Build the card of one evaluated arm out of a finished research run."""
    baseline = (run.get("baseline") or {}).get("mean_hits")
    perm = (run.get("permutation_tests") or {}).get(arm.get("model_name"), {})
    boot = ((run.get("block_bootstrap") or {}).get("best_arm_hits") or {})
    if boot.get("arm") != arm.get("model_name"):
        boot = {}
    golden = run.get("golden_holdout") or {}
    gev = (golden.get("evaluation") or {})
    gate = run.get("replication_gate") or {}
    queue = run.get("confirmation_queue") or {}

    decision = "CHALLENGER"
    if run.get("promotion", {}).get("promoted") and \
            run["promotion"].get("model_name") == arm.get("model_name"):
        decision = "CHAMPION"
    elif arm.get("accepted"):
        decision = "PENDING_REPLICATION"

    return ModelCardData(
        model=arm.get("model_name", "?"),
        version=f"{arm.get('model_name')}-{run.get('run_id', '')}",
        game=run.get("game_type", ""),
        role="champion" if decision == "CHAMPION" else "challenger",
        data_snapshot=golden.get("sha256", ""),
        train_samples=int(run.get("selection_draws") or 0),
        validation_samples=int(arm.get("metrics", {}).get("n") or 0),
        walk_forward_mean_hits=arm.get("metrics", {}).get("mean_hits"),
        random_baseline=baseline,
        observed_delta=arm.get("edge_vs_random"),
        permutation_p=perm.get("p_value"),
        bootstrap_low=(boot.get("ci95") or [None, None])[0],
        bootstrap_high=(boot.get("ci95") or [None, None])[1],
        bh_q=arm.get("q_value"),
        golden_holdout_score=gev.get("metrics", {}).get("mean_hits") if gev else None,
        replication_passed=bool(gate.get("passed")),
        looks_like_base_rate=False,
        decision=decision,
        blocked_by=list(gate.get("missing") or []),
        extra={
            "lab": arm.get("lab"),
            "label": arm.get("label"),
            "windows_won": arm.get("windows_won"),
            "reason": arm.get("reason"),
            "confirmations": queue.get("confirmations"),
            "required_confirmations": queue.get("required"),
        },
    )


def card_from_worker(payload: dict, version: str) -> ModelCardData:
    """Build the card of a Training Worker run."""
    stability = (payload.get("stability") or {})
    ablation = (payload.get("ablation_protocol") or {})
    return ModelCardData(
        model=f"worker_{payload.get('model', '?')}",
        version=version,
        game=payload.get("game", ""),
        role="challenger",
        data_snapshot=str(payload.get("draws", "")),
        train_samples=int(payload.get("train_samples") or 0),
        validation_samples=int(payload.get("validation_samples") or 0),
        walk_forward_mean_hits=payload.get("validation_mean_hits"),
        random_baseline=payload.get("random_mean_hits"),
        observed_delta=payload.get("edge_vs_random"),
        looks_like_base_rate=bool(payload.get("looks_like_base_rate")),
        stability_verdict=str(stability.get("verdict") or ""),
        decision="CHALLENGER",
        blocked_by=["protocolo completo no ejecutado sobre este modelo"],
        extra={
            "framework": payload.get("framework"),
            "epochs": payload.get("epochs"),
            "lookback": payload.get("lookback"),
            "channels": payload.get("channels"),
            "flat_predictions": payload.get("flat_predictions"),
            "close_to_base_rate": payload.get("close_to_base_rate"),
            "ablation_reading": ablation.get("reading"),
            "stability_reading": stability.get("reading"),
        },
    )


def persist(db, card: ModelCardData, run_id: str = "") -> None:
    from ..models import ModelCard

    db.add(ModelCard(
        game_type=card.game, model_name=card.model, version=card.version,
        role=card.role, data_snapshot=card.data_snapshot,
        train_samples=card.train_samples, validation_samples=card.validation_samples,
        walk_forward_mean_hits=card.walk_forward_mean_hits,
        random_baseline=card.random_baseline, observed_delta=card.observed_delta,
        permutation_p=card.permutation_p, bootstrap_low=card.bootstrap_low,
        bootstrap_high=card.bootstrap_high, bh_q=card.bh_q,
        golden_holdout_score=card.golden_holdout_score,
        replication_passed=card.replication_passed,
        looks_like_base_rate=card.looks_like_base_rate,
        stability_verdict=card.stability_verdict, decision=card.decision,
        extra=json.dumps({"blocked_by": card.blocked_by, **card.extra}, default=str),
        run_id=run_id or card.version,
    ))
