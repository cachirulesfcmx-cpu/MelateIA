"""Evolutionary ensemble — full port of the "Melate Genius" engine.

13 statistical base models, each producing a per-number probability distribution
over the history. Their weights are *evolved* by walk-forward evaluation (top-k
precision of each model over recent draws) and combined via a temperature
softmax. On top of the fused distribution a "meta-consciousness" layer applies:
  - consensus boost (numbers many models agree on)
  - error memory (boost numbers that came out but we ignored; penalize repeated
    misses) — from the user's real evaluated predictions
  - acceleration (numbers trending up in the last draws)

Tickets are then sampled DIRECTLY from this distribution (roulette wheel), the
way Genius does it — so suggestions concentrate on the numbers the models favor,
instead of being dispersed by symbolic strategy profiles.

Only applies to COMBINATION games. Tris (positional) keeps its own engine.

Honest framing: the lottery is random; this reproduces Genius's behavior and
calibration — it does not make the draw predictable.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from heapq import nlargest

from .game_config import GameConfig

# Cap how much history each model digests, for performance on long histories
# (Chispazo has 10k+ draws). Recency-focused, matches Genius's recency emphasis.
HIST_CAP = 800
# Walk-forward evaluation window (last N draws) and per-step train cap.
WF_WINDOW = 70
WF_TRAIN_CAP = 450


def _normalize(d: dict[int, float]) -> dict[int, float]:
    s = sum(d.values())
    if s <= 0:
        n = len(d) or 1
        return {k: 1.0 / n for k in d}
    return {k: v / s for k, v in d.items()}


def _nums(cfg: GameConfig) -> range:
    return range(1, cfg.max_number + 1)


# --------------------------------------------------------------------------- #
# Base models: history (oldest->newest) -> {number: probability}
# Faithful ports of the Genius JS models (1-indexed, normalized).
# --------------------------------------------------------------------------- #
def m_bayes_decay(history, cfg, decay: float = 0.97) -> dict[int, float]:
    counts = {n: 1.0 for n in _nums(cfg)}  # Laplace prior
    total = len(history)
    for i, draw in enumerate(history):
        w = decay ** (total - 1 - i)
        for x in draw:
            if 1 <= x <= cfg.max_number:
                counts[x] += w
    return _normalize(counts)


def m_gap_hazard(history, cfg) -> dict[int, float]:
    """Survival-analysis hazard with a logistic curve (Genius M2)."""
    maxn = cfg.max_number
    last = {n: -1 for n in range(maxn + 1)}
    tot_gap = {n: 0.0 for n in range(maxn + 1)}
    gap_cnt = {n: 0 for n in range(maxn + 1)}
    for i, draw in enumerate(history):
        for n in draw:
            if 1 <= n <= maxn:
                if last[n] >= 0:
                    tot_gap[n] += i - last[n]
                    gap_cnt[n] += 1
                last[n] = i
    n = len(history)
    h = {}
    for num in _nums(cfg):
        avg = tot_gap[num] / gap_cnt[num] if gap_cnt[num] > 0 else n / max(1, cfg.pick)
        cur = n - 1 - last[num] if last[num] >= 0 else n
        ratio = cur / max(avg, 1)
        h[num] = 1.0 / (1.0 + math.exp(-1.5 * (ratio - 1)))
    return _normalize(h)


def m_cooccurrence(history, cfg) -> dict[int, float]:
    cooc = defaultdict(float)
    for r in history:
        rs = [x for x in r if 1 <= x <= cfg.max_number]
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = (rs[i], rs[j]) if rs[i] < rs[j] else (rs[j], rs[i])
                cooc[(a, b)] += 1.0
    recent_nums = set(x for r in history[-30:] for x in r if 1 <= x <= cfg.max_number)
    s = {}
    for num in _nums(cfg):
        acc = 0.0
        for o in recent_nums:
            if o != num:
                a, b = (num, o) if num < o else (o, num)
                acc += cooc.get((a, b), 0.0)
        s[num] = acc
    return _normalize(s)


def m_frequency(history, cfg) -> dict[int, float]:
    f = {n: 0.0 for n in _nums(cfg)}
    for r in history:
        for x in r:
            if 1 <= x <= cfg.max_number:
                f[x] += 1.0
    return _normalize(f)


def m_momentum(history, cfg, alpha: float = 0.15) -> dict[int, float]:
    ewma = {n: 0.0 for n in _nums(cfg)}
    for r in history:
        drawn = set(r)
        for n in _nums(cfg):
            ewma[n] = alpha * (1.0 if n in drawn else 0.0) + (1 - alpha) * ewma[n]
    return _normalize({n: v + 1e-9 for n, v in ewma.items()})


def m_markov(history, cfg, laplace: float = 0.5) -> dict[int, float]:
    maxn = cfg.max_number
    nums = list(_nums(cfg))
    if len(history) < 10:
        return {n: 1.0 / maxn for n in nums}
    trans = defaultdict(lambda: defaultdict(float))
    for t in range(1, len(history)):
        for i in history[t - 1]:
            if 1 <= i <= maxn:
                row = trans[i]
                for j in history[t]:
                    if 1 <= j <= maxn:
                        row[j] += 1.0
    last = history[-1]
    probs = {}
    for j in nums:
        p = 0.0
        for i in last:
            if 1 <= i <= maxn:
                row = trans.get(i, {})
                cnt = row.get(j, 0.0) + laplace
                row_sum = sum(row.values()) + laplace * maxn
                p += cnt / row_sum if row_sum else 0.0
        probs[j] = p / max(1, len(last))
    return _normalize(probs)


def m_fourier(history, cfg) -> dict[int, float]:
    """Cyclic-pattern model via autocorrelation (Genius M7), numpy-vectorized."""
    import numpy as np
    n = len(history)
    maxn = cfg.max_number
    if n < 50:
        return {x: 1.0 / maxn for x in _nums(cfg)}
    max_lag = min(80, n // 3)
    # binary occurrence matrix: rows = numbers (1..maxn), cols = draws
    mat = np.zeros((maxn + 1, n), dtype=np.float64)
    for t, draw in enumerate(history):
        for x in draw:
            if 1 <= x <= maxn:
                mat[x, t] = 1.0
    series = mat[1:]                       # (maxn, n)
    mean = series.mean(axis=1, keepdims=True)
    centered = series - mean
    var0 = (centered ** 2).mean(axis=1)    # (maxn,)
    probs = {}
    base = 1.0 / maxn
    for idx in range(maxn):
        num = idx + 1
        if var0[idx] < 1e-9:
            probs[num] = base
            continue
        c = centered[idx]
        best_lag, best_corr = 0, 0.0
        for lag in range(2, max_lag + 1):
            cov = float(np.dot(c[:n - lag], c[lag:])) / (n - lag)
            corr = cov / var0[idx]
            if abs(corr) > abs(best_corr):
                best_corr, best_lag = corr, lag
        prob = base
        if abs(best_corr) > 0.05 and best_lag > 0:
            nz = np.nonzero(series[idx])[0]
            if nz.size:
                since_last = n - 1 - int(nz[-1])
                phase = since_last % best_lag
                dist_return = (best_lag - phase) % best_lag
                boost = math.exp(-dist_return / (best_lag * 0.3)) * abs(best_corr)
                prob = base * (1 + 3 * boost * (1 if best_corr >= 0 else -1))
        probs[num] = max(prob, 1e-6)
    return _normalize(probs)


def m_positional(history, cfg) -> dict[int, float]:
    """Per-position (sorted) histogram aggregated per number (Genius M8)."""
    pick = cfg.pick
    maxn = cfg.max_number
    pos_hist = [[0.5] * (maxn + 1) for _ in range(pick)]
    for draw in history:
        s = sorted(x for x in draw if 1 <= x <= maxn)
        for pos, n in enumerate(s):
            if pos < pick:
                pos_hist[pos][n] += 1
    for pos in range(pick):
        tot = sum(pos_hist[pos])
        if tot > 0:
            pos_hist[pos] = [v / tot for v in pos_hist[pos]]
    probs = {}
    for n in _nums(cfg):
        probs[n] = sum(pos_hist[pos][n] for pos in range(pick)) / pick
    return _normalize(probs)


def m_gaussian(history, cfg) -> dict[int, float]:
    """Fit numbers to the typical draw-sum distribution (Genius M9)."""
    pick = cfg.pick
    if not history:
        return {n: 1.0 / cfg.max_number for n in _nums(cfg)}
    sums = [sum(r) for r in history]
    mu_sum = sum(sums) / len(sums)
    sig_sum = math.sqrt(sum((x - mu_sum) ** 2 for x in sums) / len(sums)) or 1.0
    freq = {n: 0.0 for n in _nums(cfg)}
    for r in history:
        for x in r:
            if 1 <= x <= cfg.max_number:
                freq[x] += 1.0
    base_total = sum(freq.values()) or 1.0
    expected = mu_sum / pick
    sig = sig_sum / pick
    probs = {}
    for n in _nums(cfg):
        base = freq[n] / base_total
        fit = math.exp(-((n - expected) ** 2) / (2 * sig ** 2 + 1))
        probs[n] = base * 0.7 + (fit * (1.0 / cfg.max_number)) * 0.3
    return _normalize(probs)


def m_delta(history, cfg) -> dict[int, float]:
    """Gap-between-sorted-numbers pattern model (Genius M10)."""
    maxn = cfg.max_number
    if len(history) < 20:
        return {n: 1.0 / maxn for n in _nums(cfg)}
    delta_freq = {d: 0.0 for d in range(maxn + 1)}
    delta_tot = 0
    for draw in history:
        s = sorted(x for x in draw if 1 <= x <= maxn)
        for i in range(1, len(s)):
            d = s[i] - s[i - 1]
            if 1 <= d <= maxn:
                delta_freq[d] += 1
                delta_tot += 1
    dp = {d: delta_freq[d] / (delta_tot or 1) for d in range(maxn + 1)}
    probs = {}
    for num in _nums(cfg):
        sc = 0.0
        for d in range(1, min(num - 1, maxn) + 1):
            sc += dp[d]
        d = 1
        while d + num <= maxn:
            sc += dp[d]
            d += 1
        probs[num] = sc
    return _normalize(probs)


def m_hot_streak(history, cfg, window: int = 15) -> dict[int, float]:
    maxn = cfg.max_number
    base = 1.0 / maxn
    if len(history) < 15:
        return {n: base for n in _nums(cfg)}
    w = min(window, len(history))
    recent = history[-w:]
    freq = {n: 0.0 for n in _nums(cfg)}
    for r in recent:
        for x in r:
            if 1 <= x <= maxn:
                freq[x] += 1.0
    expected = w * cfg.pick / maxn
    probs = {}
    for n in _nums(cfg):
        ratio = freq[n] / max(expected, 0.1)
        if ratio >= 2.0:
            probs[n] = base * 1.8
        elif ratio >= 1.4:
            probs[n] = base * 1.3
        elif ratio == 0:
            probs[n] = base * 1.2
        else:
            probs[n] = base * (0.8 + ratio * 0.2)
    return _normalize(probs)


def m_zone_pressure(history, cfg, zones: int = 4, window: int = 20) -> dict[int, float]:
    maxn = cfg.max_number
    base = 1.0 / maxn
    if len(history) < 10:
        return {n: base for n in _nums(cfg)}
    zone_size = math.ceil(maxn / zones)
    recent = history[-window:]
    zfreq = [0.0] * zones
    ztotal = 0
    for r in recent:
        for n in r:
            if 1 <= n <= maxn:
                z = min((n - 1) // zone_size, zones - 1)
                zfreq[z] += 1
                ztotal += 1
    zexp = ztotal / zones if zones else 0
    probs = {}
    for n in _nums(cfg):
        z = min((n - 1) // zone_size, zones - 1)
        deficit = max(0.0, zexp - zfreq[z])
        probs[n] = base * (1 + (deficit / max(zexp, 1)) * 0.5)
    return _normalize(probs)


def m_pair_lift(history, cfg) -> dict[int, float]:
    """Lift of co-appearance vs independence (Genius M13)."""
    maxn = cfg.max_number
    if len(history) < 30:
        return {n: 1.0 / maxn for n in _nums(cfg)}
    freq = {n: 0.0 for n in range(maxn + 1)}
    for r in history:
        for x in r:
            if 1 <= x <= maxn:
                freq[x] += 1.0
    n = len(history)
    cooc = defaultdict(float)
    for r in history:
        rs = [x for x in r if 1 <= x <= maxn]
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = (rs[i], rs[j]) if rs[i] < rs[j] else (rs[j], rs[i])
                cooc[(a, b)] += 1.0
    recent_set = set(x for r in history[-25:] for x in r if 1 <= x <= maxn)
    pick = cfg.pick
    probs = {}
    for num in _nums(cfg):
        lift = 0.0
        for o in recent_set:
            if o == num:
                continue
            a, b = (num, o) if num < o else (o, num)
            p_ab = cooc.get((a, b), 0.0) / n
            p_a = freq[num] / (n * pick)
            p_b = freq[o] / (n * pick)
            if p_a > 0 and p_b > 0:
                lift += p_ab / (p_a * p_b * n)
        probs[num] = lift
    return _normalize(probs)


def m_repeat_carry(history, cfg) -> dict[int, float]:
    """Repeat-carry (Genius M14): how often numbers from the previous draw
    reappear in the next one, measured on THIS game's real history. Last draw's
    numbers get exactly the measured lift vs pure chance — honest calibration."""
    maxn = cfg.max_number
    base = 1.0 / maxn
    if len(history) < 10:
        return {n: base for n in _nums(cfg)}
    repeats = 0
    slots = 0
    for t in range(1, len(history)):
        prev = set(history[t - 1])
        for x in history[t]:
            if 1 <= x <= maxn:
                slots += 1
                if x in prev:
                    repeats += 1
    rate = repeats / max(1, slots)
    chance = cfg.pick / maxn
    lift = rate / max(chance, 1e-9)
    last = set(x for x in history[-1] if 1 <= x <= maxn)
    probs = {n: base * (lift if n in last else 1.0) for n in _nums(cfg)}
    return _normalize(probs)


def m_neighbor(history, cfg) -> dict[int, float]:
    """Neighbor drift (Genius M15): numbers adjacent (±1, ±2) to the previous
    draw, boosted by the adjacency rate measured on the real history."""
    maxn = cfg.max_number
    base = 1.0 / maxn
    if len(history) < 10:
        return {n: base for n in _nums(cfg)}
    hit1 = hit2 = slots = 0
    for t in range(1, len(history)):
        prev = set(history[t - 1])
        for x in history[t]:
            if 1 <= x <= maxn:
                slots += 1
                if (x - 1) in prev or (x + 1) in prev:
                    hit1 += 1
                elif (x - 2) in prev or (x + 2) in prev:
                    hit2 += 1
    r1 = hit1 / max(1, slots)
    r2 = hit2 / max(1, slots)
    last = set(x for x in history[-1] if 1 <= x <= maxn)
    probs = {}
    for n in _nums(cfg):
        if (n - 1) in last or (n + 1) in last:
            probs[n] = base * (1 + 3 * r1)
        elif (n - 2) in last or (n + 2) in last:
            probs[n] = base * (1 + 2 * r2)
        else:
            probs[n] = base
    return _normalize(probs)


MODELS = {
    "bayes_decay": m_bayes_decay,
    "gap_hazard": m_gap_hazard,
    "cooccurrence": m_cooccurrence,
    "frequency": m_frequency,
    "momentum": m_momentum,
    "markov": m_markov,
    "fourier": m_fourier,
    "positional": m_positional,
    "gaussian": m_gaussian,
    "delta": m_delta,
    "hot_streak": m_hot_streak,
    "zone_pressure": m_zone_pressure,
    "pair_lift": m_pair_lift,
    "repeat_carry": m_repeat_carry,
    "neighbor": m_neighbor,
}
MODEL_KEYS = list(MODELS.keys())

MODEL_LABELS = {
    "bayes_decay": "Bayesiano (decay)",
    "gap_hazard": "Atraso (hazard)",
    "cooccurrence": "Co-ocurrencia",
    "frequency": "Frecuencia",
    "momentum": "Momentum (EWMA)",
    "markov": "Markov (orden 1)",
    "fourier": "Fourier (ciclos)",
    "positional": "Posicional",
    "gaussian": "Mezcla gaussiana",
    "delta": "Patrón delta",
    "hot_streak": "Racha caliente",
    "zone_pressure": "Presión por zona",
    "pair_lift": "Pair lift",
    "repeat_carry": "Arrastre (repite)",
    "neighbor": "Vecinos (±1/±2)",
}


def _topk_for(cfg: GameConfig) -> int:
    return max(cfg.pick + 2, round(cfg.max_number * 0.27))


def all_model_probabilities(history, cfg) -> dict[str, dict[int, float]]:
    h = history[-HIST_CAP:] if len(history) > HIST_CAP else history
    return {k: fn(h, cfg) for k, fn in MODELS.items()}


def walk_forward_scores(history, cfg, window: int = WF_WINDOW) -> dict[str, float]:
    """Top-k precision of each model over the last `window` draws (no look-ahead)."""
    n = len(history)
    start = max(30, n - window)
    if start >= n:
        return {k: 1.0 / len(MODELS) for k in MODELS}
    topk = _topk_for(cfg)
    hits = {k: 0.0 for k in MODELS}
    trials = 0
    for t in range(start, n):
        train = history[max(0, t - WF_TRAIN_CAP):t]
        actual = set(history[t])
        for k, fn in MODELS.items():
            probs = fn(train, cfg)
            top = set(num for num, _ in nlargest(topk, probs.items(), key=lambda kv: kv[1]))
            hits[k] += len(actual & top)
        trials += len(actual)
    return {k: hits[k] / max(1, trials) for k in MODELS}


def evolve_weights(scores: dict[str, float], temperature: float = 120.0, floor: float = 0.03) -> dict[str, float]:
    """Softmax over walk-forward scores. temperature=120 (measured best on the
    real Melate history, 200-draw walk-forward) reacts harder to score gaps, so
    each new result moves the weights more decisively."""
    if not scores:
        return {}
    mx = max(scores.values())
    exps = {k: math.exp((v - mx) * temperature) for k, v in scores.items()}
    se = sum(exps.values()) or 1.0
    w = {k: v / se for k, v in exps.items()}
    fl = min(floor, 0.30 / len(w))
    w = {k: max(v, fl) for k, v in w.items()}
    s = sum(w.values()) or 1.0
    return {k: v / s for k, v in w.items()}


# in-memory cache so requests are cheap between draws
_ENS_CACHE: dict[str, dict] = {}


def compute_weights(history, cfg, force: bool = False) -> dict:
    key = cfg.key
    cached = _ENS_CACHE.get(key)
    if cached and not force and cached.get("n_draws") == len(history):
        return cached
    scores = walk_forward_scores(history, cfg)
    weights = evolve_weights(scores)
    out = {"weights": weights, "scores": scores, "n_draws": len(history)}
    _ENS_CACHE[key] = out
    return out


def set_weights(cfg: GameConfig, weights: dict[str, float], scores: dict[str, float],
                n_draws: int) -> None:
    """Install externally-governed weights into the cache.

    Used after persisting weights with the constitution's inertia cap applied,
    so predictions use exactly the governed mix, not the raw recomputation.
    """
    _ENS_CACHE[cfg.key] = {"weights": dict(weights), "scores": dict(scores),
                           "n_draws": n_draws, "backbone": None}


def genius_backbone(history, cfg) -> dict[int, float]:
    """Fused Genius distribution (no ML blend, no meta) cached per draw count.
    Used to reinforce EVERY combination strategy's sampling weights, so the
    whole app runs on the Genius engine, not just the Evolutiva strategy."""
    info = compute_weights(history, cfg)
    if info.get("backbone") is None:
        info["backbone"] = fused_probabilities(history, cfg, weights=info["weights"])
    return info["backbone"]


def fused_probabilities(history, cfg, weights: dict[str, float] | None = None,
                        ml_probs: dict[int, float] | None = None, ml_blend: float = 0.5) -> dict[int, float]:
    """Weighted fusion of the 13 base models, optionally blended with the XGBoost
    per-number model (the prior MelateIA model becomes one more voice)."""
    if weights is None:
        weights = compute_weights(history, cfg)["weights"]
    model_probs = all_model_probabilities(history, cfg)
    fused = {n: 0.0 for n in _nums(cfg)}
    for k, probs in model_probs.items():
        w = weights.get(k, 0.0)
        if w <= 0:
            continue
        for n in fused:
            fused[n] += w * probs.get(n, 0.0)
    fused = _normalize(fused)
    if ml_probs:
        ml = _normalize({n: ml_probs.get(n, 0.0) for n in _nums(cfg)})
        fused = _normalize({n: (1 - ml_blend) * fused[n] + ml_blend * ml[n] for n in _nums(cfg)})
    return fused


def meta_probabilities(history, cfg, fused: dict[int, float],
                       model_probs: dict[str, dict[int, float]] | None = None,
                       evaluated: list[tuple[set, set]] | None = None,
                       memory: int = 40) -> dict[int, float]:
    """Genius "meta-consciousness": consensus + error memory + acceleration.

    `evaluated` is a list of (predicted_set, actual_set) from recent real
    evaluated predictions (most recent last). Optional — consensus and
    acceleration work without it.
    """
    maxn = cfg.max_number
    if model_probs is None:
        model_probs = all_model_probabilities(history, cfg)

    # 1. consensus: fraction of models that rank n in their top 15
    consensus = {n: 0 for n in range(maxn + 1)}
    for probs in model_probs.values():
        for num, _ in nlargest(15, probs.items(), key=lambda kv: kv[1]):
            consensus[num] += 1
    nmodels = len(model_probs) or 1
    consensus = {n: c / nmodels for n, c in consensus.items()}

    # 2. error memory from the last `memory` evaluated predictions
    over = {n: 0 for n in range(maxn + 1)}
    under = {n: 0 for n in range(maxn + 1)}
    recent_checked = (evaluated or [])[-memory:]
    n15 = len(recent_checked) or 1
    for predicted, actual in recent_checked:
        for n in predicted:
            if 1 <= n <= maxn and n not in actual:
                over[n] += 1
        for n in actual:
            if 1 <= n <= maxn and n not in predicted:
                under[n] += 1

    # 3. acceleration: recent (last 10) vs older (prev 10) frequency
    recent_draws = history[-10:]
    older_draws = history[-20:-10]
    rf = {n: 0 for n in range(maxn + 1)}
    of = {n: 0 for n in range(maxn + 1)}
    for d in recent_draws:
        for n in d:
            if 1 <= n <= maxn:
                rf[n] += 1
    for d in older_draws:
        for n in d:
            if 1 <= n <= maxn:
                of[n] += 1
    rn = len(recent_draws) or 1
    on = len(older_draws) or 1

    meta = {}
    for n in _nums(cfg):
        base = fused.get(n, 0.0)
        consensus_bonus = consensus[n] * 0.25 * base
        over_penalty = (over[n] / n15) * 0.30 * base
        under_bonus = (under[n] / n15) * 0.20 * base
        rr, orr = rf[n] / rn, of[n] / on
        accel_bonus = (rr - orr) * 0.5 * base if rr > orr else 0.0
        meta[n] = max(0.0001, base + consensus_bonus - over_penalty + under_bonus + accel_bonus)
    return _normalize(meta)


# --------------------------------------------------------------------------- #
# Ticket generation — sample directly from the distribution (Genius style)
# --------------------------------------------------------------------------- #
def _jaccard(a, b) -> float:
    A, B = set(a), set(b)
    inter = len(A & B)
    return inter / (len(A) + len(B) - inter or 1)


def _sample_ticket(probs: dict[int, float], cfg: GameConfig, rng: random.Random) -> list[int]:
    pick = cfg.pick
    nums = list(_nums(cfg))
    chosen: list[int] = []
    used: set[int] = set()
    attempts = 0
    while len(chosen) < pick and attempts < 1000:
        attempts += 1
        r = rng.random()
        cum = 0.0
        for n in nums:
            if n in used:
                continue
            cum += probs.get(n, 0.0)
            if r <= cum:
                chosen.append(n)
                used.add(n)
                break
    for n in nums:
        if len(chosen) >= pick:
            break
        if n not in used:
            chosen.append(n)
            used.add(n)
    return sorted(chosen)


def _history_ctx(history, cfg) -> tuple[dict, dict, int]:
    """Precompute per-number frequency and last-seen index once, so scoring a
    large candidate pool doesn't rescan the whole history per ticket."""
    maxn = cfg.max_number
    freq = {n: 0 for n in range(maxn + 1)}
    last = {n: -1 for n in range(maxn + 1)}
    for i, r in enumerate(history):
        for x in r:
            if 0 <= x <= maxn:
                freq[x] += 1
                last[x] = i
    return freq, last, len(history)


