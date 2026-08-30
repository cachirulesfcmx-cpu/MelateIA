"""v7 — Candidate Portfolio, Evolutionary Search, Monte Carlo, Dynamic Ensemble.

Constitution rule 16 governs this whole module: **a portfolio is not more likely
to win because it was optimized**. Diversifying tickets changes how the same
fixed probability is spread across outcomes — it buys coverage, not luck. Every
function here reports that plainly instead of dressing optimization up as an
edge.

Three defects in the reference package are fixed here:

  * `monte_carlo.simulate` counted `len(set(sample))`, which is always `pick`,
    so it reported 6.0 hits and a degenerate distribution. It never simulated
    hits against a winning draw at all.
  * `no_edge.evaluate_edge` named `q[0]` champion — the first model in input
    order rather than the strongest.
  * `DynamicEnsemble.confidence` compared the sum of normalized weights against
    0.8; that sum is 1.0 whenever any model qualifies, so it always answered
    HIGH. Confidence now derives from the evidence itself.
"""
from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass

from .game_config import GameConfig
from .research_lab import hypergeometric_pmf, theoretical_random_mean_hits


# --------------------------------------------------------------------------- #
# Candidate portfolio
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Candidate:
    numbers: tuple
    score: float
    source: str

    def as_dict(self) -> dict:
        return {"numbers": list(self.numbers), "score": round(self.score, 4),
                "source": self.source}


class PortfolioEngine:
    """Builds a diversified set of candidate tickets."""

    def __init__(self, cfg: GameConfig):
        self.cfg = cfg

    def validate(self, combo) -> bool:
        c = tuple(sorted({int(x) for x in combo}))
        return (len(c) == self.cfg.pick
                and all(self.cfg.min_number <= x <= self.cfg.max_number for x in c))

    def diversify(self, candidates: list[Candidate], size: int = 10,
                  overlap_limit: int = 3) -> list[Candidate]:
        """Greedy selection: best first, skipping anything that overlaps too much."""
        out: list[Candidate] = []
        for c in sorted(candidates, key=lambda x: x.score, reverse=True):
            if not self.validate(c.numbers):
                continue
            if all(len(set(c.numbers) & set(s.numbers)) <= overlap_limit for s in out):
                out.append(c)
            if len(out) >= size:
                break
        return out

    def coverage(self, portfolio: list[Candidate]) -> dict:
        """What the portfolio actually buys: distinct numbers and shared prize risk.

        This is the honest way to describe a portfolio — coverage of the number
        space and how correlated the tickets are — never "higher probability".
        """
        pick = self.cfg.pick
        span = self.cfg.max_number - self.cfg.min_number + 1
        numbers = Counter(n for c in portfolio for n in c.numbers)
        distinct = len(numbers)
        overlaps = []
        for i, a in enumerate(portfolio):
            for b in portfolio[i + 1:]:
                overlaps.append(len(set(a.numbers) & set(b.numbers)))
        n_tickets = len(portfolio)
        # probability that at least one ticket hits all `pick` numbers, if the
        # tickets are distinct: n / C(span, pick). Still astronomically small.
        total_combinations = math.comb(span, pick)
        return {
            "tickets": n_tickets,
            "distinct_numbers": distinct,
            "coverage_share": round(distinct / span, 4),
            "mean_overlap": round(sum(overlaps) / len(overlaps), 3) if overlaps else 0.0,
            "max_overlap": max(overlaps) if overlaps else 0,
            "jackpot_odds_one_in": (round(total_combinations / n_tickets)
                                    if n_tickets else total_combinations),
            "expected_hits_per_ticket": round(
                theoretical_random_mean_hits(self.cfg.max_number, pick), 4),
            "note": ("Diversificar reparte la MISMA probabilidad entre más resultados: "
                     "compra cobertura, no suerte. Jugar 10 boletos distintos multiplica "
                     "por 10 la probabilidad de premio mayor respecto a jugar 1, igual "
                     "que comprar 10 billetes — no porque estén optimizados."),
        }


