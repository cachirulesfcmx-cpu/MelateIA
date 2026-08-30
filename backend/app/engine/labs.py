"""The three research labs of the v4 architecture.

    AUTONOMOUS RESEARCH AGENT
       ├── STATISTICAL LAB    χ² · MI · drift · pairs · change-point
       ├── CLASSICAL ML LAB   XGBoost · ExtraTrees · RandomForest · GBM
       └── DEEP LEARNING LAB  LSTM · Transformer
                └── QUANTUM CHALLENGER

Every challenger is evaluated the same honest way as the statistical arms:
trained ONLY on data strictly before its evaluation window (frozen at the
window start — stricter than refitting per step), then scored against the real
outcome.

Optional heavy dependencies (LightGBM, CatBoost, PyTorch, PennyLane) are not
installed in this deployment: pulling PyTorch into a small web dyno would
inflate the image by hundreds of megabytes for models that cannot be trained
inside a request anyway. They are declared with their real status instead of
being faked — a lab that reports "unavailable" is honest; one that reports
invented numbers is not.
"""
from __future__ import annotations

from . import research_lab as rlab
from .game_config import GameConfig
from .models_ml import HAS_XGB, SKLEARN, _row_features

try:
    import numpy as np
    HAS_NUMPY = True
except Exception:  # pragma: no cover
    np = None  # type: ignore
    HAS_NUMPY = False


