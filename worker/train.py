"""Training loop for the sequence challengers.

Two deliberate differences from the reference package:

1. It does NOT report validation loss as the headline. A binary cross-entropy
   loss looks excellent the moment the network learns to output the base rate
   (6/56 everywhere) — which predicts nothing. So the loop also measures the
   metric that actually matters: mean hits of the top-`pick` ticket on the
   validation slice, against the exact random baseline.

2. It trains in mini-batches over real epochs instead of one full-batch step,
   and keeps the weights of the best validation epoch.

The result is always published as a Challenger with promotion blocked: nothing
here can make a model Champion. That still requires walk-forward, permutation,
block bootstrap, multiple-testing correction, the Golden Holdout and
independent replication, all of which live in the app's research cycle.
"""
from __future__ import annotations

import math

import numpy as np
import torch
from torch import nn

from .dataset import chronological_split, make_windows
from .models import build


def _exact_random_mean_hits(max_number: int, pick: int) -> float:
    return (pick * pick) / max_number


def _mean_hits(logits: "torch.Tensor", targets: "torch.Tensor", pick: int) -> float:
    """Top-`pick` ticket per row, counted against the real outcome."""
    top = torch.topk(logits, pick, dim=1).indices
    hit = torch.gather(targets, 1, top).sum(dim=1)
    return float(hit.mean().item())


def train_model(draws: list[list[int]], max_number: int, kind: str, pick: int = 6,
                epochs: int = 40, lookback: int = 32, batch_size: int = 64,
                min_number: int = 1, seed: int = 42) -> dict:
    torch.manual_seed(seed)
    np.random.seed(seed)

    X, y = make_windows(draws, max_number, lookback, min_number)
    if len(X) < 100:
        return {"status": "insufficient_data", "samples": int(len(X)),
                "minimum": 100, "model": kind}

    Xtr, Xv, ytr, yv = chronological_split(X, y, 0.8)
    span = X.shape[2]
    model = build(kind, span)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.BCEWithLogitsLoss()

    Xtr_t, ytr_t = torch.from_numpy(Xtr), torch.from_numpy(ytr)
    Xv_t, yv_t = torch.from_numpy(Xv), torch.from_numpy(yv)

    best_loss = float("inf")
    best_hits = 0.0
    best_epoch = -1
    n = len(Xtr_t)

    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(n)          # batch order only; the split stays chronological
        for i in range(0, n, batch_size):
            idx = perm[i:i + batch_size]
            optimizer.zero_grad()
            loss = loss_fn(model(Xtr_t[idx]), ytr_t[idx])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        model.eval()
        with torch.no_grad():
            logits = model(Xv_t)
            val = float(loss_fn(logits, yv_t).item())
            hits = _mean_hits(logits, yv_t, pick)
        if val < best_loss:
            best_loss, best_hits, best_epoch = val, hits, epoch

    random_mean = _exact_random_mean_hits(max_number, pick)
    # how concentrated the predictions are: a model that just learned the base
    # rate has almost no spread and cannot beat random no matter its loss
    with torch.no_grad():
        probs = torch.sigmoid(model(Xv_t))
        spread = float(probs.std().item())
        base_rate = pick / span

    return {
        "status": "trained",
        "model": kind,
        "framework": "torch",
        "samples": int(len(X)),
        "train_samples": int(len(Xtr)),
        "validation_samples": int(len(Xv)),
        "epochs": epochs,
        "lookback": lookback,
        "best_epoch": best_epoch,
        "best_val_loss": round(best_loss, 6),
        # the metric that actually means something
        "validation_mean_hits": round(best_hits, 4),
        "random_mean_hits": round(random_mean, 4),
        "edge_vs_random": round(best_hits - random_mean, 4),
        "prediction_spread": round(spread, 6),
        "base_rate": round(base_rate, 6),
        "looks_like_base_rate": bool(spread < 0.01),
        "role": "challenger",
        "promotion": "blocked_until_protocol_pass",
        "note": ("La pérdida de validación no acredita nada: se minimiza prediciendo "
                 "la tasa base. Lo que cuenta es la ventaja sobre el azar, y aun así "
                 "debe pasar el protocolo completo antes de promoverse."),
    }
