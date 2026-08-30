"""Autonomous Researcher — proposes experiments, cannot move the goalposts.

The v6 documentation states that the researcher "puede proponer/ordenar
experimentos, pero no puede cambiar umbrales, BH, Golden Holdout ni reglas de
Champion". A sentence in a document is not a constraint, so here it is enforced:
`propose()` returns actions, and every action is passed through `validate()`,
which rejects anything touching the protected surface. An agent that could
lower its own bar would make the entire protocol decorative.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .autonomous_cycle import CATALOG, STATES, generate_hypotheses

# Actions the researcher is allowed to order.
ALLOWED_ACTIONS = {
    "REGISTER_HYPOTHESIS",
    "RUN_ABLATIONS",
    "RUN_MULTI_SEED",
    "RUN_LOOKBACK_SWEEP",
    "RUN_PERMUTATION",
    "RUN_BLOCK_BOOTSTRAP",
    "APPLY_BH",
    "RUN_GOLDEN_HOLDOUT",
    "RUN_REPLICATION",
    "RUN_STATISTICS",
    "RUN_CLASSICAL",
    "RUN_DEEP",
    "REPORT",
}

# Anything that would change the standard of evidence itself.
PROTECTED = {
    "alpha", "min_improvement", "minimum_improvement", "max_p_value",
    "maximum_q_value", "threshold", "thresholds", "bh", "benjamini",
    "fdr", "golden_holdout", "holdout_ratio", "champion", "promotion",
    "required_confirmations", "constitution", "rules", "max_weight_delta",
}

SEEDS = [7, 17, 42, 101, 2026]
LOOKBACKS = [8, 16, 32, 64, 96]


@dataclass
class ResearchAction:
    kind: str
    payload: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def validate(action: ResearchAction) -> tuple[bool, str]:
    """Reject any action outside the allowed set or touching protected settings."""
    if action.kind not in ALLOWED_ACTIONS:
        return False, f"acción no permitida: {action.kind}"
    for key, value in (action.payload or {}).items():
        k = str(key).strip().lower()
        if any(p in k for p in PROTECTED):
            return False, (f"la acción intenta modificar '{key}', que pertenece al "
                           f"estándar de evidencia y es inmutable para el agente")
        if isinstance(value, str) and any(p == value.strip().lower() for p in PROTECTED):
            return False, f"la acción apunta a '{value}', que es inmutable para el agente"
    return True, "ok"


class AutonomousResearcher:
    """Plans the next experiments for a game, within its authority."""

    STATES = STATES

    def __init__(self, game: str):
        self.game = game

    def propose(self, existing_hypotheses: list[str] | None = None) -> list[ResearchAction]:
        new = generate_hypotheses(existing_hypotheses or [])
        actions = [ResearchAction("REGISTER_HYPOTHESIS", {"statement": h}) for h in new]
        actions += [
            ResearchAction("RUN_ABLATIONS", {"configurations": 7}),
            ResearchAction("RUN_MULTI_SEED", {"seeds": SEEDS}),
            ResearchAction("RUN_LOOKBACK_SWEEP", {"lookbacks": LOOKBACKS}),
            ResearchAction("RUN_PERMUTATION", {}),
            ResearchAction("RUN_BLOCK_BOOTSTRAP", {}),
            ResearchAction("APPLY_BH", {}),
            ResearchAction("RUN_GOLDEN_HOLDOUT", {}),
            ResearchAction("RUN_REPLICATION", {}),
        ]
        return actions

    def plan(self, existing_hypotheses: list[str] | None = None) -> dict:
        proposed = self.propose(existing_hypotheses)
        approved, rejected = [], []
        for a in proposed:
            ok, reason = validate(a)
            (approved if ok else rejected).append({**a.as_dict(), "reason": reason})
        return {
            "game": self.game,
            "states": list(self.STATES),
            "approved": approved,
            "rejected": rejected,
            "authority": {
                "may": sorted(ALLOWED_ACTIONS),
                "may_not": sorted(PROTECTED),
                "note": ("El investigador ordena experimentos; no puede mover el umbral "
                         "que esos experimentos deben superar. Si pudiera, el protocolo "
                         "sería decorativo."),
            },
            "hypothesis_catalog": CATALOG,
        }
