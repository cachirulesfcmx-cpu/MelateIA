"""Positional game engine (Tris).

Tris is fundamentally different from the lottery (Melate/Chispazo) games:
each draw is a SEQUENCE of `pick` digits (0..9) where REPETITIONS are allowed
and the POSITION matters. A play matches per-position — "1,2,3,4,5" against a
draw of "1,9,3,9,5" scores 3 hits (positions 1, 3 and 5), not 5.

This module is fully self-contained so the combination-game code paths
(Melate, Revancha, Chispazo, …) are never touched by it. All statistics,
generation, scoring and evaluation here are per-position.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict

from .game_config import GameConfig


class PositionalStats:
    """Per-position digit statistics over the chronological draw history."""

    def __init__(self, cfg: GameConfig, draws: list[list[int]]):
        self.cfg = cfg
        self.length = cfg.pick
        self.lo = cfg.min_number
        self.hi = cfg.max_number
        self.digits = list(range(self.lo, self.hi + 1))
        self.draws = [d for d in draws if len(d) == self.length]
        self.total = len(self.draws)
        self._compute()

    def _compute(self):
        L, total = self.length, self.total
        # per-position global frequency
        self.pos_freq = [defaultdict(int) for _ in range(L)]
        # per-position recent frequency (last 50)
        self.pos_recent = [defaultdict(int) for _ in range(L)]
        # gaps: per position, draws since the digit last appeared there
        last_seen = [defaultdict(lambda: None) for _ in range(L)]
        self.digit_freq = defaultdict(int)  # ignoring position
        for idx, draw in enumerate(self.draws):
            for i, d in enumerate(draw):
                self.pos_freq[i][d] += 1
                self.digit_freq[d] += 1
                last_seen[i][d] = idx
        window = 50
        for draw in self.draws[-window:]:
            for i, d in enumerate(draw):
                self.pos_recent[i][d] += 1
        self.pos_gaps = [dict() for _ in range(L)]
        for i in range(L):
            for d in self.digits:
                ls = last_seen[i].get(d)
                self.pos_gaps[i][d] = (total - 1 - ls) if ls is not None else total
        self.last_draw = self.draws[-1] if self.draws else []

    # ---------- per-position distributions ----------
    def position_prob(self, i: int, recency: float = 0.4) -> dict[int, float]:
        """Smoothed probability distribution of each digit at position `i`."""
        gtot = max(1, sum(self.pos_freq[i].values()))
        rtot = max(1, sum(self.pos_recent[i].values()))
        out = {}
        for d in self.digits:
            g = self.pos_freq[i].get(d, 0) / gtot
            r = self.pos_recent[i].get(d, 0) / rtot
            out[d] = (1 - recency) * g + recency * r + 1e-3
        s = sum(out.values())
        return {d: v / s for d, v in out.items()}

    def position_weights(self, i: int, prefer: str, recency: float) -> dict[int, float]:
        """Sampling weights at position `i` shaped by the strategy preference."""
        prob = self.position_prob(i, recency)
        max_gap = max(1, max(self.pos_gaps[i].values()))
        out = {}
        for d in self.digits:
            v = prob[d]
            gap_factor = self.pos_gaps[i][d] / max_gap
            if prefer == "cold":
                v = v * 0.35 + gap_factor * 0.9
            elif prefer == "hot":
                v = v * 1.5
            elif prefer == "contrarian":
                v = (1.0 / (v + 1e-3)) * 0.001 + 0.05
            out[d] = max(v, 1e-4)
        return out


# strategy -> (prefer, temperature, recency)
_STRAT_MAP = {
    "conservadora": ("hot", 0.45, 0.3),
    "balanceada": ("balanced", 1.0, 0.4),
    "agresiva": ("contrarian", 1.5, 0.6),
    "genetica": ("balanced", 1.2, 0.5),
    "anti_popular": ("contrarian", 1.3, 0.45),
    "calientes": ("hot", 0.4, 0.8),
    "frios": ("cold", 0.7, 0.5),
    "hibrida": ("balanced", 1.0, 0.5),
    "adaptativa": ("balanced", 1.0, 0.5),
}


def _sample_digit(weights: dict[int, float], temperature: float) -> int:
    items = list(weights.items())
    w = [max(1e-6, v) ** (1.0 / max(0.05, temperature)) for _, v in items]
    total = sum(w)
    r = random.uniform(0, total)
    acc = 0.0
    for (d, _), wi in zip(items, w):
        acc += wi
        if acc >= r:
            return d
    return items[-1][0]


def pos_features(numbers: list[int]) -> dict:
    odd = sum(1 for x in numbers if x % 2 == 1)
    total = sum(numbers)
    return {
        "sum": total,
        "odd": odd,
        "even": len(numbers) - odd,
        "distinct": len(set(numbers)),
        "repeats": len(numbers) - len(set(numbers)),
        "max_digit": max(numbers),
        "min_digit": min(numbers),
    }


def pos_score(numbers: list[int], stats: PositionalStats) -> tuple[float, dict]:
    """Score a play 0..1 as the mean per-position probability, normalised by the
    best achievable per-position probability."""
    if not stats.total:
        return 0.5, {}
    comps = {}
    rels = []
    for i, d in enumerate(numbers):
        prob = stats.position_prob(i)
        best = max(prob.values()) or 1.0
        rel = prob.get(d, 0.0) / best
        rels.append(rel)
        comps[f"pos{i + 1}"] = round(prob.get(d, 0.0), 4)
    score = sum(rels) / len(rels) if rels else 0.5
    return round(min(1.0, max(0.0, score)), 4), comps


def pos_explain(numbers: list[int], stats: PositionalStats, strategy_label: str) -> str:
    bits = []
    for i, d in enumerate(numbers):
        prob = stats.position_prob(i)
        rank = sorted(stats.digits, key=lambda x: prob[x], reverse=True).index(d) + 1
        bits.append(f"P{i + 1}:{d}(#{rank})")
    return (
        f"{strategy_label} · jugada posicional {'-'.join(map(str, numbers))}. "
        f"Cada dígito se elige por su distribución histórica en esa posición exacta "
        f"[{', '.join(bits)}]. En Tris la posición importa: el orden cuenta."
    )


def pos_generate(stats: PositionalStats, strategy: str, count: int, seed: int | None = None) -> list[dict]:
    if seed is not None:
        random.seed(seed)
    prefer, temperature, recency = _STRAT_MAP.get(strategy, _STRAT_MAP["balanceada"])
    label = strategy.replace("_", " ").capitalize()
    weights = [stats.position_weights(i, prefer, recency) for i in range(stats.length)]

    seen: set[tuple] = set()
    out = []
    attempts = 0
    # first play for "peaky" strategies = argmax per position (deterministic best)
    deterministic = prefer in ("hot",) and temperature <= 0.5
    while len(out) < count and attempts < count * 40:
        attempts += 1
        if deterministic and not out:
            play = [max(weights[i], key=weights[i].get) for i in range(stats.length)]
        else:
            play = [_sample_digit(weights[i], temperature) for i in range(stats.length)]
        key = tuple(play)
        if key in seen:
            continue
        seen.add(key)
        score, comps = pos_score(play, stats)
        out.append({
            "numbers": play,
            "score": score,
            "explanation": pos_explain(play, stats, label),
            "strategy": strategy,
            "features": pos_features(play),
        })
    out.sort(key=lambda c: c["score"], reverse=True)
    return out[:count]


def pos_evaluate(pred_numbers: list[int], draw_numbers: list[int]) -> tuple[int, list[int], list[int]]:
    """Per-position comparison. Returns (hits, matched_digits, missed_digits)."""
    matched, missed = [], []
    n = min(len(pred_numbers), len(draw_numbers))
    for i in range(n):
        if pred_numbers[i] == draw_numbers[i]:
            matched.append(pred_numbers[i])
        else:
            missed.append(pred_numbers[i])
    # any extra predicted positions count as missed
    for i in range(n, len(pred_numbers)):
        missed.append(pred_numbers[i])
    return len(matched), matched, missed


def pos_regime(stats: PositionalStats) -> str:
    """Coarse regime for the contextual bandit, based on the last draw's parity
    of the digit sum — deliberately simple to avoid sparse buckets."""
    if not stats.last_draw:
        return "even-sum"
    return "even-sum" if sum(stats.last_draw) % 2 == 0 else "odd-sum"


def pos_probabilities(stats: PositionalStats) -> dict:
    """Per-position digit probability grid for the analytics heatmap."""
    grid = []
    for i in range(stats.length):
        prob = stats.position_prob(i)
        mx = max(prob.values()) or 1.0
        digits = [
            {"digit": d, "prob": round(prob[d], 4), "rel": round(prob[d] / mx, 3)}
            for d in stats.digits
        ]
        top = max(stats.digits, key=lambda d: prob[d])
        grid.append({"position": i + 1, "digits": digits, "top": top})
    return {"length": stats.length, "lo": stats.lo, "hi": stats.hi, "positions": grid}


_POS_PRIZE = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}  # ROI proxy unused for positional backtest


def run_positional_backtest(cfg, all_draws, strategy, last_n, combos_per_draw, cost_per_combination) -> dict:
    """Replay a positional strategy over the last N draws with no look-ahead."""
    from collections import Counter
    ordered = sorted(all_draws, key=lambda d: d["draw_number"] or 0)
    sequences = [d["numbers"] for d in ordered]
    n = len(sequences)
    if n < last_n + 30:
        last_n = max(5, n - 30)
    if last_n <= 0:
        return {"error": "Historial insuficiente para backtesting."}

    pick = cfg.pick
    base = cfg.max_number - cfg.min_number + 1
    hit_counter: Counter = Counter()
    random_counter: Counter = Counter()
    per_draw = []
    best, worst, total_hits = 0, pick, 0
    start = n - last_n
    for i in range(start, n):
        history = sequences[:i]
        actual = sequences[i]
        stats = PositionalStats(cfg, history)
        combos = pos_generate(stats, strategy, combos_per_draw)
        draw_best = 0
        for c in combos:
            h, _, _ = pos_evaluate(c["numbers"], actual)
            hit_counter[h] += 1
            total_hits += h
            draw_best = max(draw_best, h)
            rc = [random.randint(cfg.min_number, cfg.max_number) for _ in range(pick)]
            rh, _, _ = pos_evaluate(rc, actual)
            random_counter[rh] += 1
        best = max(best, draw_best)
        worst = min(worst, draw_best)
        per_draw.append({"draw_number": ordered[i]["draw_number"], "actual": actual, "best_hits": draw_best})

    total_combos = sum(hit_counter.values())
    avg = round(total_hits / max(1, total_combos), 3)
    rand_avg = round(sum(k * v for k, v in random_counter.items()) / max(1, sum(random_counter.values())), 3)
    total_spent = round(total_combos * cost_per_combination, 2)
    return {
        "game_type": cfg.key,
        "strategy": strategy,
        "draws_tested": last_n,
        "combos_per_draw": combos_per_draw,
        "total_combinations": total_combos,
        "average_hits": avg,
        "best_hits": best,
        "worst_hits": worst,
        "distribution": {str(k): hit_counter.get(k, 0) for k in range(pick + 1)},
        "random_average_hits": rand_avg,
        "random_distribution": {str(k): random_counter.get(k, 0) for k in range(pick + 1)},
        "edge_vs_random": round(avg - rand_avg, 3),
        "simulated": {"total_spent": total_spent, "total_won": 0.0, "roi_percent": 0.0, "random_roi_percent": 0.0},
        "recent_draws": per_draw[-15:],
    }


def pos_earnings(cfg: GameConfig, combinations: int, cost_per_combination: float, prizes: dict | None) -> dict:
    """Positional probability: each position is an independent 1/base chance.
    P(exactly k of `pick` positions correct) = C(pick,k) p^k (1-p)^(pick-k),
    with p = 1 / (number of digits)."""
    base = cfg.max_number - cfg.min_number + 1
    p = 1.0 / base
    pick = cfg.pick
    default_prizes = {1: 2.5, 2: 10.0, 3: 50.0, 4: 500.0, 5: 5000.0}
    prize_tbl = dict(default_prizes)
    if prizes:
        for k, v in prizes.items():
            try:
                prize_tbl[int(k)] = float(v)
            except (ValueError, TypeError):
                continue
    total_cost = round(combinations * cost_per_combination, 2)
    scenarios = []
    for hits in range(1, pick + 1):
        p_single = math.comb(pick, hits) * (p ** hits) * ((1 - p) ** (pick - hits))
        p_any = 1 - (1 - p_single) ** combinations
        prize = prize_tbl.get(hits, 0)
        ev = p_single * prize * combinations
        scenarios.append({
            "hits": hits,
            "probability_single": p_single,
            "odds_one_in": round(1 / p_single) if p_single > 0 else None,
            "probability_any_in_set": round(p_any, 8),
            "prize_estimate": prize,
            "expected_return": round(ev, 2),
            "net_if_hit": round(prize - total_cost, 2),
            "roi_if_hit_percent": round((prize - total_cost) / total_cost * 100, 1) if total_cost else None,
        })
    expected_total = round(sum(s["expected_return"] for s in scenarios), 2)
    expected_roi = round((expected_total - total_cost) / total_cost * 100, 2) if total_cost else None
    p_jackpot = p ** pick
    return {
        "game_type": cfg.key,
        "game_label": cfg.label,
        "combinations": combinations,
        "cost_per_combination": cost_per_combination,
        "total_cost": total_cost,
        "scenarios": scenarios,
        "expected_total_return": expected_total,
        "expected_roi_percent": expected_roi,
        "jackpot_probability": p_jackpot,
        "jackpot_probability_any": 1 - (1 - p_jackpot) ** combinations,
        "jackpot_odds_one_in": round(1 / p_jackpot),
        "risk": "Alto (esperanza matemática negativa, típico de lotería)" if (expected_roi or -100) > -90 else "Muy alto",
        "disclaimer": (
            "Estimación NO garantizada. Tris es un juego de azar; cada posición es "
            "independiente (1 en {0}). Ninguna IA puede garantizar premios.".format(base)
        ),
    }
