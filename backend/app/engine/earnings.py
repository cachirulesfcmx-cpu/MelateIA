"""Earnings / probability estimator.

Computes theoretical probabilities via the hypergeometric distribution (no ML —
pure combinatorics) and builds an ROI scenario table. All numbers are clearly
framed as estimates, never guarantees.
"""
from __future__ import annotations

from math import comb

from .game_config import get_game
from .backtesting import PRIZE_PROXY


def hypergeom_prob(max_number: int, pick: int, hits: int) -> float:
    """P(exactly `hits` of our `pick` numbers match the `pick` drawn balls)."""
    total = comb(max_number, pick)
    favorable = comb(pick, hits) * comb(max_number - pick, pick - hits)
    return favorable / total


def estimate(game_type: str, combinations: int, cost_per_combination: float, custom_prizes: dict | None):
    cfg = get_game(game_type)
    prizes = dict(PRIZE_PROXY.get(cfg.key, PRIZE_PROXY["melate"]))
    if custom_prizes:
        for k, v in custom_prizes.items():
            try:
                prizes[int(k)] = float(v)
            except (ValueError, TypeError):
                continue

    total_cost = round(combinations * cost_per_combination, 2)

    scenarios = []
    for hits in range(2, cfg.pick + 1):
        p_single = hypergeom_prob(cfg.max_number, cfg.pick, hits)
        # probability at least one of N combinations achieves this tier
        p_any = 1 - (1 - p_single) ** combinations
        prize = prizes.get(hits, 0)
        expected_value = p_single * prize * combinations
        odds = round(1 / p_single) if p_single > 0 else None
        scenarios.append({
            "hits": hits,
            "probability_single": p_single,
            "odds_one_in": odds,
            "probability_any_in_set": round(p_any, 8),
            "prize_estimate": prize,
            "expected_return": round(expected_value, 2),
            "net_if_hit": round(prize - total_cost, 2),
            "roi_if_hit_percent": round((prize - total_cost) / total_cost * 100, 1) if total_cost else None,
        })

    expected_total_return = round(sum(s["expected_return"] for s in scenarios), 2)
    expected_roi = round((expected_total_return - total_cost) / total_cost * 100, 2) if total_cost else None

    # risk classification based on expected value vs cost
    if expected_roi is None:
        risk = "Indefinido"
    elif expected_roi > -50:
        risk = "Alto (esperanza matemática negativa, típico de lotería)"
    elif expected_roi > -90:
        risk = "Muy alto"
    else:
        risk = "Extremo"

    jackpot_prob_any = 1 - (1 - hypergeom_prob(cfg.max_number, cfg.pick, cfg.pick)) ** combinations

    return {
        "game_type": cfg.key,
        "game_label": cfg.label,
        "combinations": combinations,
        "cost_per_combination": cost_per_combination,
        "total_cost": total_cost,
        "scenarios": scenarios,
        "expected_total_return": expected_total_return,
        "expected_roi_percent": expected_roi,
        "jackpot_probability": hypergeom_prob(cfg.max_number, cfg.pick, cfg.pick),
        "jackpot_probability_any": jackpot_prob_any,
        "jackpot_odds_one_in": round(1 / hypergeom_prob(cfg.max_number, cfg.pick, cfg.pick)),
        "risk": risk,
        "disclaimer": (
            "Estimación NO garantizada. Melate es un juego de azar; ninguna IA puede "
            "garantizar premios. La esperanza matemática de la lotería es negativa."
        ),
    }