def _optional(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# STATISTICAL LAB
# --------------------------------------------------------------------------- #
class StatisticalLab:
    """χ² · mutual information · drift · pair lift · change-point."""

    name = "statistical"

    def run(self, draws: list, cfg: GameConfig, mi_null_reps: int = 30) -> dict:
        maxn = cfg.max_number
        diagnostics = rlab.run_diagnostics(draws, maxn)
        mi = rlab.mutual_information_pairs(draws, maxn)
        mi_null = rlab.max_mi_null(draws, maxn, reps=mi_null_reps)
        mi_sig = rlab.mi_significance(mi, len(draws), maxn, null=mi_null)
        cp = rlab.change_point(draws)
        dr = rlab.drift_l1(draws, maxn)
        findings = []
        if mi_sig.get("significant"):
            findings.append(f"Información mutua significativa entre {mi_sig['a']} y {mi_sig['b']}.")
        else:
            findings.append("Ninguna pareja comparte información más allá del ruido.")
        if cp.get("available"):
            findings.append(
                f"Cambio de régimen máximo {cp['standardized_shift']:.3f} frente a "
                f"{cp['noise_reference']:.3f} de referencia: "
                + ("hay punto de quiebre." if cp["significant"] else "sin punto de quiebre."))
        if dr.get("available"):
            findings.append(
                f"Deriva L1 {dr['l1']:.3f} frente a {dr['sampling_reference']:.3f} esperado: "
                + ("por encima del muestreo." if dr["above_noise"] else "compatible con muestreo."))
        return {
            "lab": self.name,
            "status": "ok",
            "chi_square": None,      # filled by the caller (uses its own agent)
            "diagnostics": diagnostics,
            "mutual_information": {"top": mi, "significance": mi_sig, "null": mi_null},
            "change_point": cp,
            "drift": dr,
            "findings": findings,
            "signal_found": bool(
                mi_sig.get("significant") or cp.get("significant") or dr.get("above_noise")
                or diagnostics.get("autocorrelation_above_noise")
            ),
        }


# --------------------------------------------------------------------------- #
# CLASSICAL ML LAB
# --------------------------------------------------------------------------- #
def _build_xy(history: list, maxn: int, start: int, max_rows: int = 60000):
    """Supervised table: one row per (draw, number) using only prior draws."""
    X, y = [], []
    for idx in range(start, len(history)):
        drawn = set(history[idx])
        for number in range(1, maxn + 1):
            X.append(_row_features(history, idx, number, maxn))
            y.append(1 if number in drawn else 0)
    if len(X) > max_rows:            # keep the most recent rows
        X, y = X[-max_rows:], y[-max_rows:]
    return X, y


class ClassicalMLLab:
    """Gradient boosting and tree ensembles as real, evaluated challengers."""

    name = "classical_ml"

    def available_models(self) -> dict[str, str]:
        return {
            "xgboost": "disponible" if HAS_XGB else "no_instalado",
            "extra_trees": "disponible" if SKLEARN else "no_instalado",
            "random_forest": "disponible" if SKLEARN else "no_instalado",
            "gradient_boosting": "disponible" if SKLEARN else "no_instalado",
            "lightgbm": "disponible" if _optional("lightgbm") else "dependencia_opcional_ausente",
            "catboost": "disponible" if _optional("catboost") else "dependencia_opcional_ausente",
        }

    def _make(self, key: str):
        if key == "xgboost" and HAS_XGB:
            import xgboost as xgb
            return xgb.XGBClassifier(n_estimators=120, max_depth=4, learning_rate=0.1,
                                     subsample=0.85, colsample_bytree=0.85,
                                     eval_metric="logloss", verbosity=0, n_jobs=2)
        if not SKLEARN:
            return None
        from sklearn.ensemble import (ExtraTreesClassifier, GradientBoostingClassifier,
                                      RandomForestClassifier)
        if key == "extra_trees":
            return ExtraTreesClassifier(n_estimators=120, max_depth=8, n_jobs=2, random_state=42)
        if key == "random_forest":
            return RandomForestClassifier(n_estimators=120, max_depth=8, n_jobs=2, random_state=42)
        if key == "gradient_boosting":
            return GradientBoostingClassifier(n_estimators=80, max_depth=3, random_state=42)
        return None

    def fit_window(self, train_history: list, cfg: GameConfig, keys: list[str]) -> dict:
        """Train each challenger ONCE on data strictly before the window."""
        fitted: dict = {}
        if not train_history or len(train_history) < 60:
            return fitted
        start = max(30, len(train_history) - 400)
        X, y = _build_xy(train_history, cfg.max_number, start)
        if not X or len(set(y)) < 2:
            return fitted
        if HAS_NUMPY:
            X = np.array(X, dtype=float)
            y = np.array(y, dtype=int)
        for key in keys:
            model = self._make(key)
            if model is None:
                continue
            try:
                model.fit(X, y)
                fitted[key] = model
            except Exception:
                continue
        return fitted

    def scores(self, model, history: list, cfg: GameConfig) -> dict[int, float]:
        """P(number appears next) for every number, from the frozen model."""
        idx = len(history)
        rows = [_row_features(history, idx, n, cfg.max_number)
                for n in range(1, cfg.max_number + 1)]
        if HAS_NUMPY:
            rows = np.array(rows, dtype=float)
        proba = model.predict_proba(rows)
        # column of class 1
        col = list(getattr(model, "classes_", [0, 1])).index(1)
        return {n + 1: float(proba[n][col]) for n in range(cfg.max_number)}


# --------------------------------------------------------------------------- #
# DEEP LEARNING LAB + QUANTUM CHALLENGER
# --------------------------------------------------------------------------- #
class _GatedChallenger:
    """A challenger whose framework may not be installed here."""

    name = ""
    requires = ""
    rationale = ""

    def available(self) -> bool:
        return _optional(self.requires)

    def status(self) -> dict:
        ok = self.available()
        return {
            "name": self.name,
            "requires": self.requires,
            "status": "disponible" if ok else "dependencia_opcional_ausente",
            "evaluated": False,
            "rationale": self.rationale,
        }


class LSTMChallenger(_GatedChallenger):
    name = "lstm"
    requires = "torch"
    rationale = ("Secuencia temporal de presencia por número. No se instala PyTorch en el "
                 "servicio web: entrenarlo dentro de una petición no es viable y el "
                 "diagnóstico ya muestra que no hay estructura temporal que aprender.")


class TransformerChallenger(_GatedChallenger):
    name = "transformer"
    requires = "torch"
    rationale = ("Atención sobre la ventana de sorteos. Mismo motivo que LSTM: requiere "
                 "un worker de entrenamiento, no el servicio web.")


class QuantumNeuralNetworkChallenger(_GatedChallenger):
    name = "quantum_neural_network"
    requires = "pennylane"
    rationale = ("Circuito variacional como challenger exploratorio. Sin evidencia de señal "
                 "en las capas previas, no habría nada que un circuito cuántico pudiera "
                 "extraer que las demás no extraigan.")


class DeepLearningLab:
    name = "deep_learning"

    def run(self) -> dict:
        challengers = [LSTMChallenger(), TransformerChallenger()]
        st = [c.status() for c in challengers]
        return {
            "lab": self.name,
            "challengers": st,
            "any_available": any(c["status"] == "disponible" for c in st),
            "note": ("Los challengers profundos se declaran con su estado real. "
                     "Ninguno reporta métricas inventadas cuando no está instalado."),
        }


class QuantumLab:
    name = "quantum"

    def run(self) -> dict:
        c = QuantumNeuralNetworkChallenger().status()
        return {"lab": self.name, "challenger": c,
                "any_available": c["status"] == "disponible"}
