"""v8 — Continuous learning: drift, decay, early stopping, budget.

The reference package defines a `DriftTrigger` that receives a `drift_score`
nothing ever computes. Here the score comes from the L1 drift the statistical
lab already measures, normalized against the drift pure sampling noise would
produce — so "drift" means something instead of being a free parameter.

Constitution rule 27 is the important one: drift opens MORE research, it never
promotes anything by itself. A regime change is a reason to look harder, not
evidence that a model works.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import research_lab as rlab
from .game_config import GameConfig


# --------------------------------------------------------------------------- #
# Drift
# --------------------------------------------------------------------------- #
@dataclass
class DriftDecision:
    detected: bool
    score: float
    observed_l1: float
    noise_reference: float
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


class DriftTrigger:
    """Turns the measured L1 drift into a decision.

    `score` is the excess over what sampling noise alone yields:
    ``l1 / reference - 1``. Zero means "exactly as noisy as chance"; positive
    means the distribution moved more than chance explains.
    """

    def evaluate(self, score: float, threshold: float = 0.05) -> DriftDecision:
        score = float(score)
        detected = score >= threshold
        return DriftDecision(
            detected=detected, score=round(score, 5),
            observed_l1=0.0, noise_reference=0.0,
            reason=("DRIFT_DETECTED" if detected else "NO_MATERIAL_DRIFT"))

    def from_history(self, draws: list, cfg: GameConfig, window: int = 200,
                     threshold: float = 0.05) -> DriftDecision:
        """Compute the score from the data instead of receiving it."""
        d = rlab.drift_l1(draws, cfg.max_number, window=window)
        if not d.get("available"):
            return DriftDecision(False, 0.0, 0.0, 0.0,
                                 f"Historial insuficiente para medir deriva "
                                 f"(se requieren {2 * window} sorteos).")
        ref = d["sampling_reference"] or 1e-9
        score = (d["l1"] / ref) - 1.0
        detected = score >= threshold
        return DriftDecision(
            detected=detected, score=round(score, 5),
            observed_l1=d["l1"], noise_reference=d["sampling_reference"],
            reason=(f"Deriva L1 {d['l1']:.4f} frente a {d['sampling_reference']:.4f} "
                    f"esperado por muestreo: "
                    + ("cambio de régimen, se amplía la investigación."
                       if detected else
                       "compatible con azar estacionario, sin investigación extra.")))


# --------------------------------------------------------------------------- #
# Champion decay
# --------------------------------------------------------------------------- #
@dataclass
class ChampionState:
    model: str
    active: bool = True
    degradation_count: int = 0
    history: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


class ChampionDecay:
    """A Champion is re-evaluated every cycle; persistent decay retires it.

    Rules 28 and 29: being promoted once is not a permanent title. If the edge
    stops showing up, the title goes away — otherwise the system would keep
    recommending a model that no longer works.
    """

    def evaluate(self, champion: ChampionState, current_delta: float,
                 min_delta: float = 0.0, max_bad_cycles: int = 3) -> ChampionState:
        if current_delta <= min_delta:
            champion.degradation_count += 1
        else:
            champion.degradation_count = 0
        champion.history.append(round(float(current_delta), 5))
        if champion.degradation_count >= max_bad_cycles:
            champion.active = False
        return champion

    def report(self, champion: ChampionState | None, current_delta: float | None,
               max_bad_cycles: int = 3) -> dict:
        if champion is None:
            return {"champion": None, "active": False, "retired": False,
                    "message": "No hay campeón vigente: nada que reevaluar."}
        if current_delta is not None:
            self.evaluate(champion, current_delta, max_bad_cycles=max_bad_cycles)
        return {
            "champion": champion.model,
            "active": champion.active,
            "retired": not champion.active,
            "degradation_count": champion.degradation_count,
            "max_bad_cycles": max_bad_cycles,
            "recent_deltas": champion.history[-max_bad_cycles:],
            "message": ("Campeón retirado por degradación sostenida."
                        if not champion.active else
                        f"Campeón vigente; {champion.degradation_count} ciclo(s) "
                        f"consecutivos por debajo del umbral."),
        }


# --------------------------------------------------------------------------- #
# Early stopping
# --------------------------------------------------------------------------- #
def should_stop(metrics: dict) -> dict:
    """Stop a line of research that is clearly going nowhere.

    Rule 26: this never touches the Golden Holdout — it only decides whether to
    keep spending budget on a family that has repeatedly produced nothing.
    """
    reasons = []
    experiments = metrics.get("experiments", 0)
    if metrics.get("base_rate_warning", False):
        reasons.append("el modelo predice la tasa base")
    # A MISSING measurement is not evidence of failure. The reference version
    # defaults q to 1.0 and permutation_p to 1.0, so a model with q=0.01 and no
    # permutation test recorded would be stopped for "p>0.8" that was never run.
    q = metrics.get("q_value")
    if q is not None and float(q) > 0.5 and experiments >= 3:
        reasons.append("q>0.5 tras 3 o más experimentos")
    perm = metrics.get("permutation_p")
    if perm is not None and float(perm) > 0.8 and experiments >= 5:
        reasons.append("permutación p>0.8 tras 5 o más experimentos")
    return {
        "stop": bool(reasons),
        "reasons": reasons,
        "touches_golden_holdout": False,
        "message": ("Se detiene esta línea: " + "; ".join(reasons) + "."
                    if reasons else "Sigue habiendo margen para investigar."),
    }


# --------------------------------------------------------------------------- #
# Experiment budget
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Budget:
    statistical: int = 20
    classical_ml: int = 30
    deep_learning: int = 20
    qnn: int = 10
    portfolio: int = 20


class ExperimentBudget:
    """Finite and auditable (rule 25).

    A budget nobody counts against is not a budget, so `spend` keeps the tally
    and `report` shows what is left per family.
    """

    def __init__(self, budget: Budget | None = None, used: dict | None = None):
        self.budget = budget or Budget()
        self.used: dict[str, int] = dict(used or {})

    def allocation(self) -> dict:
        return dict(self.budget.__dict__)

    def spend(self, family: str, n: int = 1) -> bool:
        allowed = self.allocation().get(family)
        if allowed is None:
            return False
        if self.used.get(family, 0) + n > allowed:
            return False
        self.used[family] = self.used.get(family, 0) + n
        return True

    def validate(self, used: dict | None = None) -> bool:
        used = self.used if used is None else used
        return all(used.get(k, 0) <= v for k, v in self.allocation().items())

    def report(self, priorities: dict | None = None) -> dict:
        alloc = self.allocation()
        remaining = {k: v - self.used.get(k, 0) for k, v in alloc.items()}
        return {
            "allocation": alloc,
            "used": dict(self.used),
            "remaining": remaining,
            "exhausted": [k for k, v in remaining.items() if v <= 0],
            "within_budget": self.validate(),
            "priorities": priorities or {},
            "note": ("El presupuesto ordena en qué gastar esfuerzo; no cambia "
                     "el listón que un modelo debe superar."),
        }


# --------------------------------------------------------------------------- #
# Continuous learning cycle
# --------------------------------------------------------------------------- #
@dataclass
class CyclePlan:
    status: str
    actions: list
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


class ContinuousLearningCycle:
    BASE_ACTIONS = [
        "AUDIT_LIVE_RESULT", "UPDATE_TRACK_RECORD", "CHECK_DRIFT",
        "QUERY_RESEARCH_MEMORY", "ALLOCATE_EXPERIMENT_BUDGET",
        "RUN_STATISTICAL_LAB", "RUN_MODEL_ZOO", "RUN_ABLATIONS",
        "RUN_STABILITY", "RUN_PERMUTATION", "RUN_BLOCK_BOOTSTRAP",
        "APPLY_BH", "RUN_GOLDEN_HOLDOUT", "RUN_REPLICATION",
        "UPDATE_META_LEARNER", "EVALUATE_CHAMPION_DECAY",
        "BUILD_CANDIDATE_PORTFOLIO", "MONTE_CARLO_AUDIT", "REPORT",
    ]

    def __init__(self, budget: ExperimentBudget | None = None):
        self.budget = budget or ExperimentBudget()
        self.drift = DriftTrigger()

    def plan(self, new_draw: bool, drift_score: float = 0.0,
             active_champion: str | None = None) -> CyclePlan:
        if not new_draw:
            return CyclePlan("WAIT", [],
                             "No hay sorteo nuevo: sin evidencia nueva, repetir el "
                             "análisis solo multiplicaría pruebas.")
        actions = list(self.BASE_ACTIONS)
        decision = self.drift.evaluate(drift_score)
        if decision.detected:
            # drift widens the search; it does NOT promote anything (rule 27)
            actions[3:3] = ["EXPAND_RESEARCH", "RUN_CHANGE_POINT"]
        if active_champion:
            actions.insert(actions.index("EVALUATE_CHAMPION_DECAY"), "RECHECK_CHAMPION")
        return CyclePlan("RUN", actions,
                         f"Nuevo sorteo detectado. {decision.reason}")
