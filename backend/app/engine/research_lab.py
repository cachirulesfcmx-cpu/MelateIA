"""Research Lab — protocol v3 (points 3 to 8).

Ported from the "MelatePro Autonomous v3" package and adapted to MelateIA's
engine and games:

  3. Separated baselines (theoretical / empirical / model / challenger),
     never mixed.
  4. Diagnostics that investigate WHY no signal appears.
  5. Temporal permutation testing (destroys time order, keeps composition).
  6. Anti-p-hacking: pre-registered hypotheses + Benjamini-Hochberg correction.
  7. Golden Holdout: the final 10% is locked out of every selection decision.
  8. A fixed production pipeline order.

One deliberate improvement over the source package: the empirical random
baseline is computed from the EXACT hypergeometric distribution instead of a
Monte Carlo simulation. The package's own rationale was "evitar confundir ruido
de Monte Carlo con el valor esperado matemático" — computing the closed form
achieves that completely, is deterministic, and needs no numpy.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import dataclass

try:  # numpy only accelerates diagnostics; everything degrades to pure Python
    import numpy as np
    HAS_NUMPY = True
except Exception:  # pragma: no cover
    np = None  # type: ignore
    HAS_NUMPY = False


# --------------------------------------------------------------------------- #
# 6. Anti-p-hacking — hypotheses registered BEFORE any test is run
# --------------------------------------------------------------------------- #
PRE_REGISTERED: dict[str, str] = {
    "H01": "La frecuencia reciente mejora el promedio de aciertos frente al baseline aleatorio.",
    "H02": "La frecuencia histórica mejora el promedio de aciertos frente al baseline aleatorio.",
    "H03": "Existe autocorrelación temporal persistente en la presencia de números.",
    "H04": "Existen pares de números con coocurrencia persistentemente superior a la esperada por azar.",
    "H05": "La distribución de frecuencias cambia de régimen de forma persistente.",
    "H06": "La complejidad del modelo aporta información incremental sobre los baselines.",
    "H07": "El orden temporal de los sorteos contiene información predictiva.",
}

ALPHA = 0.05
MIN_IMPROVEMENT_V3 = 0.02


# --------------------------------------------------------------------------- #
# 3. Baselines — kept strictly separate
# --------------------------------------------------------------------------- #
def theoretical_random_mean_hits(max_number: int, pick: int = 6) -> float:
    """E[hits] = pick^2 / N when matching `pick` numbers against `pick` winners."""
    return (pick * pick) / max_number


def hypergeometric_pmf(max_number: int, pick: int) -> dict[int, float]:
    """Exact distribution of hits for a uniformly random ticket.

    P(h) = C(pick, h) * C(N - pick, pick - h) / C(N, pick)
    """
    total = math.comb(max_number, pick)
    pmf = {}
    for h in range(0, pick + 1):
        rest = pick - h
        if rest > max_number - pick:
            pmf[h] = 0.0
            continue
        pmf[h] = math.comb(pick, h) * math.comb(max_number - pick, rest) / total
    return pmf


def empirical_random_baseline(n_draws: int, max_number: int, pick: int = 6) -> dict:
    """Exact random baseline (closed form, no Monte Carlo noise).

    `n_draws` is the number of evaluated draws; it only affects the standard
    error of the mean, which is what tells us how much a measured advantage
    could be luck.
    """
    pmf = hypergeometric_pmf(max_number, pick)
    mean = sum(h * p for h, p in pmf.items())
    var = sum((h - mean) ** 2 * p for h, p in pmf.items())
    sd = math.sqrt(var)
    se = sd / math.sqrt(n_draws) if n_draws > 0 else 0.0
    return {
        "n": n_draws,
        "method": "hipergeométrica exacta",
        "mean_hits": round(mean, 6),
        "std_hits": round(sd, 6),
        "std_error_of_mean": round(se, 6),
        "hit_rate_3plus": round(sum(p for h, p in pmf.items() if h >= 3), 6),
        "hit_rate_4plus": round(sum(p for h, p in pmf.items() if h >= 4), 6),
        # 95% interval for the MEAN over n_draws evaluations
        "ci95_low": round(mean - 1.96 * se, 6),
        "ci95_high": round(mean + 1.96 * se, 6),
        "distribution": {str(h): round(p, 8) for h, p in pmf.items()},
    }


# --------------------------------------------------------------------------- #
# 6. Multiple-testing correction
# --------------------------------------------------------------------------- #
def benjamini_hochberg(pvalues: list[float], alpha: float = ALPHA) -> list[dict]:
    """Benjamini-Hochberg FDR correction. Returns one entry per input p-value.

    With 16 arms tested at once, uncorrected p-values would produce a false
    "winner" about half the time. This is the guard against that.
    """
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [1.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        q[i] = max(0.0, min(1.0, running))
    return [{"p": round(pvalues[i], 6), "q": round(q[i], 6),
             "significant": q[i] <= alpha} for i in range(m)]


def permutation_pvalue(observed: float, null_values: list[float],
                       higher_is_better: bool = True) -> float:
    """(#null at least as extreme + 1) / (n + 1) — never reports p = 0."""
    n = len(null_values)
    if n == 0:
        return 1.0
    if higher_is_better:
        extreme = sum(1 for v in null_values if v >= observed)
    else:
        extreme = sum(1 for v in null_values if v <= observed)
    return (extreme + 1) / (n + 1)


# --------------------------------------------------------------------------- #
# 7. Golden Holdout
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Split:
    train: list
    validation: list
    test: list
    golden_holdout: list

    @property
    def selection(self) -> list:
        """Everything a model is allowed to see while being selected."""
        return self.train + self.validation + self.test


def chronological_split(draws: list, train_ratio: float = 0.65,
                        validation_ratio: float = 0.15, test_ratio: float = 0.10,
                        golden_ratio: float = 0.10) -> Split:
    if abs(train_ratio + validation_ratio + test_ratio + golden_ratio - 1.0) > 1e-9:
        raise ValueError("Las proporciones deben sumar 1")
    n = len(draws)
    a = int(n * train_ratio)
    b = a + int(n * validation_ratio)
    c = b + int(n * test_ratio)
    return Split(draws[:a], draws[a:b], draws[b:c], draws[c:])


def hash_draws(draws: list) -> str:
    """Stable SHA-256 identity of a set of draws, so a holdout can be proven
    to be the same one across runs (and proven not to have been moved)."""
    return hashlib.sha256(
        json.dumps(draws, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def golden_holdout_block(split: Split) -> dict:
    return {
        "rows": len(split.golden_holdout),
        "locked": True,
        "sha256": hash_draws(split.golden_holdout),
        "selection_allowed": False,
        "purpose": "solo evaluación final de un candidato ya congelado",
        "split_rows": {
            "train": len(split.train),
            "validation": len(split.validation),
            "test": len(split.test),
            "golden": len(split.golden_holdout),
        },
    }


# --------------------------------------------------------------------------- #
# 4. Diagnostics — why no signal appears
# --------------------------------------------------------------------------- #
def _presence_matrix(draws: list, max_number: int):
    if HAS_NUMPY:
        x = np.zeros((len(draws), max_number), dtype=float)
        for i, d in enumerate(draws):
            for n in d:
                if 1 <= n <= max_number:
                    x[i, int(n) - 1] = 1.0
        return x
    return [[1.0 if (j + 1) in set(d) else 0.0 for j in range(max_number)] for d in draws]


def autocorrelation_presence(draws: list, max_number: int, max_lag: int = 20) -> dict:
    """Mean autocorrelation of each number's presence series, per lag.

    If draws were predictable from their own past, some lag would show a
    consistently non-zero correlation.
    """
    n = len(draws)
    if n < 30:
        return {}
    x = _presence_matrix(draws, max_number)
    out: dict[str, float] = {}
    top_lag = min(max_lag, n - 2)
    for lag in range(1, top_lag + 1):
        vals = []
        if HAS_NUMPY:
            for j in range(max_number):
                a, b = x[:-lag, j], x[lag:, j]
                if a.std() > 0 and b.std() > 0:
                    vals.append(float(np.corrcoef(a, b)[0, 1]))
        else:  # pragma: no cover - numpy is present in production
            for j in range(max_number):
                a = [row[j] for row in x[:-lag]]
                b = [row[j] for row in x[lag:]]
                ma, mb = sum(a) / len(a), sum(b) / len(b)
                va = sum((v - ma) ** 2 for v in a)
                vb = sum((v - mb) ** 2 for v in b)
                if va > 0 and vb > 0:
                    cov = sum((p - ma) * (q - mb) for p, q in zip(a, b))
                    vals.append(cov / math.sqrt(va * vb))
        out[str(lag)] = round(sum(vals) / len(vals), 5) if vals else 0.0
    return out


def rolling_frequency_shift(draws: list, max_number: int, window: int = 100) -> dict:
    """How much the per-number frequency moved between the two last windows."""
    if len(draws) < 2 * window:
        return {"window": window, "mean_abs_shift": None, "max_abs_shift": None}
    prev = _presence_matrix(draws[-2 * window:-window], max_number)
    curr = _presence_matrix(draws[-window:], max_number)
    if HAS_NUMPY:
        a, b = prev.mean(axis=0), curr.mean(axis=0)
        diff = [abs(float(x)) for x in (a - b)]
    else:  # pragma: no cover
        a = [sum(r[j] for r in prev) / len(prev) for j in range(max_number)]
        b = [sum(r[j] for r in curr) / len(curr) for j in range(max_number)]
        diff = [abs(x - y) for x, y in zip(a, b)]
    expected = 2 * math.sqrt((6 / max_number) * (1 - 6 / max_number) / window)
    return {
        "window": window,
        "mean_abs_shift": round(sum(diff) / len(diff), 5),
        "max_abs_shift": round(max(diff), 5),
        # what a shift of pure sampling noise would look like, for comparison
        "expected_noise_shift": round(expected, 5),
    }


def pair_lift(draws: list, max_number: int, top_k: int = 10) -> list[dict]:
    """Pairs whose co-occurrence most exceeds independence."""
    total = len(draws)
    if total == 0:
        return []
    singles = Counter(n for d in draws for n in d if 1 <= n <= max_number)
    pairs = Counter()
    for d in draws:
        s = sorted(n for n in d if 1 <= n <= max_number)
        for i, a in enumerate(s):
            for b in s[i + 1:]:
                pairs[(a, b)] += 1
    rows = []
    for (a, b), c in pairs.items():
        expected = (singles[a] / total) * (singles[b] / total) * total
        if expected <= 0:
            continue
        rows.append({"a": a, "b": b, "count": c, "lift": round(c / expected, 4)})
    rows.sort(key=lambda r: r["lift"], reverse=True)
    return rows[:top_k]


def _normal_sf(z: float) -> float:
    """P(Z > z) for a standard normal."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def top_pair_significance(draws: list, max_number: int, pick: int = 6) -> dict:
    """Is the most over-represented pair beyond what chance produces?

    Under independence a given pair's count is Binomial(n, p_a*p_b). We take the
    strongest pair and Bonferroni-correct by the number of pairs examined —
    otherwise "the luckiest of 1,540 pairs" always looks impressive.
    """
    total = len(draws)
    if total < 30:
        return {"tested_pairs": 0, "significant": False}
    singles = Counter(n for d in draws for n in d if 1 <= n <= max_number)
    pairs = Counter()
    for d in draws:
        s = sorted(n for n in d if 1 <= n <= max_number)
        for i, a in enumerate(s):
            for b in s[i + 1:]:
                pairs[(a, b)] += 1
    n_pairs = max_number * (max_number - 1) // 2
    best = None
    for (a, b), c in pairs.items():
        p = (singles[a] / total) * (singles[b] / total)
        exp = p * total
        if exp <= 0:
            continue
        sd = math.sqrt(total * p * (1 - p))
        z = (c - exp) / sd if sd > 0 else 0.0
        if best is None or z > best["z"]:
            best = {"a": a, "b": b, "count": c, "expected": round(exp, 3),
                    "z": round(z, 3), "lift": round(c / exp, 4)}
    if not best:
        return {"tested_pairs": n_pairs, "significant": False}
    p_raw = _normal_sf(best["z"])
    p_adj = min(1.0, p_raw * n_pairs)   # Bonferroni over every pair examined
    best.update({"p_raw": round(p_raw, 6), "p_bonferroni": round(p_adj, 6),
                 "tested_pairs": n_pairs, "significant": p_adj < ALPHA})
    return best


def run_diagnostics(draws: list, max_number: int) -> dict:
    """Point 4: measure the structures a predictable lottery would have."""
    ac = autocorrelation_presence(draws, max_number)
    shift = rolling_frequency_shift(draws, max_number, 100)
    lifts = pair_lift(draws, max_number)
    strongest_lag = max(ac.items(), key=lambda kv: abs(kv[1]))[0] if ac else None
    strongest_val = ac.get(strongest_lag, 0.0) if strongest_lag else 0.0
    # a persistent temporal structure would sit far outside +-2/sqrt(n)
    threshold = 2 / math.sqrt(max(1, len(draws)))
    reading = []
    if ac:
        reading.append(
            f"Autocorrelación máxima {strongest_val:+.4f} en lag {strongest_lag} "
            f"(umbral de ruido ±{threshold:.4f}): "
            + ("por encima del ruido." if abs(strongest_val) > threshold else
               "dentro del ruido, sin memoria temporal aprovechable.")
        )
    if shift.get("mean_abs_shift") is not None:
        reading.append(
            f"Desplazamiento medio de frecuencias {shift['mean_abs_shift']:.4f} frente a "
            f"{shift['expected_noise_shift']:.4f} esperado por puro muestreo: "
            + ("hay cambio de régimen." if shift["mean_abs_shift"] > shift["expected_noise_shift"]
               else "compatible con azar estacionario.")
        )
    pair_sig = top_pair_significance(draws, max_number)
    if lifts:
        reading.append(
            f"El par más extremo ({pair_sig.get('a')}-{pair_sig.get('b')}) aparece "
            f"{pair_sig.get('lift', 0):.2f}× lo esperado; tras corregir por las "
            f"{pair_sig.get('tested_pairs', 0)} parejas examinadas "
            + ("sigue siendo significativo." if pair_sig.get("significant")
               else "no es significativo (es el más afortunado, no uno especial).")
        )
    return {
        "autocorrelation_presence": ac,
        "strongest_lag": strongest_lag,
        "strongest_autocorrelation": round(strongest_val, 5),
        "autocorrelation_above_noise": bool(abs(strongest_val) > threshold),
        "noise_threshold": round(threshold, 5),
        "rolling_shift_100": shift,
        "regime_shift_above_noise": bool(
            shift.get("mean_abs_shift") is not None
            and shift["mean_abs_shift"] > shift["expected_noise_shift"]),
        "top_pair_lifts": lifts,
        "top_pair_significance": pair_sig,
        "reading": " ".join(reading),
    }


# --------------------------------------------------------------------------- #
# 5. Temporal permutation test
# --------------------------------------------------------------------------- #
def temporal_permutation_test(draws: list, evaluate_fn, n_permutations: int = 40,
                              seed: int = 42) -> dict:
    """Does the ORDER of the draws carry predictive information?

    Null hypothesis: shuffling the chronological order changes nothing. Each
    draw keeps its exact six numbers; only the sequence is randomized, which
    destroys any temporal structure while preserving composition. If the model's
    real score sits inside the shuffled distribution, whatever it "learned" was
    not time-dependent signal.

    `evaluate_fn(sequence) -> mean_hits` is supplied by the caller so this works
    for any arm of the ensemble.
    """
    observed = evaluate_fn(draws)
    rng = random.Random(seed)
    null: list[float] = []
    for _ in range(n_permutations):
        perm = list(draws)
        rng.shuffle(perm)
        null.append(evaluate_fn(perm))
    mean_null = sum(null) / len(null) if null else 0.0
    if len(null) > 1:
        var = sum((v - mean_null) ** 2 for v in null) / (len(null) - 1)
        sd = math.sqrt(var)
    else:
        sd = 0.0
    return {
        "observed_mean_hits": round(observed, 5),
        "null_mean_hits": round(mean_null, 5),
        "null_std_hits": round(sd, 5),
        "p_value": round(permutation_pvalue(observed, null, True), 5),
        "n_permutations": len(null),
        "null_definition": "orden de sorteos aleatorizado; números de cada sorteo intactos",
    }


# --------------------------------------------------------------------------- #
# Promotion policy (point 6 + 7)
# --------------------------------------------------------------------------- #
def promotion_decision(metrics: dict, alpha: float = ALPHA,
                       min_improvement: float = MIN_IMPROVEMENT_V3) -> dict:
    """Conservative Champion policy, now on the CORRECTED q-value.

    Requires: out-of-sample, a real margin over the empirical random baseline,
    corrected significance, several independent windows, and — when it was
    evaluated — survival on the Golden Holdout.
    """
    improvement = metrics.get("improvement_vs_random", 0.0)
    q = metrics.get("q_value", 1.0)
    oos = bool(metrics.get("out_of_sample", False))
    windows_won = metrics.get("windows_won", 0)
    min_windows = metrics.get("min_windows", 2)
    golden_ok = metrics.get("golden_holdout_passed", True)

    reasons = []
    if not oos:
        reasons.append("la métrica no es out-of-sample")
    if improvement < min_improvement:
        reasons.append(f"mejora {improvement:+.4f} < mínimo {min_improvement}")
    if q > alpha:
        reasons.append(f"q-valor corregido {q:.4f} > {alpha}")
    if windows_won < min_windows:
        reasons.append(f"ganó {windows_won} ventana(s) de {min_windows} requeridas")
    if not golden_ok:
        reasons.append("no superó el Golden Holdout")

    promote = not reasons
    return {
        "promote": promote,
        "reason": ("Cumple todos los criterios corregidos out-of-sample."
                   if promote else "No se promueve: " + "; ".join(reasons) + "."),
        "min_improvement": min_improvement,
        "alpha": alpha,
        "q_value": q,
    }
