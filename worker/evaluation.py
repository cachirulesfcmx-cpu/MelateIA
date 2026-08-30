"""Honest evaluation of a challenger's predictions.

The metric that matters is how many numbers a top-k ticket actually hits,
compared against the EXACT random baseline. Two independent base-rate warnings
are computed, because a network can fail in two different ways:

  * `close_to_base_rate` — its hits sit at the level pure chance produces.
  * `flat_predictions`   — its outputs barely vary between numbers, i.e. it
    learned the global frequency and nothing else. This one catches a model
    whose hits happen to look good on a small validation slice.
"""
from __future__ import annotations

import numpy as np


def theoretical_random_mean_hits(max_number: int, k: int = 6) -> float:
    return (k * k) / max_number


def topk_numbers(scores, k: int = 6, min_number: int = 1) -> set[int]:
    idx = np.argsort(np.asarray(scores, dtype=float))[-k:]
    return {int(i) + min_number for i in idx}


def hit_rate(predictions, actuals, k: int = 6, min_number: int = 1) -> float:
    """Mean hits of the top-k ticket. `actuals` may be number lists or 0/1 rows."""
    vals = []
    for s, a in zip(predictions, actuals):
        arr = np.asarray(a)
        if arr.ndim == 1 and arr.size and set(np.unique(arr).tolist()) <= {0.0, 1.0} and arr.size > k:
            actual_set = {int(i) + min_number for i in np.nonzero(arr)[0]}
        else:
            actual_set = {int(v) for v in np.asarray(a).ravel().tolist()}
        vals.append(len(topk_numbers(s, k, min_number) & actual_set))
    return float(np.mean(vals)) if vals else 0.0


def close_to_base_rate(mean_hits: float, max_number: int, k: int = 6,
                       tolerance: float = 0.05) -> bool:
    """Are the hits indistinguishable from what chance alone delivers?"""
    return bool(abs(mean_hits - theoretical_random_mean_hits(max_number, k)) <= tolerance)


def flat_predictions(scores, threshold: float = 0.01) -> bool:
    """Did the model just learn the global rate instead of discriminating?"""
    arr = np.asarray(scores, dtype=float)
    return bool(arr.size == 0 or float(arr.std()) < threshold)


def summarize(scores, actuals, max_number: int, k: int = 6,
              min_number: int = 1) -> dict:
    mean_hits = hit_rate(scores, actuals, k, min_number)
    random_mean = theoretical_random_mean_hits(max_number, k)
    return {
        "validation_mean_hits": round(mean_hits, 4),
        "random_mean_hits": round(random_mean, 4),
        "edge_vs_random": round(mean_hits - random_mean, 4),
        "close_to_base_rate": close_to_base_rate(mean_hits, max_number, k),
        "flat_predictions": flat_predictions(scores),
        "prediction_spread": round(float(np.asarray(scores, dtype=float).std()), 6),
    }
