"""v9 — Live Intelligence: sequential analysis, rolling windows, lineage.

The live record is the only measurement in this whole system taken on data that
never influenced anything. That makes it valuable and, for the same reason,
easy to abuse: looking at it after every draw and declaring victory the first
time a confidence interval clears zero is the classic sequential-testing trap.

Two corrections to the reference package:

  * It computes a fixed 95% interval at every look. Peeking repeatedly at a
    growing sample inflates the false-positive rate far above 5% — which is
    precisely what "sequential analysis" exists to prevent. Here the interval
    widens with the number of looks (a Bonferroni-style alpha split), and the
    number of looks is reported alongside the verdict.
  * `rank_models` sorted by ``-live_ci_low`` under ``reverse=True``, which ranks
    a LOWER confidence bound as better — backwards. Stronger lower bounds now
    rank higher.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field

WINDOW_SIZES = (20, 40, 60)


def _z_for(alpha: float) -> float:
    """Two-sided critical value; small table avoids a scipy dependency."""
    table = [(0.20, 1.282), (0.10, 1.645), (0.05, 1.960), (0.025, 2.241),
             (0.0125, 2.498), (0.00625, 2.734), (0.003125, 2.955),
             (0.0015625, 3.163), (0.00078125, 3.361)]
    for a, z in table:
        if alpha >= a:
            return z
    return 3.5


# --------------------------------------------------------------------------- #
# Sequential analysis
# --------------------------------------------------------------------------- #
@dataclass
class SequentialResult:
    n: int
    mean_hits: float
    baseline: float
    delta: float
    se_delta: float
    z_score: float
    ci_low: float
    ci_high: float
    looks: int
    alpha_per_look: float
    z_used: float
    status: str
    reading: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def analyze(hit_counts, baseline: float, alpha: float = 0.05,
            looks: int = 1) -> SequentialResult:
    """Is the live mean above the baseline, accounting for repeated looks?

    `looks` is how many times this record has been examined. With one look the
    interval is the usual 95%; with ten it is the interval that keeps the
    OVERALL false-positive rate at 5%, which is the honest comparison when a
    system checks itself after every single draw.
    """
    vals = [float(x) for x in hit_counts]
    n = len(vals)
    looks = max(1, int(looks))
    alpha_per_look = alpha / looks
    z = _z_for(alpha_per_look)

    if n < 2:
        return SequentialResult(n, (vals[0] if vals else 0.0), baseline, 0.0,
                                float("inf"), 0.0, float("-inf"), float("inf"),
                                looks, alpha_per_look, z, "INSUFFICIENT_DATA",
                                "Se requieren al menos 2 observaciones.")
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / (n - 1)
    se = math.sqrt(var / n) if var > 0 else 0.0
    delta = mean - baseline
    if se == 0.0:
        lo = hi = delta
        score = 0.0
    else:
        lo, hi = delta - z * se, delta + z * se
        score = delta / se
    status = "SIGNAL_CANDIDATE" if lo > 0 else "COMPATIBLE_WITH_BASELINE"
    reading = (
        f"{n} predicciones: {mean:.4f} frente a {baseline:.4f} del azar "
        f"({delta:+.4f}). IC ajustado por {looks} mirada(s): "
        f"[{lo:+.4f}, {hi:+.4f}]. "
        + ("El intervalo excluye al azar: candidato a señal, todavía sujeto al "
           "protocolo completo." if status == "SIGNAL_CANDIDATE" else
           "El intervalo cruza al azar, así que no demuestra ventaja."))
    return SequentialResult(n, round(mean, 5), round(baseline, 5), round(delta, 5),
                            round(se, 6), round(score, 4), round(lo, 5), round(hi, 5),
                            looks, round(alpha_per_look, 6), z, status, reading)


def rolling_windows(hit_counts, sizes=WINDOW_SIZES) -> dict:
    vals = list(hit_counts)
    return {s: vals[-s:] for s in sizes if len(vals) >= s}


def summarize_live(model: str, hit_counts, baseline: float,
                   looks: int = 1, alpha: float = 0.05) -> dict:
    """Full live picture: overall plus each rolling window."""
    full = analyze(hit_counts, baseline, alpha=alpha, looks=looks)
    windows = {}
    for size, vals in rolling_windows(hit_counts).items():
        r = analyze(vals, baseline, alpha=alpha, looks=looks)
        windows[str(size)] = {"delta": r.delta, "ci_low": r.ci_low,
                              "ci_high": r.ci_high, "status": r.status}
    return {
        "model": model,
        **full.as_dict(),
        "windows": windows,
        "note": ("Las ventanas móviles describen tramos recientes; no sustituyen "
                 "a las pruebas corregidas del ciclo de investigación."),
    }


# --------------------------------------------------------------------------- #
# Regression guard
# --------------------------------------------------------------------------- #
def detect_regression(current_delta: float, previous_delta: float,
                      tolerance: float = 0.05) -> dict:
    change = float(current_delta) - float(previous_delta)
    regressed = change < -abs(tolerance)
    return {
        "change": round(change, 5),
        "regressed": regressed,
        "tolerance": tolerance,
        "status": "REGRESSION" if regressed else "STABLE_OR_IMPROVED",
        "note": ("Una regresión puede retirar a un Champion, pero nunca promueve "
                 "a otro automáticamente."),
    }


# --------------------------------------------------------------------------- #
# Adaptive budget with caps
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BudgetCaps:
    statistical: int = 30
    classical_ml: int = 40
    deep_learning: int = 40
    qnn: int = 40
    portfolio: int = 40


class AdaptiveBudget:
    """Reallocates effort by priority, but never past a hard cap (rule 36)."""

    def __init__(self, caps: BudgetCaps | None = None):
        self.caps = caps or BudgetCaps()

    def allocate(self, priorities: dict) -> dict:
        caps = dict(self.caps.__dict__)
        total = sum(max(0.0, float(v)) for v in priorities.values())
        if total <= 0:
            return {k: 1 for k in caps}
        return {k: min(cap, max(1, round(cap * max(0.0, float(priorities.get(k, 0))) / total)))
                for k, cap in caps.items()}

    def validate(self, allocation: dict) -> bool:
        return all(allocation.get(k, 0) <= cap for k, cap in self.caps.__dict__.items())

    def report(self, priorities: dict) -> dict:
        alloc = self.allocate(priorities)
        return {"caps": dict(self.caps.__dict__), "allocation": alloc,
                "within_caps": self.validate(alloc),
                "note": "El presupuesto adaptativo tiene límites duros por familia."}


# --------------------------------------------------------------------------- #
# Data lineage
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DataLineage:
    model_version: str
    train_snapshot: str
    validation_snapshot: str
    holdout_snapshot: str
    live_start_snapshot: str
    live_end_snapshot: str | None = None
    live_predictions_count: int = 0
    training_includes_live: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> bool:
        """Rule 39: folding live data into training opens a NEW temporal frontier.

        Without closing the old live window, yesterday's live predictions would
        silently become part of training and the next 'live' measurement would
        be contaminated by data the model already saw.
        """
        if self.training_includes_live and not self.live_end_snapshot:
            raise ValueError(
                "Incorporar live al entrenamiento exige cerrar la frontera "
                "temporal: falta live_end_snapshot.")
        return True


def snapshot_id(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Model ranking
# --------------------------------------------------------------------------- #
def rank_models(records: list[dict]) -> list[dict]:
    """Rank by strength of evidence, not by raw delta (rule 38).

    The reference version sorted by ``-live_ci_low`` under ``reverse=True``,
    which puts the WEAKEST lower bound first. Ordering here is: replicated,
    then corrected significance, then the lower bound of the live interval
    (higher is stronger), then the delta.
    """
    def key(r: dict):
        return (
            bool(r.get("replicated", False)),
            float(r.get("q_value", 1.0)) < 0.05,
            float(r.get("live_ci_low", float("-inf"))),
            float(r.get("live_delta", float("-inf"))),
        )
    return sorted(records, key=key, reverse=True)


# --------------------------------------------------------------------------- #
# Next cycle planner
# --------------------------------------------------------------------------- #
@dataclass
class NextCyclePlan:
    status: str
    priority: str
    actions: list = field(default_factory=list)
    rationale: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class LiveIntelligence:
    def __init__(self, caps: BudgetCaps | None = None):
        self.budget = AdaptiveBudget(caps)

    def plan(self, new_draw: bool, live_hits, baseline: float,
             priorities: dict | None = None, looks: int = 1) -> dict:
        if not new_draw:
            return {**NextCyclePlan("WAIT", "NONE", [],
                                    "No hay sorteo nuevo: sin evidencia nueva.").as_dict(),
                    "sequential": None}
        r = analyze(live_hits, baseline, looks=looks)
        if r.status == "SIGNAL_CANDIDATE":
            priority = "CONFIRMATION"
            actions = ["REPLICATE", "RECHECK_PERMUTATION", "RECHECK_GOLDEN_HOLDOUT"]
        else:
            priority = "EXPLORATION"
            actions = ["UPDATE_TRACK_RECORD", "QUERY_MEMORY", "RUN_ADAPTIVE_RESEARCH"]
        actions += ["UPDATE_SEQUENTIAL_METRICS", "CHECK_DRIFT",
                    "CHECK_CHAMPION_DECAY", "BUILD_PORTFOLIO", "REPORT"]
        return {
            **NextCyclePlan("RUN", priority, actions,
                            "La prioridad sale de la evidencia live, no del "
                            "rendimiento bruto.").as_dict(),
            "sequential": r.as_dict(),
            "budget": self.budget.report(priorities or {}),
        }
