"""Machine-learning layer.

A per-number appearance model: for every ball we train a classifier that predicts
the probability the ball appears in the *next* draw, using rolling-window
frequency, gap/recency and parity features extracted from the chronological
history. Models are cached per game.

Uses scikit-learn's GradientBoostingClassifier / RandomForest. The structure is
deliberately pluggable so XGBoost / LightGBM / a PyTorch LSTM can be dropped in
behind the same ``NumberModel`` interface.
"""
from __future__ import annotations

try:
    import numpy as np
    NUMPY = True
except Exception:  # pragma: no cover
    np = None  # type: ignore
    NUMPY = False

try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    SKLEARN = NUMPY  # sklearn needs numpy
except Exception:  # pragma: no cover
    SKLEARN = False

# optional gradient boosting backends
try:
    import xgboost  # noqa: F401
    HAS_XGB = True
except Exception:
    HAS_XGB = False
try:
    import lightgbm  # noqa: F401
    HAS_LGBM = True
except Exception:
    HAS_LGBM = False


def _row_features(history: list[list[int]], idx: int, number: int, max_number: int) -> list[float]:
    """Features for `number` evaluated at draw position `idx` (uses draws < idx)."""
    past = history[:idx]
    if not past:
        return [0.0] * 7
    windows = [10, 25, 50]
    feats = []
    for w in windows:
        recent = past[-w:]
        cnt = sum(1 for d in recent for x in d if x == number)
        feats.append(cnt / max(1, len(recent)))
    # gap since last appearance
    gap = 0
    for d in reversed(past):
        if number in d:
            break
        gap += 1
    feats.append(min(gap, 60) / 60.0)
    feats.append(number / max_number)         # positional bias
    feats.append(1.0 if number % 2 else 0.0)  # parity
    feats.append(sum(1 for d in past[-25:] if number in d) / max(1, len(past[-25:])))
    return feats


class NumberModel:
    """Predicts P(ball appears next) for each ball."""

    def __init__(self, max_number: int):
        self.max_number = max_number
        self.model = None
        self.trained = False
        self.metrics: dict = {}
        self.backend = "heuristic"

    def fit(self, history: list[list[int]], min_history: int = 60, max_train_draws: int = 900):
        if not SKLEARN or len(history) < min_history:
            self.trained = False
            return self
        # Bound training to the most recent draws (recent data is more relevant
        # and keeps memory/CPU sane on small hosts). Deeper history still informs
        # the heuristic fallback.
        if len(history) > max_train_draws:
            history = history[-max_train_draws:]
        X, y = [], []
        start = 30
        for idx in range(start, len(history)):
            drawn = set(history[idx])
            for number in range(1, self.max_number + 1):
                X.append(_row_features(history, idx, number, self.max_number))
                y.append(1 if number in drawn else 0)
        X = np.array(X, dtype=float)
        y = np.array(y, dtype=int)
        if len(set(y.tolist())) < 2:
            self.trained = False
            return self
        # Prefer XGBoost when available (faster, often better calibrated);
        # otherwise fall back to scikit-learn's GradientBoosting.
        if HAS_XGB:
            import xgboost as xgb
            self.model = xgb.XGBClassifier(
                n_estimators=180, max_depth=4, learning_rate=0.08, subsample=0.85,
                colsample_bytree=0.85, eval_metric="logloss", n_jobs=2, tree_method="hist",
            )
            self.backend = "XGBoost"
        else:
            self.model = GradientBoostingClassifier(
                n_estimators=120, max_depth=3, learning_rate=0.08, subsample=0.85,
            )
            self.backend = "GradientBoosting"
        self.model.fit(X, y)
        self.trained = True
        # simple train accuracy / base rate for reporting
        preds = self.model.predict(X)
        self.metrics = {
            "samples": int(len(y)),
            "base_rate": round(float(y.mean()), 4),
            "train_accuracy": round(float((preds == y).mean()), 4),
            "backend": self.backend,
            "xgboost_available": HAS_XGB,
            "lightgbm_available": HAS_LGBM,
        }
        return self

    def probabilities(self, history: list[list[int]]) -> dict[int, float]:
        """P(next draw contains ball) for every ball."""
        idx = len(history)
        if self.trained and self.model is not None:
            X = np.array(
                [_row_features(history, idx, n, self.max_number) for n in range(1, self.max_number + 1)],
                dtype=float,
            )
            proba = self.model.predict_proba(X)[:, 1]
            return {n + 1: float(proba[n]) for n in range(self.max_number)}
        # heuristic fallback: recent frequency + overdue blend
        recent = history[-50:] if history else []
        counts = {n: 0 for n in range(1, self.max_number + 1)}
        for d in recent:
            for x in d:
                if 1 <= x <= self.max_number:
                    counts[x] += 1
        total = max(1, sum(counts.values()))
        return {n: counts[n] / total for n in range(1, self.max_number + 1)}

    def make_scorer(self, history: list[list[int]]):
        probs = self.probabilities(history)
        ranked = sorted(probs.values(), reverse=True)
        top = sum(ranked[: self.max_number // 4]) or 1.0

        def scorer(combo: list[int]) -> float:
            s = sum(probs.get(n, 0.0) for n in combo)
            return min(1.0, s / (top * 0.6 + 1e-6))

        return scorer


_CACHE: dict[str, NumberModel] = {}


def get_model(game_type: str, max_number: int, history: list[list[int]], force: bool = False) -> NumberModel:
    if force or game_type not in _CACHE:
        _CACHE[game_type] = NumberModel(max_number).fit(history)
    return _CACHE[game_type]


def clear_cache():
    _CACHE.clear()
