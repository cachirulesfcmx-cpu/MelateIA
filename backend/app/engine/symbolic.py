"""Symbolic / rule-based engine.

Evaluates how well a candidate combination respects mathematical heuristics that
historically describe winning combinations, and penalises obviously "human" or
degenerate combinations (1-2-3-4-5-6, all-low, etc.).

Every strategy supplies an ``ideal`` profile; ``score_combination`` returns a
0..1 score plus a human-readable explanation of the dominant factors.
"""
from __future__ import annotations

from .features import GameStats, combination_features


def _bell(value: float, target: float, tolerance: float) -> float:
    """1.0 at target, decaying smoothly with distance (gaussian-ish)."""
    if tolerance <= 0:
        return 1.0 if value == target else 0.0
    z = (value - target) / tolerance
    return max(0.0, 1.0 - min(1.0, abs(z)) ** 2 * 0.85)


def hard_valid(numbers: list[int], stats: GameStats) -> bool:
    if len(numbers) != stats.pick:
        return False
    if len(set(numbers)) != len(numbers):
        return False
    if any(n < 1 or n > stats.max_number for n in numbers):
        return False
    # reject the canonical obvious sequence
    sd = sorted(numbers)
    if all(sd[i + 1] - sd[i] == 1 for i in range(len(sd) - 1)):
        return False
    return True


def score_combination(numbers: list[int], stats: GameStats, profile: dict) -> tuple[float, dict]:
    """Score a combination 0..1 against a strategy ``profile`` of ideal targets."""
    f = combination_features(numbers, stats)
    mx = stats.max_number
    pick = stats.pick

    components: dict[str, float] = {}

    # Sum distribution — expected mean sum ~ pick * (mx+1)/2
    ideal_sum = profile.get("ideal_sum", pick * (mx + 1) / 2)
    components["sum"] = _bell(f["sum"], ideal_sum, profile.get("sum_tol", mx * 0.9))

    # Odd/even balance
    components["parity"] = _bell(f["odd"], profile.get("ideal_odd", pick / 2), profile.get("odd_tol", 1.6))

    # Range coverage (avoid clustered or maximal spreads)
    components["range"] = _bell(f["range"], profile.get("ideal_range", mx * 0.72), profile.get("range_tol", mx * 0.35))

    # Tercile spread — reward using all three regions
    spread = 1.0 - (abs(f["low"] - pick / 3) + abs(f["mid"] - pick / 3) + abs(f["high"] - pick / 3)) / (pick * 1.4)
    components["spread"] = max(0.0, spread)

    # Primes
    components["primes"] = _bell(f["primes"], profile.get("ideal_primes", 2), 1.6)

    # Consecutive penalty (some runs ok, many bad)
    components["consecutive"] = max(0.0, 1.0 - f["consecutive"] / 3.0)

    # Statistical signal: hot vs cold according to strategy
    weights = stats.number_weights(recency_bias=profile.get("recency_bias", 0.5))
    wsum = sum(weights[n] for n in numbers)
    wmax = sum(sorted(weights.values(), reverse=True)[:pick])
    hot_signal = wsum / wmax if wmax else 0.0
    # overdue signal
    gap_norm = f["avg_gap"] / max(1, max(stats.gaps.values()))
    if profile.get("prefer", "hot") == "cold":
        components["signal"] = 0.5 * (1 - hot_signal) + 0.5 * gap_norm
    elif profile.get("prefer") == "balanced":
        components["signal"] = 0.5 * hot_signal + 0.5 * (1 - abs(gap_norm - 0.5) * 2)
    else:  # hot
        components["signal"] = 0.7 * hot_signal + 0.3 * (1 - gap_norm)

    # Anti-popular: reward contrarian combos
    pop = f["popularity"]
    components["contrarian"] = 1.0 - pop if profile.get("anti_popular") else (1.0 - pop * 0.4)

    # Repeats from last draw (1 is typical, many is unusual)
    components["repeats"] = _bell(f["repeats_last"], profile.get("ideal_repeats", 1), 1.4)

    # Weighted aggregate
    weights_w = profile.get("component_weights", {})
    default_w = {
        "sum": 1.0, "parity": 1.0, "range": 1.0, "spread": 1.2, "primes": 0.6,
        "consecutive": 0.8, "signal": 1.6, "contrarian": 1.0, "repeats": 0.6,
    }
    total_w = 0.0
    acc = 0.0
    for k, v in components.items():
        w = weights_w.get(k, default_w.get(k, 1.0))
        acc += v * w
        total_w += w
    score = acc / total_w if total_w else 0.0
    return round(score, 4), components


def explain(numbers: list[int], stats: GameStats, components: dict, strategy_label: str) -> str:
    f = combination_features(numbers, stats)
    top = sorted(components.items(), key=lambda kv: kv[1], reverse=True)[:3]
    names = {
        "sum": "suma equilibrada", "parity": "balance par/impar", "range": "rango amplio",
        "spread": "buena distribución por tercios", "primes": "primos óptimos",
        "consecutive": "pocos consecutivos", "signal": "señal estadística fuerte",
        "contrarian": "patrón poco popular", "repeats": "repeticiones razonables",
    }
    highlights = ", ".join(names.get(k, k) for k, _ in top)
    return (
        f"Estrategia {strategy_label}: suma {f['sum']}, "
        f"{f['odd']} impares / {f['even']} pares, {f['primes']} primos, "
        f"rango {f['range']}, {f['consecutive']} consecutivos. "
        f"Factores dominantes: {highlights}."
    )
