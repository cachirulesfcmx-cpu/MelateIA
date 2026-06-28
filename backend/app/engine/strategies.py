"""Reasoning tree: strategy profiles.

Each strategy defines an ``ideal`` profile (targets for the symbolic scorer) and
a biasing function that shapes the per-number sampling weights used by the
heuristic/genetic generator. Different strategies therefore produce genuinely
different combinations and carry their own rationale.
"""
from __future__ import annotations

from .features import GameStats

STRATEGIES = {
    "conservadora": {
        "label": "Conservadora",
        "desc": "Prioriza números de alta frecuencia histórica y combinaciones estadísticamente típicas.",
        "prefer": "hot",
        "recency_bias": 0.35,
        "anti_popular": False,
        "ideal_odd": 3, "ideal_primes": 2,
        "component_weights": {"signal": 1.8, "sum": 1.3, "parity": 1.2, "contrarian": 0.4},
        "temperature": 0.6,
    },
    "balanceada": {
        "label": "Balanceada",
        "desc": "Equilibrio entre números calientes, fríos y reglas de distribución.",
        "prefer": "balanced",
        "recency_bias": 0.5,
        "anti_popular": False,
        "ideal_odd": 3, "ideal_primes": 2,
        "component_weights": {"signal": 1.4, "spread": 1.5, "parity": 1.2},
        "temperature": 1.0,
    },
    "agresiva": {
        "label": "Agresiva",
        "desc": "Busca patrones poco probables y mayor varianza para premios grandes.",
        "prefer": "cold",
        "recency_bias": 0.7,
        "anti_popular": True,
        "ideal_odd": 3, "ideal_primes": 3,
        "component_weights": {"contrarian": 1.6, "signal": 1.2, "range": 1.4},
        "temperature": 1.6,
    },
    "genetica": {
        "label": "Genética",
        "desc": "Optimización evolutiva: cruza y muta las mejores combinaciones candidatas.",
        "prefer": "balanced",
        "recency_bias": 0.5,
        "anti_popular": True,
        "ideal_odd": 3, "ideal_primes": 2,
        "component_weights": {"spread": 1.6, "signal": 1.4, "contrarian": 1.2},
        "temperature": 1.2,
        "genetic": True,
    },
    "anti_popular": {
        "label": "Anti-popular",
        "desc": "Evita combinaciones que mucha gente juega (cumpleaños, secuencias) para no compartir premio.",
        "prefer": "balanced",
        "recency_bias": 0.5,
        "anti_popular": True,
        "ideal_odd": 3, "ideal_primes": 2,
        "ideal_sum_shift": 1.15,  # push sum higher (less calendar bias)
        "component_weights": {"contrarian": 2.2, "spread": 1.3},
        "temperature": 1.3,
    },
    "calientes": {
        "label": "Números calientes",
        "desc": "Enfatiza los números más frecuentes en las últimas 50 extracciones.",
        "prefer": "hot",
        "recency_bias": 0.85,
        "anti_popular": False,
        "ideal_odd": 3, "ideal_primes": 2,
        "component_weights": {"signal": 2.0},
        "temperature": 0.5,
    },
    "frios": {
        "label": "Números fríos",
        "desc": "Apuesta por números atrasados que llevan muchos sorteos sin aparecer.",
        "prefer": "cold",
        "recency_bias": 0.6,
        "anti_popular": False,
        "ideal_odd": 3, "ideal_primes": 2,
        "component_weights": {"signal": 2.0},
        "temperature": 0.7,
    },
    "hibrida": {
        "label": "Híbrida avanzada",
        "desc": "Ensemble: combina señal estadística, reglas simbólicas y optimización genética.",
        "prefer": "balanced",
        "recency_bias": 0.55,
        "anti_popular": True,
        "ideal_odd": 3, "ideal_primes": 2,
        "component_weights": {"signal": 1.5, "spread": 1.5, "contrarian": 1.3, "parity": 1.1},
        "temperature": 1.1,
        "genetic": True,
        "use_ml": True,
    },
    "adaptativa": {
        "label": "Adaptativa (IA)",
        "desc": "Aprendizaje por refuerzo: enruta automáticamente a la estrategia que mejor ha rendido en este juego.",
        "prefer": "balanced",
        "recency_bias": 0.55,
        "anti_popular": True,
        "ideal_odd": 3, "ideal_primes": 2,
        "component_weights": {"signal": 1.5, "spread": 1.4, "synergy": 1.2, "contrarian": 1.1},
        "temperature": 1.0,
        "genetic": True,
        "use_ml": True,
        "adaptive": True,
    },
    "evolutiva": {
        "label": "Evolutiva (Genius)",
        "desc": "Motor Genius completo: fusiona 13 modelos (Bayes, Markov, Fourier, atraso, co-ocurrencia, delta, gaussiana…) con pesos que evolucionan según su acierto, una capa meta que aprende de los sorteos evaluados, y genera los boletos muestreando de esa distribución.",
        "prefer": "balanced",
        "recency_bias": 0.5,
        "anti_popular": True,
        "ideal_odd": 3, "ideal_primes": 2,
        "component_weights": {"signal": 1.6, "spread": 1.4, "synergy": 1.2, "contrarian": 1.0},
        "temperature": 1.0,
        "genetic": True,
        "use_ml": True,
    },
}

STRATEGY_KEYS = list(STRATEGIES.keys())


def build_profile(strategy: str, stats: GameStats) -> dict:
    base = STRATEGIES.get(strategy, STRATEGIES["balanceada"]).copy()
    mx = stats.max_number
    pick = stats.pick
    profile = dict(base)
    profile["ideal_sum"] = pick * (mx + 1) / 2 * base.get("ideal_sum_shift", 1.0)
    profile["sum_tol"] = mx * 0.85
    profile["ideal_range"] = mx * 0.72
    profile["range_tol"] = mx * 0.35
    profile["odd_tol"] = 1.6
    return profile


def biased_weights(strategy: str, stats: GameStats) -> dict[int, float]:
    """Per-number sampling weights shaped by the strategy."""
    prof = STRATEGIES.get(strategy, STRATEGIES["balanceada"])
    w = stats.number_weights(recency_bias=prof.get("recency_bias", 0.5))
    prefer = prof.get("prefer", "balanced")
    max_gap = max(1, max(stats.gaps.values()))

    out = {}
    for n in range(1, stats.max_number + 1):
        val = w[n]
        gap_factor = stats.gaps[n] / max_gap
        if prefer == "cold":
            val = val * 0.4 + gap_factor * 0.9
        elif prefer == "hot":
            val = val * 1.4
        else:  # balanced
            val = val * 0.8 + gap_factor * 0.3
        if prof.get("anti_popular") and n <= 31:
            val *= 0.8  # de-emphasise calendar numbers
        out[n] = max(val, 1e-4)
    return out
