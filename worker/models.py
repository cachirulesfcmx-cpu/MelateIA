"""Sequence challengers (PyTorch). Imported only when torch is installed."""
from __future__ import annotations

import torch
from torch import nn


class LSTMChallenger(nn.Module):
    def __init__(self, input_size: int, hidden: int = 64, layers: int = 2,
                 output_size: int | None = None):
        super().__init__()
        output_size = output_size or input_size
        self.lstm = nn.LSTM(input_size, hidden, layers, batch_first=True,
                            dropout=0.1 if layers > 1 else 0.0)
        self.head = nn.Sequential(nn.LayerNorm(hidden), nn.Linear(hidden, output_size))

    def forward(self, x):
        y, _ = self.lstm(x)
        return self.head(y[:, -1, :])


class TransformerChallenger(nn.Module):
    def __init__(self, input_size: int, d_model: int = 64, heads: int = 4,
                 layers: int = 2, output_size: int | None = None):
        super().__init__()
        output_size = output_size or input_size
        self.proj = nn.Linear(input_size, d_model)
        enc = nn.TransformerEncoderLayer(d_model=d_model, nhead=heads,
                                         batch_first=True, dropout=0.1,
                                         norm_first=True)
        self.encoder = nn.TransformerEncoder(enc, num_layers=layers)
        self.head = nn.Sequential(nn.LayerNorm(d_model), nn.Linear(d_model, output_size))

    def forward(self, x):
        y = self.encoder(self.proj(x))
        return self.head(y[:, -1, :])


def build(kind: str, input_size: int):
    if kind == "lstm":
        return LSTMChallenger(input_size)
    if kind == "transformer":
        return TransformerChallenger(input_size)
    raise ValueError(f"modelo desconocido: {kind}")