# --------------------------------------------------------------------------- #
# Evolutionary search over combinations
# --------------------------------------------------------------------------- #
class EvolutionarySearch:
    """Mutation + crossover over tickets, guided by a fitness function.

    Never sees the Golden Holdout (constitution rule 17): the fitness passed in
    is built from the selection data only.
    """

    def __init__(self, cfg: GameConfig, seed: int = 42):
        self.cfg = cfg
        self.rng = random.Random(seed)

    def random_combo(self) -> tuple:
        return tuple(sorted(self.rng.sample(
            range(self.cfg.min_number, self.cfg.max_number + 1), self.cfg.pick)))

    def mutate(self, combo) -> tuple:
        c = set(combo)
        pool = [n for n in range(self.cfg.min_number, self.cfg.max_number + 1)
                if n not in c]
        if not pool:
            return tuple(sorted(c))
        c.discard(self.rng.choice(sorted(c)))
        c.add(self.rng.choice(pool))
        return tuple(sorted(c))

    def crossover(self, a, b) -> tuple:
        pool = list(dict.fromkeys(tuple(a) + tuple(b)))
        if len(pool) < self.cfg.pick:
            return tuple(sorted(a))
        return tuple(sorted(self.rng.sample(pool, self.cfg.pick)))

    def evolve(self, population: list, fitness, generations: int = 20,
               elite: int = 10) -> list[tuple]:
        pop = [tuple(sorted(p)) for p in population]
        if not pop:
            return []
        cache: dict[tuple, float] = {}

        def fit(c):                       # fitness can be expensive; memoize it
            if c not in cache:
                cache[c] = fitness(c)
            return cache[c]

        elite = max(1, min(elite, len(pop) - 1)) if len(pop) > 1 else 1
        for _ in range(generations):
            ranked = sorted(pop, key=fit, reverse=True)
            keep = ranked[:elite]
            children = []
            guard = 0
            while len(children) + len(keep) < len(pop) and guard < len(pop) * 10:
                guard += 1
                a, b = (self.rng.sample(keep, 2) if len(keep) > 1 else (keep[0], keep[0]))
                child = self.crossover(a, b)
                if self.rng.random() < 0.7:
                    child = self.mutate(child)
                children.append(child)
            pop = keep + children
        return sorted(set(pop), key=fit, reverse=True)


# --------------------------------------------------------------------------- #
# Monte Carlo
# --------------------------------------------------------------------------- #
def monte_carlo_hits(cfg: GameConfig, universes: int = 20000, seed: int = 42,
                     tickets: list | None = None) -> dict:
    """Distribution of hits for random tickets against a random winning draw.

    The reference implementation counted the size of the sampled set, which is
    `pick` by definition — it always reported 6.0 hits and never simulated
    anything. This one draws a winner and a ticket and counts the overlap, and
    the result is checked against the exact hypergeometric distribution.
    """
    rng = random.Random(seed)
    pool = list(range(cfg.min_number, cfg.max_number + 1))
    pick = cfg.pick
    counts: Counter = Counter()
    for _ in range(universes):
        winner = set(rng.sample(pool, pick))
        ticket = set(tickets[rng.randrange(len(tickets))]) if tickets else set(rng.sample(pool, pick))
        counts[len(winner & ticket)] += 1
    mean = sum(k * v for k, v in counts.items()) / universes
    exact = hypergeometric_pmf(cfg.max_number - cfg.min_number + 1, pick)
    return {
        "universes": universes,
        "seed": seed,
        "mean_hits": round(mean, 4),
        "distribution": {str(k): counts.get(k, 0) for k in range(pick + 1)},
        "share": {str(k): round(counts.get(k, 0) / universes, 5) for k in range(pick + 1)},
        "exact_reference": {str(k): round(v, 5) for k, v in exact.items()},
        "exact_mean_hits": round(theoretical_random_mean_hits(
            cfg.max_number - cfg.min_number + 1, pick), 4),
        "note": ("Monte Carlo estima distribuciones, no causalidad. Se contrasta "
                 "contra la hipergeométrica exacta para que el ruido de simulación "
                 "no se confunda con un hallazgo."),
    }


# --------------------------------------------------------------------------- #
# Dynamic ensemble
# --------------------------------------------------------------------------- #
@dataclass
class ModelEvidence:
    name: str
    score: float
    stability: float
    q_value: float
    permutation_p: float = 1.0
    golden_holdout_delta: float = 0.0
    replicated: bool = False
    base_rate_warning: bool = False

    def as_dict(self) -> dict:
        return {"model": self.name, "score": self.score, "stability": self.stability,
                "q_value": self.q_value, "permutation_p": self.permutation_p,
                "golden_holdout_delta": self.golden_holdout_delta,
                "replicated": self.replicated,
                "base_rate_warning": self.base_rate_warning}


