"""Heuristic & genetic combination generator.

Pipeline:
  1. Sample a large pool of candidate combinations using strategy-biased weights.
  2. Score every candidate with the symbolic engine (+ optional ML signal).
  3. For genetic strategies: evolve the pool with crossover + mutation.
  4. Select a diverse top-k (combinations must differ enough from each other).
"""
from __future__ import annotations

import random

from .features import GameStats
from .strategies import STRATEGIES, build_profile, biased_weights
from .symbolic import score_combination, hard_valid, explain


def _weighted_sample(weights: dict[int, float], k: int, temperature: float) -> list[int]:
    nums = list(weights.keys())
    # temperature reshapes the distribution: >1 flatter (more random), <1 peakier
    w = [max(1e-6, weights[n]) ** (1.0 / max(0.05, temperature)) for n in nums]
    chosen: set[int] = set()
    pool = list(zip(nums, w))
    while len(chosen) < k and pool:
        total = sum(x[1] for x in pool)
        r = random.uniform(0, total)
        acc = 0.0
        for i, (n, wi) in enumerate(pool):
            acc += wi
            if acc >= r:
                chosen.add(n)
                pool.pop(i)
                break
    return sorted(chosen)


def _mutate(combo: list[int], weights: dict[int, float], max_number: int) -> list[int]:
    c = set(combo)
    # drop the weakest-weighted number, add a new sampled one
    weakest = min(c, key=lambda n: weights.get(n, 0))
    c.discard(weakest)
    candidates = [n for n in range(1, max_number + 1) if n not in c]
    w = [weights.get(n, 1e-4) for n in candidates]
    total = sum(w)
    r = random.uniform(0, total)
    acc = 0.0
    for n, wi in zip(candidates, w):
        acc += wi
        if acc >= r:
            c.add(n)
            break
    if len(c) < len(combo):  # safety
        c.add(random.choice(candidates))
    return sorted(c)


def _crossover(a: list[int], b: list[int], max_number: int, pick: int) -> list[int]:
    pool = list(dict.fromkeys(a + b))
    random.shuffle(pool)
    child = sorted(pool[:pick])
    while len(child) < pick:
        n = random.randint(1, max_number)
        if n not in child:
            child.append(n)
    return sorted(child)


def _diverse_select(scored: list[tuple], k: int, min_diff: int = 2) -> list[tuple]:
    """Greedily pick top combos that differ from already-selected ones."""
    selected: list[tuple] = []
    for combo, score, comps in scored:
        cs = set(combo)
        if all(len(cs & set(s[0])) <= len(combo) - min_diff for s in selected):
            selected.append((combo, score, comps))
        if len(selected) >= k:
            break
    # fallback: if diversity filter was too strict, pad with best remaining
    if len(selected) < k:
        for item in scored:
            if item not in selected:
                selected.append(item)
            if len(selected) >= k:
                break
    return selected[:k]


def generate(
    stats: GameStats,
    strategy: str,
    count: int,
    ml_scorer=None,
    pool_size: int = 1200,
    seed: int | None = None,
    genius_probs: dict[int, float] | None = None,
    genius_blend: float = 0.35,
) -> list[dict]:
    if seed is not None:
        random.seed(seed)
    cfg = STRATEGIES.get(strategy, STRATEGIES["balanceada"])
    profile = build_profile(strategy, stats)
    weights = biased_weights(strategy, stats)
    if genius_probs:
        # Genius backbone: geometric blend of the strategy's own bias with the
        # fused Genius distribution, so every strategy leans on the engine.
        tot = sum(weights.values()) or 1.0
        b = genius_blend
        weights = {
            n: ((weights[n] / tot) ** (1 - b)) * (max(genius_probs.get(n, 0.0), 1e-9) ** b)
            for n in weights
        }
    temperature = cfg.get("temperature", 1.0)
    pick = stats.pick

    def fitness(combo):
        s, comps = score_combination(combo, stats, profile)
        if ml_scorer is not None and cfg.get("use_ml"):
            ml = ml_scorer(combo)  # 0..1
            s = 0.7 * s + 0.3 * ml
            comps["ml"] = round(ml, 4)
        return s, comps

    # 1. initial pool
    pool: dict[tuple, tuple] = {}
    attempts = 0
    while len(pool) < pool_size and attempts < pool_size * 4:
        attempts += 1
        combo = _weighted_sample(weights, pick, temperature)
        if not hard_valid(combo, stats):
            continue
        key = tuple(combo)
        if key not in pool:
            s, comps = fitness(combo)
            pool[key] = (combo, s, comps)

    scored = sorted(pool.values(), key=lambda x: x[1], reverse=True)

    # 2. genetic refinement
    if cfg.get("genetic"):
        generations = 6
        elite = [list(x[0]) for x in scored[: max(20, count * 4)]]
        for _ in range(generations):
            children = []
            for _ in range(len(elite)):
                a, b = random.sample(elite, 2)
                child = _crossover(a, b, stats.max_number, pick)
                if random.random() < 0.6:
                    child = _mutate(child, weights, stats.max_number)
                if hard_valid(child, stats):
                    children.append(child)
            combined = {tuple(c): c for c in elite + children}
            rescored = []
            for combo in combined.values():
                s, comps = fitness(combo)
                rescored.append((combo, s, comps))
            rescored.sort(key=lambda x: x[1], reverse=True)
            elite = [list(x[0]) for x in rescored[: max(20, count * 4)]]
            scored = rescored

    # 3. diverse selection
    chosen = _diverse_select(scored, count, min_diff=2)

    results = []
    label = cfg.get("label", strategy)
    for combo, score, comps in chosen:
        from .features import combination_features
        results.append({
            "numbers": combo,
            "score": round(float(score), 4),
            "explanation": explain(combo, stats, comps, label),
            "strategy": strategy,
            "features": combination_features(combo, stats),
        })
    return results
