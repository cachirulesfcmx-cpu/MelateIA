"""Feature engineering & historical statistics for a single game.

Consumes the chronological list of historical draws (each a sorted list of the
6 main numbers, ordered OLDEST -> NEWEST) and exposes:

  - frequency (global + recent windows 10/25/50/100)
  - gaps since last appearance ("atraso")
  - hot / cold rankings
  - per-number probability weights used by the generators
  - combination-level features (sum, range, odd/even, primes, consecutive...)
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97}


def is_prime(n: int) -> bool:
    return n in PRIMES


@dataclass
class GameStats:
    max_number: int
    draws: list[list[int]]  # oldest -> newest
    pick: int = 6

    # computed
    frequency: dict = field(default_factory=dict)
    recent: dict = field(default_factory=dict)  # window -> {num: count}
    gaps: dict = field(default_factory=dict)     # num -> draws since last seen
    pair_freq: dict = field(default_factory=dict)
    last_draw: list = field(default_factory=list)

    def __post_init__(self):
        self._compute()

    def _compute(self):
        n = self.max_number
        self.frequency = {i: 0 for i in range(1, n + 1)}
        last_seen = {i: None for i in range(1, n + 1)}
        windows = [10, 25, 50, 100]
        self.recent = {w: {i: 0 for i in range(1, n + 1)} for w in windows}
        self.pair_freq = defaultdict(int)

        total = len(self.draws)
        for idx, draw in enumerate(self.draws):
            for num in draw:
                if 1 <= num <= n:
                    self.frequency[num] += 1
                    last_seen[num] = idx
            sd = sorted(draw)
            for a in range(len(sd)):
                for b in range(a + 1, len(sd)):
                    self.pair_freq[(sd[a], sd[b])] += 1

        # recent windows
        for w in windows:
            for draw in self.draws[-w:]:
                for num in draw:
                    if 1 <= num <= n:
                        self.recent[w][num] += 1

        # gaps: how many draws ago each number last appeared (large = overdue)
        self.gaps = {}
        for i in range(1, n + 1):
            self.gaps[i] = (total - 1 - last_seen[i]) if last_seen[i] is not None else total

        self.last_draw = self.draws[-1] if self.draws else []

    # ---------- rankings ----------
    def hot_numbers(self, window: int = 50, k: int | None = None) -> list[int]:
        ref = self.recent.get(window, self.frequency)
        ranked = sorted(range(1, self.max_number + 1), key=lambda x: ref[x], reverse=True)
        return ranked[:k] if k else ranked

    def cold_numbers(self, window: int = 50, k: int | None = None) -> list[int]:
        ref = self.recent.get(window, self.frequency)
        ranked = sorted(range(1, self.max_number + 1), key=lambda x: (ref[x], -self.gaps[x]))
        return ranked[:k] if k else ranked

    def overdue_numbers(self, k: int | None = None) -> list[int]:
        ranked = sorted(range(1, self.max_number + 1), key=lambda x: self.gaps[x], reverse=True)
        return ranked[:k] if k else ranked

    def number_weights(self, recency_bias: float = 0.5) -> dict[int, float]:
        """Blend global frequency with recent frequency to produce sampling weights."""
        total_draws = max(1, len(self.draws))
        weights = {}
        rec = self.recent[50]
        rec_total = max(1, sum(rec.values()))
        glob_total = max(1, sum(self.frequency.values()))
        for i in range(1, self.max_number + 1):
            g = self.frequency[i] / glob_total
            r = rec[i] / rec_total
            base = (1 - recency_bias) * g + recency_bias * r
            weights[i] = base + 1e-4  # smoothing so nothing is impossible
        return weights

    # ---------- popularity penalty ----------
    def popularity_score(self, numbers: list[int]) -> float:
        """0 = unpopular/contrarian, 1 = very 'human' / commonly played combo.

        Humans over-pick low numbers (calendar/birthdays <= 31), arithmetic
        sequences and clustered numbers. We approximate that bias.
        """
        score = 0.0
        low = sum(1 for x in numbers if x <= 31)
        score += (low / len(numbers)) * 0.5
        # consecutive runs
        sd = sorted(numbers)
        consec = sum(1 for i in range(len(sd) - 1) if sd[i + 1] - sd[i] == 1)
        score += min(consec, 4) / 4 * 0.3
        # tight clustering (small range = more "patterned")
        rng = sd[-1] - sd[0]
        score += max(0.0, (self.max_number - rng) / self.max_number) * 0.2
        return min(1.0, score)


def combination_features(numbers: list[int], stats: GameStats) -> dict:
    sd = sorted(numbers)
    odd = sum(1 for x in sd if x % 2 == 1)
    primes = sum(1 for x in sd if is_prime(x))
    consec = sum(1 for i in range(len(sd) - 1) if sd[i + 1] - sd[i] == 1)
    total = sum(sd)
    rng = sd[-1] - sd[0]
    mean = total / len(sd)
    variance = sum((x - mean) ** 2 for x in sd) / len(sd)
    # range buckets (terciles of the number space)
    third = stats.max_number / 3
    low = sum(1 for x in sd if x <= third)
    mid = sum(1 for x in sd if third < x <= 2 * third)
    high = sum(1 for x in sd if x > 2 * third)
    repeats = len(set(sd) & set(stats.last_draw))
    avg_gap = sum(stats.gaps[x] for x in sd) / len(sd)
    return {
        "sum": total,
        "range": rng,
        "mean": round(mean, 2),
        "std": round(math.sqrt(variance), 2),
        "odd": odd,
        "even": len(sd) - odd,
        "primes": primes,
        "consecutive": consec,
        "low": low,
        "mid": mid,
        "high": high,
        "repeats_last": repeats,
        "avg_gap": round(avg_gap, 1),
        "popularity": round(stats.popularity_score(sd), 3),
    }
