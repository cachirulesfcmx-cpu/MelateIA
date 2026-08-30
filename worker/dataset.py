"""Windowed, multi-channel dataset for the sequence challengers.

Each draw becomes a feature vector per number. The channels exist so an
ablation can switch them off and show whether an advantage depended on one of
them:

    presence   the number came out in that draw (binary, always on)
    recency    exponentially decayed time since it last appeared
    frequency  rolling frequency over the window
    position   the number's normalized position in the range

The split is strictly chronological — validation is always the FUTURE of
training, never a random shuffle, or the score would be meaningless.
"""
from __future__ import annotations

import numpy as np

CHANNELS = ("presence", "recency", "frequency", "position")


def build_channels(draws: list[list[int]], max_number: int, min_number: int = 1,
                   freq_window: int = 50, decay: float = 0.9):
    """(n_draws, span, n_channels) float32 tensor of per-number features."""
    span = max_number - min_number + 1
    n = len(draws)
    presence = np.zeros((n, span), dtype=np.float32)
    for i, draw in enumerate(draws):
        for num in draw:
            if min_number <= num <= max_number:
                presence[i, int(num) - min_number] = 1.0

    # recency: decayed indicator of "how recently did this number appear"
    recency = np.zeros((n, span), dtype=np.float32)
    acc = np.zeros(span, dtype=np.float32)
    for i in range(n):
        recency[i] = acc                     # state BEFORE draw i (no look-ahead)
        acc = acc * decay + presence[i]

    # frequency: rolling share over the previous `freq_window` draws
    frequency = np.zeros((n, span), dtype=np.float32)
    running = np.zeros(span, dtype=np.float32)
    for i in range(n):
        frequency[i] = running / max(1, min(i, freq_window))
        running += presence[i]
        if i >= freq_window:
            running -= presence[i - freq_window]

    position = np.tile(
        (np.arange(span, dtype=np.float32) / max(1, span - 1))[None, :], (n, 1))

    return np.stack([presence, recency, frequency, position], axis=-1)


def make_windows(draws: list[list[int]], max_number: int, lookback: int = 32,
                 min_number: int = 1, use_recency: bool = True,
                 use_frequency: bool = True, use_position: bool = True):
    """Sliding windows of the enabled channels, flattened per timestep.

    Returns (X, y) where X is (samples, lookback, span * n_enabled_channels)
    and y is the next draw's presence vector.
    """
    span = max_number - min_number + 1
    feats = build_channels(draws, max_number, min_number)
    keep = [0]                                   # presence is always kept
    if use_recency:
        keep.append(1)
    if use_frequency:
        keep.append(2)
    if use_position:
        keep.append(3)
    selected = feats[:, :, keep]                 # (n, span, c)
    n = selected.shape[0]
    flat = selected.reshape(n, span * len(keep))
    target = feats[:, :, 0]                      # presence of the next draw

    X, y = [], []
    for i in range(lookback, n):
        X.append(flat[i - lookback:i])
        y.append(target[i])
    if not X:
        return (np.zeros((0, lookback, span * len(keep)), dtype=np.float32),
                np.zeros((0, span), dtype=np.float32))
    return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.float32)


def chronological_split(X, y, train_ratio: float = 0.8):
    """Never shuffle: validation must be the future of training."""
    split = int(len(X) * train_ratio)
    return X[:split], X[split:], y[:split], y[split:]
