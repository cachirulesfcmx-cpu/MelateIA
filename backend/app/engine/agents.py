"""Research agents — each one does real work over the real history.

Ported from the "Melate Autonomous Research Agent" package, where these were
placeholders returning static dicts. Here every agent computes something the
research cycle actually consumes.
"""
from __future__ import annotations

import math
from collections import Counter

from .game_config import GameConfig


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def chi_square_uniformity(history: list[list[int]], cfg: GameConfig) -> dict:
    """Test whether the observed number frequencies differ from uniform.

    Wilson–Hilferty approximation for the chi-square survival function, so the
    project keeps working without scipy. A high p-value means "indistinguishable
    from a fair draw" — which is the expected, honest outcome for a lottery.
    """
    maxn = cfg.max_number
    counts = Counter(n for d in history for n in d if cfg.min_number <= n <= maxn)
    k = maxn - cfg.min_number + 1
    total = sum(counts.values())
    if total == 0 or k < 2:
        return {"chi_square": 0.0, "df": 0, "p_value": 1.0, "uniform": True, "n_draws": len(history)}
    expected = total / k
    chi2 = sum((counts.get(n, 0) - expected) ** 2 / expected
               for n in range(cfg.min_number, maxn + 1))
    df = k - 1
    # Wilson–Hilferty: (chi2/df)^(1/3) is ~normal
    t = (chi2 / df) ** (1.0 / 3.0)
    mean = 1.0 - 2.0 / (9.0 * df)
    sd = math.sqrt(2.0 / (9.0 * df))
    z = (t - mean) / sd if sd > 0 else 0.0
    p = max(0.0, min(1.0, 1.0 - _phi(z)))
    return {"chi_square": round(chi2, 3), "df": df, "p_value": round(p, 4),
            "uniform": p > 0.05, "n_draws": len(history)}


class DataAgent:
    """Guards the integrity of the history (constitution rules 1 and 2)."""

    def validate_draw(self, numbers: list[int], cfg: GameConfig) -> bool:
        if len(numbers) != cfg.pick:
            return False
        if not all(cfg.min_number <= int(n) <= cfg.max_number for n in numbers):
            return False
        if cfg.kind == "combination" and len(set(numbers)) != cfg.pick:
            return False
        return True

    def audit(self, rows: list[dict], cfg: GameConfig) -> dict:
        """Full integrity report over the stored history."""
        invalid, duplicated_draws, seen_numbers = [], [], set()
        seen_draw_numbers: set = set()
        for r in rows:
            nums = r.get("numbers") or []
            if not self.validate_draw(nums, cfg):
                invalid.append(r.get("draw_number"))
            dn = r.get("draw_number")
            if dn is not None:
                if dn in seen_draw_numbers:
                    duplicated_draws.append(dn)
                seen_draw_numbers.add(dn)
            key = tuple(sorted(nums)) if cfg.kind == "combination" else tuple(nums)
            seen_numbers.add(key)
        ordered = [r.get("draw_number") for r in rows if r.get("draw_number") is not None]
        chronological = ordered == sorted(ordered)
        return {
            "total": len(rows),
            "invalid": invalid[:20],
            "invalid_count": len(invalid),
            "duplicated_draw_numbers": duplicated_draws[:20],
            "distinct_combinations": len(seen_numbers),
            "chronological": chronological,
            "ok": not invalid and not duplicated_draws,
        }


class StatisticianAgent:
    """Descriptive statistics + the null-hypothesis test (rule 9)."""

    def analyze(self, history: list[list[int]], cfg: GameConfig) -> dict:
        counts = Counter(n for d in history for n in d
                         if cfg.min_number <= n <= cfg.max_number)
        total = sum(counts.values()) or 1
        ranking = sorted(
            ({"number": n, "count": counts.get(n, 0), "share": round(counts.get(n, 0) / total, 5)}
             for n in range(cfg.min_number, cfg.max_number + 1)),
            key=lambda x: x["count"], reverse=True,
        )
        uniformity = chi_square_uniformity(history, cfg)
        return {
            "n_draws": len(history),
            "top": ranking[:10],
            "bottom": ranking[-10:],
            "uniformity": uniformity,
            "reading": (
                "Las frecuencias no se distinguen de un sorteo justo (p > 0.05): "
                "no hay números 'con suerte'."
                if uniformity["uniform"] else
                "Se observa desviación respecto a la uniformidad; puede ser ruido "
                "de muestreo y requiere backtesting para significar algo."
            ),
        }


def paired_significance(arm_hits: list[int], baseline_hits: list[int]) -> dict:
    """Paired test of "this arm beats the random baseline", draw by draw.

    Both arms are evaluated against the SAME actual draws, so the comparison is
    paired: we test whether the mean of the per-draw differences is above zero.
    One-sided, normal approximation of the t statistic (no scipy needed).
    """
    n = min(len(arm_hits), len(baseline_hits))
    if n < 2:
        return {"n": n, "mean_diff": 0.0, "t_stat": 0.0, "p_value": 1.0, "significant": False}
    diffs = [a - b for a, b in zip(arm_hits[:n], baseline_hits[:n])]
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    se = math.sqrt(var / n) if var > 0 else 0.0
    if se == 0.0:
        # identical every draw → no measurable advantage
        return {"n": n, "mean_diff": round(mean, 4), "t_stat": 0.0,
                "p_value": 0.0 if mean > 0 else 1.0, "significant": mean > 0}
    t = mean / se
    p = max(0.0, min(1.0, 1.0 - _phi(t)))  # one-sided
    return {"n": n, "mean_diff": round(mean, 4), "t_stat": round(t, 3),
            "p_value": round(p, 4), "significant": p < 0.05}


