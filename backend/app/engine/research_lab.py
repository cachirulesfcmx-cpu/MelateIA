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
# v4 STATISTICAL LAB — mutual information, change point, drift, block bootstrap
# --------------------------------------------------------------------------- #
def _entropy(counts: list[int], total: int) -> float:
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            h -= p * math.log(p)
    return h


def _mi_from_matrix(x, max_number: int) -> list[tuple[int, int, float, int]]:
    """Pairwise mutual information from a 0/1 presence matrix (n x max_number)."""
    n = x.shape[0]
    co = x.T @ x                      # n11 for every pair
    ca = x.sum(axis=0)                # marginal per number
    out = []
    for a in range(max_number):
        for b in range(a + 1, max_number):
            n11 = co[a, b]
            n10 = ca[a] - n11
            n01 = ca[b] - n11
            n00 = n - n11 - n10 - n01
            mi = 0.0
            for nij, ni, nj in ((n11, ca[a], ca[b]), (n10, ca[a], n - ca[b]),
                                (n01, n - ca[a], ca[b]), (n00, n - ca[a], n - ca[b])):
                if nij > 0 and ni > 0 and nj > 0:
                    mi += (nij / n) * math.log((nij * n) / (ni * nj))
            out.append((a + 1, b + 1, float(mi), int(n11)))
    return out


def mutual_information_pairs(draws: list, max_number: int, top_k: int = 10) -> list[dict]:
    """Mutual information between the presence of each pair of numbers.

    MI is zero when two numbers appear independently. In a fair draw every pair
    sits at the level produced by finite-sample noise.
    """
    n = len(draws)
    if n < 50:
        return []
    if HAS_NUMPY:
        x = np.zeros((n, max_number), dtype=np.float64)
        for i, d in enumerate(draws):
            for num in d:
                if 1 <= num <= max_number:
                    x[i, num - 1] = 1.0
        rows = _mi_from_matrix(x, max_number)
    else:  # pragma: no cover
        present = [set(d) for d in draws]
        counts = {num: sum(1 for s in present if num in s) for num in range(1, max_number + 1)}
        rows = []
        for a in range(1, max_number + 1):
            for b in range(a + 1, max_number + 1):
                n11 = sum(1 for s in present if a in s and b in s)
                n10, n01 = counts[a] - n11, counts[b] - n11
                n00 = n - n11 - n10 - n01
                mi = 0.0
                for nij, ni, nj in ((n11, counts[a], counts[b]), (n10, counts[a], n - counts[b]),
                                    (n01, n - counts[a], counts[b]), (n00, n - counts[a], n - counts[b])):
                    if nij > 0 and ni > 0 and nj > 0:
                        mi += (nij / n) * math.log((nij * n) / (ni * nj))
                rows.append((a, b, mi, n11))
    rows.sort(key=lambda r: r[2], reverse=True)
    return [{"a": a, "b": b, "mi": round(mi, 6), "together": c} for a, b, mi, c in rows[:top_k]]


MIN_NULL_REPS = 20


def max_mi_null(draws: list, max_number: int, reps: int = 30, seed: int = 42) -> dict:
    """Empirical null for the LARGEST mutual information across all pairs.

    The asymptotic chi-square approximation is unreliable here: the ~1,500 pairs
    are not independent and the 2x2 tables are heavily unbalanced, so it flags
    noise as signal. Shuffling each number's presence series independently
    destroys any dependence BETWEEN numbers while preserving how often each one
    appears, giving a calibrated threshold for "the luckiest pair".
    """
    n = len(draws)
    if not HAS_NUMPY or n < 50:
        return {"available": False, "reps": 0}
    x = np.zeros((n, max_number), dtype=np.float64)
    for i, d in enumerate(draws):
        for num in d:
            if 1 <= num <= max_number:
                x[i, num - 1] = 1.0
    rng = np.random.default_rng(seed)
    maxima = []
    for _ in range(reps):
        shuffled = np.empty_like(x)
        for j in range(max_number):
            shuffled[:, j] = rng.permutation(x[:, j])
        maxima.append(float(max(r[2] for r in _mi_from_matrix(shuffled, max_number))))
    maxima.sort()
    return {
        "available": True, "reps": reps, "enough_reps": reps >= MIN_NULL_REPS,
        "null_max_mean": round(sum(maxima) / len(maxima), 6),
        "null_max_p95": round(maxima[min(len(maxima) - 1, int(0.95 * len(maxima)))], 6),
        "null_max_observed_range": [round(maxima[0], 6), round(maxima[-1], 6)],
    }


def mi_noise_reference(n_draws: int) -> float:
    """Expected MI magnitude from finite-sample noise alone (~ df / (2n))."""
    return 1.0 / (2.0 * n_draws) if n_draws else 0.0


