"""Autonomous research cycle — v5 state machine, hypothesis generator and
replication gate.

The agent does not re-run itself for nothing: with no new official draw there
is no new evidence, so the correct decision is WAIT. When a draw does arrive it
walks the fifteen protocol states in order.
"""
from __future__ import annotations

from dataclasses import dataclass

# Hypotheses the agent can still open, beyond the ones already pre-registered.
CATALOG: list[str] = [
    "Dependencia temporal no lineal",
    "Cambio de régimen detectable",
    "Dependencia condicional entre pares",
    "Interacciones de triples",
    "Información mutua no lineal",
    "Estructura local preservada bajo block bootstrap",
    "Ventaja de ensemble sobre todos los baselines",
]

STATES: list[str] = [
    "INGEST", "AUDIT", "REGISTER_HYPOTHESES", "RUN_STATISTICS",
    "RUN_CLASSICAL", "RUN_DEEP", "RUN_PERMUTATION", "RUN_BLOCK_BOOTSTRAP",
    "MULTIPLE_TESTING", "GOLDEN_HOLDOUT", "REPLICATION",
    "CONFIRMATION_QUEUE", "CHAMPION_DECISION", "CANDIDATES", "REPORT",
]


@dataclass
class ResearchDecision:
    action: str
    reason: str

    def as_dict(self) -> dict:
        return {"action": self.action, "reason": self.reason}


class AutonomousResearchCycle:
    """Plans the states to execute, and knows when NOT to run."""

    STATES = STATES

    def plan(self, game: str, new_draw: bool = True,
             last_run_draws: int | None = None,
             current_draws: int | None = None) -> dict:
        if last_run_draws is not None and current_draws is not None:
            new_draw = current_draws > last_run_draws
        if not new_draw:
            decision = ResearchDecision(
                "WAIT", "No hay sorteo nuevo desde el último ciclo: sin evidencia "
                        "nueva, repetir el análisis solo multiplicaría pruebas.")
            return {"game": game, "run": False, "decisions": [decision.as_dict()],
                    "states": []}
        return {
            "game": game,
            "run": True,
            "decisions": [ResearchDecision(s, "etapa requerida del protocolo").as_dict()
                          for s in self.STATES],
            "states": list(self.STATES),
        }


def generate_hypotheses(existing: list[str]) -> list[str]:
    """Catalog entries not yet on record — deduplicated case-insensitively."""
    seen = {e.strip().lower() for e in existing}
    out = []
    for h in CATALOG:
        if h.strip().lower() not in seen and not any(h.lower() in e for e in seen):
            out.append(h)
    return out


def replication_gate(q_value: float, permutation_p: float, holdout_score: float,
                     baseline: float, confirmations: int = 0,
                     required_confirmations: int = 2) -> dict:
    """Every condition that must hold before a Champion exists.

    Each one is reported separately so a failure says exactly what was missing
    instead of a bare "not promoted".
    """
    checks = {
        "q_corregido_bajo_alpha": bool(q_value < 0.05),
        "permutacion_significativa": bool(permutation_p < 0.05),
        "supera_golden_holdout": bool(holdout_score > baseline),
        "replicacion_independiente": bool(confirmations >= required_confirmations),
    }
    missing = [k for k, ok in checks.items() if not ok]
    return {
        "passed": not missing,
        "checks": checks,
        "missing": missing,
        "requires": ["q<0.05", "permutación p<0.05", "holdout > baseline",
                     f"replicación independiente ({required_confirmations} corridas)"],
        "reason": ("Todas las compuertas superadas." if not missing
                   else "Faltan: " + ", ".join(missing) + "."),
    }