class BacktestAgent:
    """Owns the acceptance rules for any predictive claim (rules 3, 5 and 9)."""

    def acceptance_rules(self) -> dict:
        from .constitution import MAX_P_VALUE, MIN_IMPROVEMENT, MIN_WINDOWS_WON
        return {
            "requires_out_of_sample": True,
            "requires_baseline_comparison": True,
            "requires_multiple_windows": True,
            "requires_statistical_significance": True,
            "minimum_improvement": MIN_IMPROVEMENT,
            "minimum_windows_won": MIN_WINDOWS_WON,
            "maximum_p_value": MAX_P_VALUE,
        }

    def accepts(self, model_metrics: dict, baseline_metrics: dict, windows_won: int,
                significance: dict | None = None) -> tuple[bool, str]:
        from .constitution import MAX_P_VALUE, MIN_IMPROVEMENT, MIN_WINDOWS_WON
        edge = model_metrics.get("mean_hits", 0.0) - baseline_metrics.get("mean_hits", 0.0)
        if edge < MIN_IMPROVEMENT:
            return False, (f"Mejora sobre el azar {edge:+.4f} < mínimo requerido "
                           f"{MIN_IMPROVEMENT}. No se promueve.")
        if windows_won < MIN_WINDOWS_WON:
            return False, (f"Ganó {windows_won} ventana(s); se requieren "
                           f"{MIN_WINDOWS_WON} independientes. No se promueve.")
        p = (significance or {}).get("p_value", 1.0)
        if p > MAX_P_VALUE:
            return False, (f"Ventaja {edge:+.4f} no es distinguible del azar "
                           f"(p={p:.3f} > {MAX_P_VALUE}). Es ruido: no se promueve.")
        return True, (f"Mejora {edge:+.4f} sobre el azar en {windows_won} ventanas "
                      f"independientes, significativa (p={p:.3f}). Promoción válida.")


class OptimizerAgent:
    """Per-game hard constraints for generated candidates."""

    def constraints(self, cfg: GameConfig) -> dict:
        return {
            "game": cfg.key,
            "pick": cfg.pick,
            "min_number": cfg.min_number,
            "max_number": cfg.max_number,
            "unique_numbers": cfg.kind == "combination",
            "ordered": cfg.kind == "positional",
            "sort_numbers": cfg.kind == "combination",
        }


class RiskAgent:
    """Filters candidates that are invalid or structurally bad bets."""

    def validate(self, candidates: list[list[int]], cfg: GameConfig) -> dict:
        out: list[list[int]] = []
        seen: set = set()
        rejected = {"invalido": 0, "duplicado": 0, "solo_calendario": 0, "secuencia_larga": 0}
        data = DataAgent()
        for c in candidates:
            nums = list(c)
            if not data.validate_draw(nums, cfg):
                rejected["invalido"] += 1
                continue
            key = tuple(sorted(nums)) if cfg.kind == "combination" else tuple(nums)
            if key in seen:
                rejected["duplicado"] += 1
                continue
            if cfg.kind == "combination":
                # all numbers <= 31 is the classic "birthdays" ticket: valid, but
                # it maximises the chance of sharing the prize.
                if all(n <= 31 for n in nums) and cfg.max_number > 31:
                    rejected["solo_calendario"] += 1
                    continue
                s = sorted(nums)
                run = longest = 1
                for i in range(1, len(s)):
                    run = run + 1 if s[i] == s[i - 1] + 1 else 1
                    longest = max(longest, run)
                if longest >= 4:
                    rejected["secuencia_larga"] += 1
                    continue
            seen.add(key)
            out.append(sorted(nums) if cfg.kind == "combination" else nums)
        return {"accepted": out, "rejected": rejected,
                "accepted_count": len(out), "rejected_count": sum(rejected.values())}


class MLResearcher:
    """Declares which model families are under study, with their real status."""

    def propose(self, cfg: GameConfig) -> list[dict]:
        from .ensemble import MODEL_KEYS, MODEL_LABELS
        from .models_ml import HAS_XGB, SKLEARN
        models = [{"model": k, "label": MODEL_LABELS.get(k, k), "family": "estadístico",
                   "status": "en_produccion"} for k in MODEL_KEYS]
        models.append({"model": "xgboost", "label": "XGBoost por número", "family": "ml",
                       "status": "en_produccion" if HAS_XGB else
                                 ("degradado_sklearn" if SKLEARN else "heuristico")})
        return models


class MasterAgent:
    """Plans the research cycle and states the rules it will be held to."""

    ACTIONS = ["validate_data", "run_statistics", "run_walk_forward",
               "compare_challengers", "generate_candidates", "risk_validate",
               "check_constitution"]

    def plan(self, game: str, context: dict | None = None) -> dict:
        return {
            "game": game,
            "actions": list(self.ACTIONS),
            "rules": ["no_future_information", "immutable_history",
                      "promote_only_on_out_of_sample_evidence",
                      "random_is_the_null_hypothesis"],
            "context": context or {},
        }
