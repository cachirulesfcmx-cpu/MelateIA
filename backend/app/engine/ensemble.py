"""Evolutionary ensemble (ported & adapted from the "Melate Genius" engine).

A set of cheap statistical base models, each producing a per-number probability
distribution over the history. Their weights are *evolved* by walk-forward
evaluation (how often each model's top picks actually appeared) and combined via
a temperature softmax — so the mix self-adjusts as the data grows.

This is fully self-contained and only applies to COMBINATION games (Melate,
Revancha, Retro, Revanchita, Chispazo). Tris (positional) keeps its own engine.

Honest framing: the lottery is random; this adds signal diversity + calibration
and a transparent "which model leads now" view — it does not predict the draw.
"""
from __future__ import annotations

import math
from collections import defaultdict
from heapq import nlargest

from .game_config import GameConfig


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


def m_markov(history, cfg, laplace: float = 0.5) -> dict[int, float]:
    nums = list(_nums(cfg))
    if len(history) < 10:
        return {n: 1.0 / len(nums) for n in nums}
    trans = defaultdict(lambda: defaultdict(float))
    for t in range(1, len(history)):
        for i in history[t - 1]:
            if 1 <= i <= cfg.max_number:
                row = trans[i]
                for j in history[t]:
                    if 1 <= j <= cfg.max_number:
                        row[j] += 1.0
    last = history[-1]
    probs = {n: 0.0 for n in nums}
    for j in nums:
        acc = 0.0
        for i in last:
            row = trans.get(i)
            cnt = (row.get(j, 0.0) if row else 0.0) + laplace
            row_sum = (sum(row.values()) if row else 0.0) + laplace * len(nums)
            acc += cnt / row_sum if row_sum else 0.0
        probs[j] = acc / max(1, len(last))
    return _normalize(probs)


def m_gap_hazard(history, cfg) -> dict[int, float]:
    total = len(history)
    freq = {n: 0 for n in _nums(cfg)}
    last_idx = {n: None for n in _nums(cfg)}
    for idx, draw in enumerate(history):
        for x in draw:
            if 1 <= x <= cfg.max_number:
                freq[x] += 1
                last_idx[x] = idx
    probs = {}
    for n in _nums(cfg):
        avg_gap = total / max(1, freq[n])
        cur_gap = (total - 1 - last_idx[n]) if last_idx[n] is not None else total
        probs[n] = min(cur_gap / avg_gap, 2.0) if avg_gap else 1.0
    return _normalize(probs)


def m_cooccurrence(history, cfg) -> dict[int, float]:
    pair = defaultdict(float)
    for draw in history:
        ds = [x for x in draw if 1 <= x <= cfg.max_number]
        for a in range(len(ds)):
            for b in range(len(ds)):
                if a != b:
                    pair[(ds[a], ds[b])] += 1.0
    last = history[-1] if history else []
    probs = {n: 0.0 for n in _nums(cfg)}
    for j in _nums(cfg):
        probs[j] = sum(pair.get((i, j), 0.0) for i in last) + 1e-3
    return _normalize(probs)


def m_momentum(history, cfg, alpha: float = 0.15) -> dict[int, float]:
    ewma = {n: 0.0 for n in _nums(cfg)}
    for draw in history:
        drawn = set(draw)
        for n in _nums(cfg):
            ewma[n] = alpha * (1.0 if n in drawn else 0.0) + (1 - alpha) * ewma[n]
    # shift so nothing is exactly zero
    return _normalize({n: v + 1e-4 for n, v in ewma.items()})


def m_hot_streak(history, cfg, window: int = 15) -> dict[int, float]:
    recent = history[-window:] if history else []
    counts = {n: 0.0 for n in _nums(cfg)}
    for draw in recent:
        for x in draw:
            if 1 <= x <= cfg.max_number:
                counts[x] += 1.0
    return _normalize({n: v + 1e-3 for n, v in counts.items()})


def m_zone_pressure(history, cfg, zones: int = 4, window: int = 20) -> dict[int, float]:
    recent = history[-window:] if history else []
    max_n = cfg.max_number
    size = max_n / zones
    observed = [0.0] * zones
    for draw in recent:
        for x in draw:
            if 1 <= x <= max_n:
                z = min(zones - 1, int((x - 1) // size))
                observed[z] += 1
    total = sum(observed) or 1.0
    expected = total / zones
    # zones with a deficit (under-represented) get more pressure
    deficit = [max(0.0, expected - observed[z]) + 0.1 for z in range(zones)]
    probs = {}
    for n in _nums(cfg):
        z = min(zones - 1, int((n - 1) // size))
        probs[n] = deficit[z]
    return _normalize(probs)


MODELS = {
    "bayes_decay": m_bayes_decay,
    "markov": m_markov,
    "gap_hazard": m_gap_hazard,
    "cooccurrence": m_cooccurrence,
    "momentum": m_momentum,
    "hot_streak": m_hot_streak,
    "zone_pressure": m_zone_pressure,
}
MODEL_KEYS = list(MODELS.keys())

MODEL_LABELS = {
    "bayes_decay": "Bayesiano (decay)",
    "markov": "Markov (orden 1)",
    "gap_hazard": "Atraso (hazard)",
    "cooccurrence": "Co-ocurrencia",
    "momentum": "Momentum (EWMA)",
    "hot_streak": "Racha caliente",
    "zone_pressure": "Presión por zona",
}


def _topk_for(cfg: GameConfig) -> int:
    return max(cfg.pick + 2, round(cfg.max_number * 0.27))


def all_model_probabilities(history, cfg) -> dict[str, dict[int, float]]:
    return {k: fn(history, cfg) for k, fn in MODELS.items()}


def walk_forward_scores(history, cfg, window: int = 80) -> dict[str, float]:
    """Hit-rate of each model's top-k over the last `window` draws (no look-ahead)."""
    n = len(history)
    start = max(30, n - window)
    if start >= n:
        return {k: 1.0 / len(MODELS) for k in MODELS}
    topk = _topk_for(cfg)
    hits = {k: 0.0 for k in MODELS}
    trials = 0
    for t in range(start, n):
        train = history[:t]
        actual = set(history[t])
        for k, fn in MODELS.items():
            probs = fn(train, cfg)
            top = set(n for n, _ in nlargest(topk, probs.items(), key=lambda kv: kv[1]))
            hits[k] += len(actual & top)
        trials += len(actual)
    return {k: hits[k] / max(1, trials) for k in MODELS}


def evolve_weights(scores: dict[str, float], temperature: float = 50.0, floor: float = 0.03) -> dict[str, float]:
    """Softmax of model scores (sharp), with a diversity floor."""
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


# in-memory cache so /ml/probabilities?source=ensemble is cheap between draws
_ENS_CACHE: dict[str, dict] = {}


def compute_weights(history, cfg, force: bool = False) -> dict:
    """Walk-forward scores + evolved weights, cached per (game, history length)."""
    key = cfg.key
    cached = _ENS_CACHE.get(key)
    if cached and not force and cached.get("n_draws") == len(history):
        return cached
    scores = walk_forward_scores(history, cfg)
    weights = evolve_weights(scores)
    out = {"weights": weights, "scores": scores, "n_draws": len(history)}
    _ENS_CACHE[key] = out
    return out


def fused_probabilities(history, cfg, weights: dict[str, float] | None = None,
                        ml_probs: dict[int, float] | None = None, ml_blend: float = 0.5) -> dict[int, float]:
    """Weighted fusion of the base models, optionally blended 50/50 with the
    existing XGBoost/GradientBoosting per-number model (the prior MelateIA model
    becomes one more voice in the ensemble)."""
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
