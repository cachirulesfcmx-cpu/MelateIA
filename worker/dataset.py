"""Windowed dataset for the sequence challengers.

Each draw becomes a 0/1 presence vector over the game's numbers; the model sees
`lookback` consecutive draws and predicts the next one. The split is strictly
chronological — the validation slice is always the FUTURE of the training
slice, never a random shuffle, or the score would be meaningless.
"""
from __future__ import annotations

import numpy as np


def presence_matrix(draws: list[list[int]], max_number: int, min_number: int = 1):
    span = max_number - min_number + 1
    x = np.zeros((len(draws), span), dtype=np.float32)
    for i, draw in enumerate(draws):
        for n in draw:
            if min_number <= n <= max_number:
                x[i, int(n) - min_number] = 1.0
    return x


def make_windows(draws: list[list[int]], max_number: int, lookback: int = 32,
                 min_number: int = 1):
    x = presence_matrix(draws, max_number, min_number)
    X, y = [], []
    for i in range(lookback, len(x)):
        X.append(x[i - lookback:i])
        y.append(x[i])
    if not X:
        span = max_number - min_number + 1
        return (np.zeros((0, lookback, span), dtype=np.float32),
                np.zeros((0, span), dtype=np.float32))
    return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.float32)


def chronological_split(X, y, train_ratio: float = 0.8):
    """Never shuffle: validation must be the future of training."""
    split = int(len(X) * train_ratio)
    return X[:split], X[split:], y[:split], y[split:]
