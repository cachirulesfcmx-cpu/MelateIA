"""Backtesting: replay a strategy over the last N historical draws.

For each of the last N draws we build statistics using ONLY the draws that
preceded it (no look-ahead), generate combinations with the chosen strategy, and
count hits against the real outcome. Reports the hit distribution, best/worst/avg
and a simulated ROI versus pure random play.
"""
from __future__ import annotations

import random
from collections import Counter

from .features import GameStats
from .game_config import GameConfig
from .generator import generate
from .models_ml import NumberModel

# Approximate Mexican lottery secondary-prize payouts (MXN) per ticket.
# Headline jackpot (6) is variable; we use a conservative fixed proxy for ROI.
PRIZE_PROXY = {
    "melate": {2: 0, 3: 47, 4: 600, 5: 12000, 6: 5_000_000},
    "revancha": {2: 0, 3: 40, 4: 500, 5: 10000, 6: 3_000_000},
    "melate_retro": {2: 0, 3: 35, 4: 450, 5: 9000, 6: 2_000_000},
    "revanchita": {2: 0, 3: 38, 4: 480, 5: 9500, 6: 2_500_000},
    "chispazo": {2: 0, 3: 18, 4: 300, 5: 200_000},
}


def _hits(combo: list[int], actual: list[int]) -> int:
    return len(set(combo) & set(actual))


def run_backtest(
    cfg: GameConfig,
    all_draws: list[dict],  # oldest->newest, each {draw_number, numbers}
    strategy: str,
    last_n: int,
    combos_per_draw: int,
    cost_per_combination: float,
) -> dict:
    ordered = sorted(all_draws, key=lambda d: d["draw_number"] or 0)
    sequences = [d["numbers"] for d in ordered]
    n = len(sequences)
    if n < last_n + 30:
        last_n = max(5, n - 30)
    if last_n <= 0:
        return {"error": "Historial insuficiente para backtesting."}

    prizes = PRIZE_PROXY.get(cfg.key, PRIZE_PROXY["melate"])

    hit_counter: Counter = Counter()
    random_counter: Counter = Counter()
    per_draw = []
    best = 0
    worst = cfg.pick
    total_hits = 0
    total_spent = 0.0
    total_won = 0.0
    rand_won = 0.0

    start = n - last_n
    for i in range(start, n):
        history = sequences[:i]
        actual = sequences[i]
        stats = GameStats(max_number=cfg.max_number, draws=history, pick=cfg.pick)
        # lightweight: heuristic model scorer (no heavy retrain per step)
        model = NumberModel(cfg.max_number)
        scorer = model.make_scorer(history)
        combos = generate(stats, strategy, combos_per_draw, ml_scorer=scorer, pool_size=400)

        draw_best = 0
        for c in combos:
            h = _hits(c["numbers"], actual)
            hit_counter[h] += 1
            total_hits += h
            total_spent += cost_per_combination
            total_won += prizes.get(h, 0)
            draw_best = max(draw_best, h)
            # random baseline
            rc = random.sample(range(1, cfg.max_number + 1), cfg.pick)
            rh = _hits(rc, actual)
            random_counter[rh] += 1
            rand_won += prizes.get(rh, 0)

        best = max(best, draw_best)
        worst = min(worst, draw_best)
        per_draw.append({
            "draw_number": ordered[i]["draw_number"],
            "actual": actual,
            "best_hits": draw_best,
        })

    total_combos = sum(hit_counter.values())
    avg = round(total_hits / max(1, total_combos), 3)
    rand_avg = round(
        sum(k * v for k, v in random_counter.items()) / max(1, sum(random_counter.values())), 3
    )
    roi = round((total_won - total_spent) / total_spent * 100, 2) if total_spent else 0.0
    rand_roi = round((rand_won - total_spent) / total_spent * 100, 2) if total_spent else 0.0

    return {
        "game_type": cfg.key,
        "strategy": strategy,
        "draws_tested": last_n,
        "combos_per_draw": combos_per_draw,
        "total_combinations": total_combos,
        "average_hits": avg,
        "best_hits": best,
        "worst_hits": worst,
        "distribution": {str(k): hit_counter.get(k, 0) for k in range(cfg.pick + 1)},
        "random_average_hits": rand_avg,
        "random_distribution": {str(k): random_counter.get(k, 0) for k in range(cfg.pick + 1)},
        "edge_vs_random": round(avg - rand_avg, 3),
        "simulated": {
            "total_spent": round(total_spent, 2),
            "total_won": round(total_won, 2),
            "roi_percent": roi,
            "random_roi_percent": rand_roi,
        },
        "recent_draws": per_draw[-15:],
    }