class DynamicEnsemble:
    """Weights only the models that cleared the gates (constitution rule 19)."""

    def qualified(self, evidence: list[ModelEvidence]) -> list[ModelEvidence]:
        return [e for e in evidence
                if e.q_value < 0.05 and not e.base_rate_warning and e.stability > 0.5]

    def weights(self, evidence: list[ModelEvidence]) -> dict[str, float]:
        valid = self.qualified(evidence)
        if not valid:
            return {e.name: 0.0 for e in evidence}
        raw = {e.name: max(0.0, e.score) * max(0.0, e.stability) for e in valid}
        total = sum(raw.values()) or 1.0
        return {e.name: round(raw.get(e.name, 0.0) / total, 6) for e in evidence}

    def confidence(self, evidence: list[ModelEvidence]) -> dict:
        """Confidence from the EVIDENCE, not from normalized weights.

        The reference version summed the weights and compared to 0.8 — but those
        weights are normalized to 1 whenever anything qualifies, so it answered
        HIGH every time a single model squeaked through.
        """
        valid = self.qualified(evidence)
        if not valid:
            return {"level": "NONE", "qualified": 0, "total": len(evidence),
                    "reason": "Ningún modelo pasó las compuertas: todos los pesos son cero."}
        replicated = [e for e in valid if e.replicated]
        strong = [e for e in valid
                  if e.permutation_p < 0.05 and e.golden_holdout_delta > 0]
        if len(replicated) >= 2 and strong:
            level = "HIGH"
        elif replicated and strong:
            level = "MEDIUM"
        else:
            level = "LOW"
        return {
            "level": level,
            "qualified": len(valid),
            "replicated": len(replicated),
            "passed_permutation_and_holdout": len(strong),
            "total": len(evidence),
            "reason": (f"{len(valid)} modelo(s) con q<0.05 y estabilidad; "
                       f"{len(replicated)} replicado(s); {len(strong)} superaron "
                       f"permutación y holdout."),
        }


# --------------------------------------------------------------------------- #
# No-Edge mode (constitution rule 20)
# --------------------------------------------------------------------------- #
def evaluate_edge(evidence: list[dict], min_models: int = 1) -> dict:
    """Is there a reproducible predictive edge? Usually the answer is no.

    Every condition must hold: corrected significance, permutation, a positive
    Golden Holdout delta, independent replication, and no base-rate warning.
    The champion is the STRONGEST qualifying model — the reference version
    returned whichever happened to be first in the list.
    """
    def passes(e: dict) -> bool:
        return (e.get("q_value", 1.0) < 0.05
                and e.get("permutation_p", 1.0) < 0.05
                and e.get("golden_holdout_delta", 0.0) > 0
                and bool(e.get("replicated", False))
                and not e.get("base_rate_warning", False))

    qualified = [e for e in evidence if passes(e)]
    if len(qualified) < max(1, min_models):
        failed = {}
        for e in evidence:
            for key, ok in (("q_value", e.get("q_value", 1.0) < 0.05),
                            ("permutation_p", e.get("permutation_p", 1.0) < 0.05),
                            ("golden_holdout_delta", e.get("golden_holdout_delta", 0.0) > 0),
                            ("replicated", bool(e.get("replicated", False))),
                            ("base_rate_warning", not e.get("base_rate_warning", False))):
                if not ok:
                    failed[key] = failed.get(key, 0) + 1
        return {
            "mode": "NO_EDGE",
            "champion": None,
            "confidence": "LOW",
            "qualified_models": 0,
            "evaluated_models": len(evidence),
            "failed_by_gate": failed,
            "message": ("No se detectó ventaja predictiva reproducible. "
                        "Es el resultado esperado en un sorteo justo, y el sistema "
                        "lo declara en vez de inventar un campeón."),
        }
    best = max(qualified, key=lambda e: (e.get("golden_holdout_delta", 0.0),
                                         -e.get("q_value", 1.0),
                                         e.get("score", 0.0)))
    return {
        "mode": "EDGE_CANDIDATE",
        "champion": best.get("model"),
        "confidence": "RESEARCH_ONLY",
        "qualified_models": len(qualified),
        "evaluated_models": len(evidence),
        "message": ("Hay un candidato que superó todas las compuertas. Sigue siendo "
                    "un hallazgo de investigación, no una promesa de ganancia."),
    }