def score_ticket(t: list[int], probs: dict[int, float], history, cfg,
                 ctx: tuple[dict, dict, int] | None = None) -> dict:
    """Genius scoreTicket: 0.45 prob + 0.18 parity + 0.17 spread + 0.20 gap."""
    maxn = cfg.max_number
    pick = len(t) or cfg.pick
    pr = sum(math.log(max(probs.get(n, 1e-10), 1e-10)) for n in t) / pick
    evens = sum(1 for n in t if n % 2 == 0)
    parity = 1 - abs(evens / pick - 0.5) * 2
    decs = {(n - 1) // 10 for n in t}
    spread = len(decs) / math.ceil(maxn / 10)
    freq, last, n = ctx if ctx is not None else _history_ctx(history, cfg)
    gap = 0.0
    for num in t:
        avg = n / max(freq[num], 1)
        cur = n - 1 - last[num] if last[num] >= 0 else n
        gap += (min(cur / avg, 2) if avg > 0 else 0.0) / pick
    prob_score = math.exp(pr)
    total = 0.45 * prob_score + 0.18 * parity + 0.17 * spread + 0.20 * gap
    return {"prob_score": prob_score, "total": total, "parity": parity,
            "spread": spread, "gap": gap, "evens": evens, "odds": pick - evens,
            "sum": sum(t)}


def generate_genius_tickets(probs: dict[int, float], history, cfg, count: int = 5,
                            seed: int | None = None, pool_factor: int = 40,
                            sharpness: float = 1.8) -> list[dict]:
    """Pool optimizer: oversample a large candidate pool from `probs`, score
    EVERY candidate, then greedily keep the `count` best mutually-diverse
    tickets — instead of settling for the first `count` samples.

    `sharpness` > 1 concentrates sampling on the engine's favorite numbers
    (probs^alpha, renormalized). 1.8 measured best on the real history."""
    rng = random.Random(seed)
    if sharpness and sharpness != 1.0:
        probs = _normalize({n: max(v, 1e-12) ** sharpness for n, v in probs.items()})
    target_pool = min(400, max(count * pool_factor, 120))
    pool: dict[tuple, list[int]] = {}
    tries = 0
    while len(pool) < target_pool and tries < target_pool * 6:
        tries += 1
        t = _sample_ticket(probs, cfg, rng)
        pool[tuple(t)] = t
    ctx = _history_ctx(history, cfg)
    scored = [{"ticket": t, "score": score_ticket(t, probs, history, cfg, ctx=ctx)}
              for t in pool.values()]
    scored.sort(key=lambda x: x["score"]["total"], reverse=True)
    tickets: list[dict] = []
    used: list[list[int]] = []
    for item in scored:
        if len(tickets) >= count:
            break
        if any(_jaccard(item["ticket"], u) > 0.6 for u in used):
            continue
        tickets.append(item)
        used.append(item["ticket"])
    if len(tickets) < count:  # diversity too strict → pad with next best
        chosen = {tuple(x["ticket"]) for x in tickets}
        for item in scored:
            if len(tickets) >= count:
                break
            if tuple(item["ticket"]) not in chosen:
                tickets.append(item)
                chosen.add(tuple(item["ticket"]))
    while len(tickets) < count:
        t = _sample_ticket(probs, cfg, rng)
        tickets.append({"ticket": t, "score": score_ticket(t, probs, history, cfg, ctx=ctx)})
    return tickets