def mi_significance(top_mi: list[dict], n_draws: int, max_number: int,
                    null: dict | None = None) -> dict:
    """Is the strongest mutual information beyond what noise alone produces?

    Decided against the EMPIRICAL null of the maximum (`max_mi_null`) when it is
    available: the asymptotic chi-square would flag the luckiest of ~1,500
    correlated pairs on purely random data. The chi-square figure is still
    reported, but it does not decide.
    """
    n_pairs = max_number * (max_number - 1) // 2
    if not top_mi or n_draws <= 0:
        return {"tested_pairs": n_pairs, "significant": False}
    top = top_mi[0]
    g = 2.0 * n_draws * top["mi"]
    p_raw = math.erfc(math.sqrt(max(g, 0.0) / 2.0))   # chi2, 1 df — reference only
    out = {
        "a": top["a"], "b": top["b"], "mi": top["mi"], "g_statistic": round(g, 3),
        "p_chi2_bonferroni": round(min(1.0, p_raw * n_pairs), 6),
        "tested_pairs": n_pairs,
        "noise_reference_single_pair": round(mi_noise_reference(n_draws), 6),
    }
    if null and null.get("available") and null.get("enough_reps"):
        threshold = float(null["null_max_p95"])
        out.update({
            "null_max_p95": threshold,
            "null_max_mean": null["null_max_mean"],
            "decided_by": "null empírico del máximo",
            "significant": bool(float(top["mi"]) > threshold),
        })
    elif null and null.get("available"):
        out.update({
            "null_max_p95": float(null["null_max_p95"]),
            "decided_by": f"null insuficiente (<{MIN_NULL_REPS} repeticiones)",
            "significant": False,
        })
    else:
        out.update({"decided_by": "chi-cuadrado con Bonferroni",
                    "significant": bool(out["p_chi2_bonferroni"] < ALPHA)})
    return out


def change_point(draws: list) -> dict:
    """Scan for the split that most changes the mean draw-sum.

    A real regime change would show a standardized shift well above what random
    splits of a stationary series produce.
    """
    n = len(draws)
    if n < 100:
        return {"available": False, "reason": "se requieren al menos 100 sorteos"}
    sums = [sum(d) for d in draws]
    mean_all = sum(sums) / n
    sd = math.sqrt(sum((x - mean_all) ** 2 for x in sums) / n) or 1e-9
    best_cut, best_z = None, 0.0
    for c in range(50, n - 50, 10):
        left = sums[:c]
        right = sums[c:]
        z = abs(sum(left) / len(left) - sum(right) / len(right)) / sd
        if z > best_z:
            best_cut, best_z = c, z
    # a stationary series still produces some maximum by chance
    reference = 2.0 * math.sqrt(1.0 / 50 + 1.0 / 50)
    return {
        "available": True,
        "cut_index": best_cut,
        "standardized_shift": round(best_z, 5),
        "noise_reference": round(reference, 5),
        "significant": best_z > reference,
    }


def drift_l1(draws: list, max_number: int, window: int = 200) -> dict:
    """L1 distance between the number distributions of two consecutive windows,
    compared against the drift pure sampling noise would create."""
    if len(draws) < 2 * window:
        return {"available": False, "window": window}
    pick = 6

    def freq(ds):
        c = Counter(n for d in ds for n in d if 1 <= n <= max_number)
        tot = sum(c.values()) or 1
        return [c.get(n, 0) / tot for n in range(1, max_number + 1)]

    a = freq(draws[-2 * window:-window])
    b = freq(draws[-window:])
    l1 = sum(abs(x - y) for x, y in zip(a, b))
    reference = math.sqrt(2 * max_number / (pick * window))
    return {"available": True, "window": window, "l1": round(l1, 5),
            "sampling_reference": round(reference, 5),
            "above_noise": l1 > reference}


def block_bootstrap(draws: list, block: int = 10, reps: int = 300,
                    seed: int = 42, statistic=None) -> dict:
    """Resample in contiguous BLOCKS, not individual draws.

    Plain bootstrap destroys local temporal structure and so understates the
    uncertainty of any time-dependent claim. Blocks preserve it, giving an
    honest confidence interval.
    """
    n = len(draws)
    if n < block * 3:
        return {"available": False, "reps": 0}
    if statistic is None:
        def statistic(sample):
            return sum(sum(d) for d in sample) / len(sample)
    blocks = [draws[i:i + block] for i in range(0, n, block)]
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        sample = []
        for _ in range(len(blocks)):
            sample.extend(blocks[rng.randrange(len(blocks))])
        means.append(statistic(sample))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[min(len(means) - 1, int(0.975 * len(means)))]
    mean = sum(means) / len(means)
    return {"available": True, "reps": reps, "block_size": block,
            "mean": round(mean, 4), "ci95": [round(lo, 4), round(hi, 4)],
            "observed": round(statistic(draws), 4)}


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
