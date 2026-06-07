"""Context (regime) detection for the contextual bandit.

The reinforcement learner tracks each strategy's performance *per regime*, so the
adaptive strategy can route to whatever has worked best in the current regime
instead of a single global winner. The regime is a coarse, stable bucket derived
from the recent draws — deliberately simple to avoid sparse buckets.
"""
from __future__ import annotations

from .features import GameStats


def regime(stats: GameStats) -> str:
    """Return a coarse regime label based on the most recent draw's sum vs the
    historical terciles: "sum-low" | "sum-mid" | "sum-high"."""
    draws = stats.draws
    if not draws or len(draws) < 12:
        return "sum-mid"
    sums = sorted(sum(d) for d in draws)
    n = len(sums)
    t1 = sums[n // 3]
    t2 = sums[2 * n // 3]
    last = sum(draws[-1])
    if last <= t1:
        return "sum-low"
    if last >= t2:
        return "sum-high"
    return "sum-mid"
