"""Autonomous research cycle.

Runs a full scientific pass over a game's real history:

    validate_data → run_statistics → run_walk_forward (multi-window, no
    look-ahead) → compare_challengers → generate_candidates → risk_validate
    → check_constitution

Every arm (each of the 15 base models, the fused Genius ensemble, and the
random baseline) is evaluated the same way: at step t, train only on the draws
before t, take the top-`pick` numbers as a ticket, and count real hits against
the actual result. Randomness is the null hypothesis, and the cycle is allowed
to conclude that no model beats it — that verdict is a valid outcome, not a
failure.

Results are persisted as Experiment / Hypothesis / ModelVersion rows so any
predictive claim is auditable and reproducible.
"""
from __future__ import annotations

import json
import random
import uuid
from heapq import nlargest

from sqlalchemy.orm import Session

from . import ensemble
from . import research_lab as rlab
from . import confirmation as cqueue
from .autonomous_cycle import (STATES as CYCLE_STATES, generate_hypotheses,
                               replication_gate)
from .labs import ClassicalMLLab, DeepLearningLab, QuantumLab, StatisticalLab
from .agents import (BacktestAgent, DataAgent, MasterAgent, MLResearcher,
                     OptimizerAgent, RiskAgent, StatisticianAgent,
                     paired_significance)
from .constitution import MAX_WEIGHT_DELTA_PER_DRAW, check_compliance, damped_step
from .game_config import GameConfig

# Defaults: 3 independent windows of 40 draws each, evaluated out-of-sample.
DEFAULT_WINDOWS = 3
DEFAULT_WINDOW_SIZE = 40
MIN_TRAIN = 120
# Temporal permutation testing (protocol v3, point 5). Kept modest by default:
# each permutation re-runs a walk-forward, so cost is permutations x perm_window
# model fits per tested arm.
DEFAULT_PERMUTATIONS = 30
DEFAULT_PERM_WINDOW = 25


def _ticket(scores: dict[int, float], cfg: GameConfig) -> list[int]:
    """Top-`pick` numbers of a score map — one deterministic ticket."""
    return sorted(n for n, _ in nlargest(cfg.pick, scores.items(), key=lambda kv: kv[1]))


def _summarize(hits: list[int], cfg: GameConfig) -> dict:
    if not hits:
        return {"n": 0, "mean_hits": 0.0, "hit_rate_3plus": 0.0,
                "hit_rate_4plus": 0.0, "max_hits": 0}
    n = len(hits)
    return {
        "n": n,
        "mean_hits": round(sum(hits) / n, 4),
        "hit_rate_3plus": round(sum(1 for h in hits if h >= 3) / n, 4),
        "hit_rate_4plus": round(sum(1 for h in hits if h >= 4) / n, 4),
        "max_hits": max(hits),
    }


def _window_bounds(n: int, windows: int, size: int) -> list[tuple[int, int]]:
    """Most recent `windows` non-overlapping blocks of `size` draws."""
    bounds = []
    end = n
    for _ in range(windows):
        start = end - size
        if start < MIN_TRAIN:
            break
        bounds.append((start, end))
        end = start
    return list(reversed(bounds))


ML_LABELS = {
    "ml_xgboost": "XGBoost (ML clásico)",
    "ml_extra_trees": "ExtraTrees (ML clásico)",
    "ml_random_forest": "RandomForest (ML clásico)",
    "ml_gradient_boosting": "GradientBoosting (ML clásico)",
    "ml_lightgbm": "LightGBM (ML clásico)",
    "ml_catboost": "CatBoost (ML clásico)",
}


def _arm_label(arm: str) -> str:
    if arm == "ensemble_genius":
        return "Ensamble Genius (fusionado)"
    if arm in ML_LABELS:
        return ML_LABELS[arm]
    return ensemble.MODEL_LABELS.get(arm, arm)


def _hits(ticket: list[int], actual: list[int], cfg: GameConfig) -> int:
    if cfg.kind == "positional":
        return sum(1 for i, d in enumerate(ticket[:len(actual)]) if d == actual[i])
    return len(set(ticket) & set(actual))


def run_research(db: Session, cfg: GameConfig, history: list[list[int]],
                 windows: int = DEFAULT_WINDOWS, window_size: int = DEFAULT_WINDOW_SIZE,
                 seed: int = 42, persist: bool = True,
                 permutations: int = DEFAULT_PERMUTATIONS,
                 perm_window: int = DEFAULT_PERM_WINDOW,
                 include_ml_lab: bool = True) -> dict:
    """Execute one full research cycle. Read-only over the history."""
    from ..models import Experiment, Hypothesis, ModelVersion

    run_id = uuid.uuid4().hex[:12]
    master = MasterAgent()
    plan = master.plan(cfg.key)
    data_agent, stat_agent = DataAgent(), StatisticianAgent()
    backtester, risk, optimizer = BacktestAgent(), RiskAgent(), OptimizerAgent()

    n_total = len(history)

    # PROTOCOL v3, point 7 — the final 10% is locked away BEFORE anything else
    # happens. Every selection decision below sees `selection` only.
    split = rlab.chronological_split(history)
    selection = split.selection
    golden = split.golden_holdout
    n = len(selection)

    bounds = _window_bounds(n, windows, window_size)
    if not bounds:
        return {
            "run_id": run_id, "game_type": cfg.key, "status": "insufficient_data",
            "draws": n_total, "selection_draws": n,
            "minimum_required": int((MIN_TRAIN + window_size) / 0.9) + 1,
            "message": (f"Tras reservar el Golden Holdout (10%) quedan {n} sorteos para "
                        f"selección; se requieren al menos {MIN_TRAIN + window_size}."),
        }

    # 1. validate_data (over the raw rows we were given)
    audit = data_agent.audit([{"numbers": h, "draw_number": i} for i, h in enumerate(history)], cfg)

    # 2. run_statistics — includes the null-hypothesis test (selection only)
    stats = stat_agent.analyze(selection, cfg)

    # 2b. STATISTICAL LAB (v4) — χ² · MI · drift · pairs · change-point
    statistical_lab = StatisticalLab().run(selection, cfg)
    statistical_lab["chi_square"] = stats["uniformity"]
    diagnostics = statistical_lab["diagnostics"]

    # DEEP LEARNING LAB + QUANTUM CHALLENGER — declared with their real status
    deep_lab = DeepLearningLab().run()
    quantum_lab = QuantumLab().run()

    # 2c. PROTOCOL v3, point 6 — hypotheses are registered BEFORE any test is
    # run, so the record cannot be rewritten to match whatever came out.
    prereg_ids: dict[str, int] = {}
    if persist:
        for code, statement in rlab.PRE_REGISTERED.items():
            row = Hypothesis(game_type=cfg.key, statement=f"[{code}] {statement}",
                             status="pendiente",
                             evidence=json.dumps({"pre_registered": True, "code": code}),
                             run_id=run_id)
            db.add(row)
            db.flush()
            prereg_ids[code] = row.id
        db.commit()

    # 3. run_walk_forward — every arm, every window, strictly no look-ahead
    arms: dict[str, dict] = {}          # arm -> {window_index: metrics}
    per_window_baseline: dict[int, dict] = {}
    # raw per-draw hits, kept so the arm can be tested against the baseline on
    # the very same draws (paired significance test)
    arm_hits_all: dict[str, list[int]] = {}
    baseline_hits_all: list[int] = []

    # CLASSICAL ML LAB — challengers trained ONCE per window on prior data only
    ml_lab = ClassicalMLLab()
    ml_available = [k for k, v in ml_lab.available_models().items() if v == "disponible"]
    ml_keys = ml_available if include_ml_lab else []

    for wi, (start, end) in enumerate(bounds):
        # ensemble weights frozen with data available BEFORE the window
        pre = selection[:start]
        try:
            w_info = ensemble.compute_weights(pre, cfg, force=True)
            frozen_weights = w_info["weights"]
        except Exception:
            frozen_weights = {k: 1.0 / len(ensemble.MODEL_KEYS) for k in ensemble.MODEL_KEYS}

        fitted_ml = {}
        if ml_keys:
            try:
                fitted_ml = ml_lab.fit_window(pre, cfg, ml_keys)
            except Exception:
                fitted_ml = {}

        model_hits: dict[str, list[int]] = {k: [] for k in ensemble.MODEL_KEYS}
        ml_hits: dict[str, list[int]] = {f"ml_{k}": [] for k in fitted_ml}
        ens_hits: list[int] = []
        base_hits: list[int] = []
        rng = random.Random(seed + wi)

        for t in range(start, end):
            train, actual = selection[:t], selection[t]
            probs_by_model = ensemble.all_model_probabilities(train, cfg)
            for k, probs in probs_by_model.items():
                model_hits[k].append(_hits(_ticket(probs, cfg), actual, cfg))
            for k, model in fitted_ml.items():
                try:
                    sc = ml_lab.scores(model, train, cfg)
                    ml_hits[f"ml_{k}"].append(_hits(_ticket(sc, cfg), actual, cfg))
                except Exception:
                    pass
            fused = {num: 0.0 for num in range(1, cfg.max_number + 1)}
            for k, probs in probs_by_model.items():
                wk = frozen_weights.get(k, 0.0)
                if wk <= 0:
                    continue
                for num in fused:
                    fused[num] += wk * probs.get(num, 0.0)
            ens_hits.append(_hits(_ticket(fused, cfg), actual, cfg))
            pool = list(range(cfg.min_number, cfg.max_number + 1))
            base_hits.append(_hits(sorted(rng.sample(pool, cfg.pick)), actual, cfg))

        for k, hits in model_hits.items():
            arms.setdefault(k, {})[wi] = _summarize(hits, cfg)
            arm_hits_all.setdefault(k, []).extend(hits)
        for k, hits in ml_hits.items():
            if len(hits) == (end - start):     # only complete windows are comparable
                arms.setdefault(k, {})[wi] = _summarize(hits, cfg)
                arm_hits_all.setdefault(k, []).extend(hits)
        arms.setdefault("ensemble_genius", {})[wi] = _summarize(ens_hits, cfg)
        arm_hits_all.setdefault("ensemble_genius", []).extend(ens_hits)
        per_window_baseline[wi] = _summarize(base_hits, cfg)
        baseline_hits_all.extend(base_hits)

    # drop ML arms that could not be evaluated in every window
    for k in [a for a in arms if a.startswith("ml_") and len(arms[a]) != len(bounds)]:
        arms.pop(k, None)
        arm_hits_all.pop(k, None)

    def _aggregate(per_window: dict[int, dict]) -> dict:
        ns = [m["n"] for m in per_window.values()]
        tot = sum(ns) or 1
        return {
            "n": tot,
            "mean_hits": round(sum(m["mean_hits"] * m["n"] for m in per_window.values()) / tot, 4),
            "hit_rate_3plus": round(sum(m["hit_rate_3plus"] * m["n"] for m in per_window.values()) / tot, 4),
            "hit_rate_4plus": round(sum(m["hit_rate_4plus"] * m["n"] for m in per_window.values()) / tot, 4),
            "max_hits": max((m["max_hits"] for m in per_window.values()), default=0),
        }

    # PROTOCOL v3, point 3 — the baselines are kept STRICTLY separate and are
    # never mixed into one number.
    tested = sum(m["n"] for m in per_window_baseline.values())
    theoretical = rlab.theoretical_random_mean_hits(cfg.max_number, cfg.pick)
    exact_random = rlab.empirical_random_baseline(tested, cfg.max_number, cfg.pick)
    simulated = _aggregate(per_window_baseline)   # one Monte Carlo realisation

    baselines_block = {
        "teorico": {"mean_hits": round(theoretical, 6),
                    "formula": f"{cfg.pick}×{cfg.pick}/{cfg.max_number}"},
        "empirico_exacto": exact_random,
        "simulado_montecarlo": simulated,
        "de_modelo": {},   # filled in after the arms are aggregated
        "nota": ("El baseline usado para juzgar a los modelos es el empírico exacto "
                 "(hipergeométrico). El simulado es una sola realización y su ruido "
                 "no debe confundirse con el valor esperado."),
    }

    # The reference every arm is judged against is the EXACT distribution, not
    # one lucky/unlucky Monte Carlo run.
    baseline = {**simulated, "mean_hits": exact_random["mean_hits"],
                "expected_random": round(theoretical, 4),
                "source": "hipergeométrica exacta"}

    # 4. compare_challengers
    results = []
    for arm, per_window in arms.items():
        agg = _aggregate(per_window)
        won = sum(1 for wi, m in per_window.items()
                  if m["mean_hits"] > per_window_baseline[wi]["mean_hits"])
        sig = paired_significance(arm_hits_all.get(arm, []), baseline_hits_all)
        results.append({
            "model_name": arm,
            "label": _arm_label(arm),
            "lab": ("classical_ml" if arm.startswith("ml_")
                    else ("ensemble" if arm == "ensemble_genius" else "statistical")),
            "metrics": agg,
            "per_window": {str(k): v for k, v in per_window.items()},
            "windows_won": won,
            "edge_vs_random": round(agg["mean_hits"] - baseline["mean_hits"], 4),
            "significance": sig,
        })

    # PROTOCOL v3, point 6 — Benjamini-Hochberg over the WHOLE family of tests.
    # Testing 16 arms at once and reading raw p-values would manufacture a
    # "winner" by chance alone; the corrected q-value is what decides.
    corrected = rlab.benjamini_hochberg([r["significance"]["p_value"] for r in results])
    for r, c in zip(results, corrected):
        r["q_value"] = c["q"]
        r["significant_corrected"] = c["significant"]
        accepted, reason = backtester.accepts(
            r["metrics"], baseline, r["windows_won"],
            {**r["significance"], "q_value": c["q"]})
        r["accepted"] = accepted
        r["reason"] = reason

    # model baselines (point 3): simple references, reported apart from the rest
    for key, name in (("frequency", "frecuencia"), ("bayes_decay", "recencia")):
        row = next((r for r in results if r["model_name"] == key), None)
        if row:
            baselines_block["de_modelo"][name] = {
                "mean_hits": row["metrics"]["mean_hits"],
                "edge_vs_random": row["edge_vs_random"],
                "q_value": row["q_value"],
            }

    # accepted arms first, then by edge: the champion must come from the arms
    # that actually passed the acceptance rules, not merely the luckiest one.
    results.sort(key=lambda r: (r["accepted"], r["edge_vs_random"]), reverse=True)
    best = results[0] if results else None

    # PROTOCOL v3, point 5 — temporal permutation test. Does the ORDER of the
    # draws carry information at all? Run on the two model baselines (as the
    # source protocol does) plus the best arm.
    permutation_block: dict = {}
    if permutations > 0:
        perm_targets = []
        for key in ("frequency", "bayes_decay"):
            if key in ensemble.MODELS:
                perm_targets.append(key)
        if best and best["model_name"] in ensemble.MODELS and best["model_name"] not in perm_targets:
            perm_targets.append(best["model_name"])
        perm_start, perm_end = bounds[-1]
        perm_steps = min(perm_window, perm_end - perm_start)
        for key in perm_targets:
            fn = ensemble.MODELS[key]

            def _mean_hits(seq, _fn=fn):
                hits = []
                stop = len(seq)
                for t in range(stop - perm_steps, stop):
                    if t < MIN_TRAIN:
                        continue
                    hits.append(_hits(_ticket(_fn(seq[:t], cfg), cfg), seq[t], cfg))
                return sum(hits) / len(hits) if hits else 0.0

            try:
                permutation_block[key] = {
                    "label": ensemble.MODEL_LABELS.get(key, key),
                    **rlab.temporal_permutation_test(
                        selection[:perm_end], _mean_hits,
                        n_permutations=permutations, seed=seed),
                }
            except Exception as exc:  # never break the cycle on a slow arm
                permutation_block[key] = {"error": str(exc)}
        if permutation_block:
            keys = [k for k, v in permutation_block.items() if "p_value" in v]
            corr = rlab.benjamini_hochberg([permutation_block[k]["p_value"] for k in keys])
            for k, c in zip(keys, corr):
                permutation_block[k]["q_value"] = c["q"]
                permutation_block[k]["significant_corrected"] = c["significant"]

    # BLOCK BOOTSTRAP — resample in contiguous blocks so local temporal
    # structure survives; a plain bootstrap would understate the uncertainty.
    bootstrap_block = rlab.block_bootstrap(selection, block=10, reps=200, seed=seed)
    if best and arm_hits_all.get(best["model_name"]):
        hits_series = arm_hits_all[best["model_name"]]
        bootstrap_best = rlab.block_bootstrap(
            [[h] for h in hits_series], block=5, reps=200, seed=seed,
            statistic=lambda sample: sum(x[0] for x in sample) / len(sample))
        if bootstrap_best.get("available"):
            bootstrap_best["arm"] = best["model_name"]
            bootstrap_best["random_baseline"] = baseline["mean_hits"]
            # if the interval contains the random baseline, the edge is not solid
            bootstrap_best["excludes_random"] = bootstrap_best["ci95"][0] > baseline["mean_hits"]
        bootstrap_block = {"draw_sums": bootstrap_block, "best_arm_hits": bootstrap_best}
    else:
        bootstrap_block = {"draw_sums": bootstrap_block, "best_arm_hits": None}

    # 4b. PROTOCOL v3, point 7 — the Golden Holdout is touched ONLY here, and
    # only by a candidate that already passed every corrected criterion.
    golden_block = rlab.golden_holdout_block(split)
    golden_eval = None
    if best and best["accepted"] and best["model_name"] in ensemble.MODELS and golden:
        fn = ensemble.MODELS[best["model_name"]]
        hits = []
        base_g = []
        rng_g = random.Random(seed + 999)
        pool = list(range(cfg.min_number, cfg.max_number + 1))
        for i, actual in enumerate(golden):
            train = selection + golden[:i]     # everything strictly before it
            hits.append(_hits(_ticket(fn(train, cfg), cfg), actual, cfg))
            base_g.append(_hits(sorted(rng_g.sample(pool, cfg.pick)), actual, cfg))
        g_metrics = _summarize(hits, cfg)
        g_exact = rlab.empirical_random_baseline(len(hits), cfg.max_number, cfg.pick)
        g_sig = paired_significance(hits, base_g)
        passed = (g_metrics["mean_hits"] - g_exact["mean_hits"]) >= rlab.MIN_IMPROVEMENT_V3
        golden_eval = {
            "model_name": best["model_name"], "label": best["label"],
            "metrics": g_metrics, "exact_random": g_exact["mean_hits"],
            "edge_vs_random": round(g_metrics["mean_hits"] - g_exact["mean_hits"], 4),
            "significance": g_sig, "passed": passed,
            "note": ("El candidato se evaluó una sola vez sobre el 10% bloqueado."
                     if passed else
                     "El candidato NO sobrevivió al Golden Holdout: la ventaja no se sostuvo "
                     "fuera de los datos de selección."),
        }
        golden_block["evaluated"] = True
        golden_block["evaluation"] = golden_eval
        if not passed:
            best["accepted"] = False
            best["reason"] = "Ventaja no confirmada en el Golden Holdout."

    # verdict — the system is allowed to say "no evidence" (rule 10)
    if best and best["accepted"]:
        verdict = "evidencia_significativa"
        verdict_text = (f"{best['label']} superó al azar por {best['edge_vs_random']:+.4f} "
                        f"aciertos/boleto en {best['windows_won']} ventanas independientes "
                        f"(q={best['q_value']:.3f} corregido"
                        + (", confirmado en el Golden Holdout" if golden_eval else "") + ").")
    elif best and best["edge_vs_random"] > 0:
        verdict = "evidencia_debil"
        verdict_text = (f"El mejor arma ({best['label']}) queda {best['edge_vs_random']:+.4f} "
                        f"sobre el azar exacto, pero tras corregir por pruebas múltiples "
                        f"no es distinguible del ruido (p={best['significance']['p_value']:.3f}, "
                        f"q={best['q_value']:.3f}). No se promueve.")
    else:
        verdict = "evidencia_insuficiente"
        verdict_text = ("Ningún modelo supera al azar en esta evaluación. "
                        "El resultado honesto es que no hay evidencia predictiva.")

    # 5. champion / challenger — the v3 policy decides on the CORRECTED q-value
    # and on Golden Holdout survival, never on a raw p-value.
    policy = rlab.promotion_decision({
        "improvement_vs_random": best["edge_vs_random"] if best else 0.0,
        "q_value": best.get("q_value", 1.0) if best else 1.0,
        "out_of_sample": True,
        "windows_won": best["windows_won"] if best else 0,
        "min_windows": 2,
        "golden_holdout_passed": (golden_eval or {}).get("passed", True),
    })
    promotion = {"promoted": False,
                 "reason": policy["reason"] if not best or not best["accepted"] else verdict_text,
                 "windows_won": best["windows_won"] if best else 0,
                 "policy": policy}
    champion_row = None
    if best and not policy["promote"]:
        best["accepted"] = False

    # CONFIRMATION QUEUE — a candidate that cleared every gate still has to
    # replicate in independent runs before it can become Champion.
    queue_state = None
    if persist and best:
        if policy["promote"]:
            queue_state = cqueue.submit(
                db, cfg.key, best["model_name"], run_id, seed,
                {"edge_vs_random": best["edge_vs_random"], "q_value": best.get("q_value"),
                 "windows_won": best["windows_won"],
                 "golden_holdout": (golden_eval or {}).get("edge_vs_random")})
        else:
            queue_state = cqueue.fail(db, cfg.key, best["model_name"], run_id,
                                      policy["reason"])
    # v5 REPLICATION GATE — every condition, reported one by one
    best_perm = None
    if best:
        pb = permutation_block.get(best["model_name"]) if permutation_block else None
        best_perm = (pb or {}).get("p_value")
    gate = replication_gate(
        q_value=best.get("q_value", 1.0) if best else 1.0,
        permutation_p=best_perm if best_perm is not None else 1.0,
        holdout_score=(golden_eval or {}).get("metrics", {}).get("mean_hits", 0.0),
        baseline=baseline["mean_hits"],
        confirmations=(queue_state or {}).get("confirmations", 0),
        required_confirmations=(queue_state or {}).get("required", 2),
    )

    ready = bool(queue_state and queue_state.get("ready_to_promote"))
    if best and policy["promote"] and not ready:
        # passed the statistics, still awaiting replication
        best["accepted"] = False

    if persist:
        champion_row = (db.query(ModelVersion)
                        .filter(ModelVersion.game_type == cfg.key,
                                ModelVersion.role == "champion",
                                ModelVersion.active.is_(True))
                        .first())
        if best and best["accepted"]:
            improves = champion_row is None or best["metrics"]["mean_hits"] > (champion_row.score or 0.0)
            if improves:
                if champion_row:
                    champion_row.role = "retired"
                    champion_row.active = False
                champion_row = ModelVersion(
                    game_type=cfg.key, model_name=best["model_name"],
                    version=f"{best['model_name']}-{run_id}", role="champion",
                    score=best["metrics"]["mean_hits"], baseline_score=baseline["mean_hits"],
                    windows=best["windows_won"], metrics=json.dumps(best["metrics"]),
                    active=True,
                )
                db.add(champion_row)
                db.commit()
                cqueue.mark_promoted(db, cfg.key, best["model_name"])
                promotion = {"promoted": True, "reason": best["reason"],
                             "windows_won": best["windows_won"],
                             "model_name": best["model_name"]}
            else:
                promotion["reason"] = ("El challenger cumple el umbral pero no supera al "
                                       "campeón vigente; no se promueve.")
        elif best and policy["promote"] and not ready:
            promotion["reason"] = (queue_state or {}).get(
                "message", "En cola de confirmación: falta replicación independiente.")

    # 5b. Resolve the PRE-REGISTERED hypotheses against the evidence actually
    # measured. Each one has a concrete, stated criterion — decided after the
    # tests ran, but written down before them.
    by_arm = {r["model_name"]: r for r in results}
    ens = by_arm.get("ensemble_genius", {})
    perm_h07 = any(v.get("significant_corrected") for v in permutation_block.values()
                   if isinstance(v, dict))
    prereg_results = {
        "H01": (bool(by_arm.get("bayes_decay", {}).get("accepted")),
                {"arm": "bayes_decay", "edge": by_arm.get("bayes_decay", {}).get("edge_vs_random"),
                 "q": by_arm.get("bayes_decay", {}).get("q_value")}),
        "H02": (bool(by_arm.get("frequency", {}).get("accepted")),
                {"arm": "frequency", "edge": by_arm.get("frequency", {}).get("edge_vs_random"),
                 "q": by_arm.get("frequency", {}).get("q_value")}),
        "H03": (bool(diagnostics.get("autocorrelation_above_noise")),
                {"strongest_lag": diagnostics.get("strongest_lag"),
                 "value": diagnostics.get("strongest_autocorrelation"),
                 "noise_threshold": diagnostics.get("noise_threshold")}),
        "H04": (bool(diagnostics.get("top_pair_significance", {}).get("significant")),
                diagnostics.get("top_pair_significance", {})),
        "H05": (bool(diagnostics.get("regime_shift_above_noise")),
                diagnostics.get("rolling_shift_100", {})),
        "H06": (bool(ens.get("accepted")),
                {"arm": "ensemble_genius", "edge": ens.get("edge_vs_random"),
                 "q": ens.get("q_value"),
                 "vs_model_baselines": baselines_block.get("de_modelo")}),
        "H07": (perm_h07, {"permutation_tests": permutation_block}),
    }
    if persist:
        for code, (confirmed, evidence) in prereg_results.items():
            hid = prereg_ids.get(code)
            if not hid:
                continue
            row = db.query(Hypothesis).filter(Hypothesis.id == hid).first()
            if row:
                row.status = "confirmada" if confirmed else "descartada"
                row.evidence = json.dumps({"pre_registered": True, "code": code,
                                           "confirmed": confirmed, **(evidence or {})},
                                          default=str)
        db.commit()

    # 6. persist experiments + hypotheses (including the rejected ones, rule 7)
    rejected_recorded = 0
    if persist:
        db.add(Experiment(game_type=cfg.key, hypothesis="Baseline aleatorio (hipótesis nula)",
                          model_name="random_baseline",
                          params=json.dumps({"seed": seed, "draws_at_run": n_total}),
                          metrics=json.dumps(baseline), status="baseline", run_id=run_id))
        for r in results:
            status = ("champion" if promotion.get("promoted") and r["model_name"] == promotion.get("model_name")
                      else ("candidate" if r["accepted"] else "rejected"))
            db.add(Experiment(
                game_type=cfg.key,
                hypothesis=f"{r['label']} supera al azar en {cfg.label}",
                model_name=r["model_name"],
                params=json.dumps({"windows": len(bounds), "window_size": window_size, "seed": seed}),
                metrics=json.dumps({**r["metrics"], "edge_vs_random": r["edge_vs_random"],
                                    "windows_won": r["windows_won"],
                                    "p_value": r["significance"]["p_value"]}),
                status=status, run_id=run_id,
            ))
            hyp_status = "confirmada" if r["accepted"] else "descartada"
            if hyp_status == "descartada":
                rejected_recorded += 1
            db.add(Hypothesis(
                game_type=cfg.key,
                statement=f"{r['label']} tiene poder predictivo sobre {cfg.label}",
                status=hyp_status,
                evidence=json.dumps({"edge_vs_random": r["edge_vs_random"],
                                     "windows_won": r["windows_won"],
                                     "p_value": r["significance"]["p_value"],
                                     "mean_hits": r["metrics"]["mean_hits"],
                                     "baseline_mean_hits": baseline["mean_hits"],
                                     "reason": r["reason"]}),
                run_id=run_id,
            ))
        db.add(Hypothesis(
            game_type=cfg.key,
            statement=f"Existe evidencia predictiva explotable en {cfg.label}",
            status="confirmada" if verdict == "evidencia_significativa" else "descartada",
            evidence=json.dumps({"verdict": verdict, "detail": verdict_text,
                                 "baseline": baseline}),
            run_id=run_id,
        ))
        if verdict != "evidencia_significativa":
            rejected_recorded += 1
        db.commit()

    # 7. generate_candidates + risk_validate (from the live engine distribution)
    candidates_block = None
    try:
        info = ensemble.compute_weights(history, cfg)
        fused = ensemble.fused_probabilities(history, cfg, weights=info["weights"])
        meta = ensemble.meta_probabilities(history, cfg, fused)
        tickets = ensemble.generate_genius_tickets(meta, history, cfg, count=10, seed=seed)
        raw = [t["ticket"] for t in tickets]
        checked = risk.validate(raw, cfg)
        candidates_block = {
            "constraints": optimizer.constraints(cfg),
            "generated": len(raw),
            **checked,
            "accepted": checked["accepted"][:5],
        }
    except Exception as exc:  # never let candidate generation break the cycle
        candidates_block = {"error": str(exc)}

    # weight movement since the last persisted evolution (rule 6)
    max_weight_delta = 0.0
    if persist:
        from ..models import EnsembleWeight
        row = db.query(EnsembleWeight).filter(EnsembleWeight.game_type == cfg.key).first()
        if row and row.weights:
            try:
                prev = json.loads(row.weights)
                target = ensemble.compute_weights(history, cfg)["weights"]
                # the movement the governance layer would actually apply, which
                # is what rule 6 constrains — not the raw recomputation gap
                _, _, max_weight_delta = damped_step(prev, target)
            except Exception:
                max_weight_delta = 0.0

    run = {
        "run_id": run_id,
        "game_type": cfg.key,
        "game_label": cfg.label,
        "status": "ok",
        "seed": seed,
        "plan": plan,
        "walk_forward": True,
        "history_mutated": False,
        "draws": n_total,
        "selection_draws": n,
        "tested_draws": sum(m["n"] for m in per_window_baseline.values()),
        "windows": [{"index": i, "from": s, "to": e, "size": e - s}
                    for i, (s, e) in enumerate(bounds)],
        "data_audit": audit,
        "statistics": stats,
        "baseline": baseline,
        # --- protocol v3 + v4 architecture blocks ---
        "protocol_version": "v4",
        "architecture": {
            "labs": ["statistical", "classical_ml", "deep_learning", "quantum"],
            "gates": ["permutation", "block_bootstrap", "multiple_testing",
                      "golden_holdout", "confirmation_queue"],
        },
        "labs": {
            "statistical": statistical_lab,
            "classical_ml": {
                "availability": ml_lab.available_models(),
                "evaluated": sorted(a for a in arms if a.startswith("ml_")),
                "enabled": include_ml_lab,
            },
            "deep_learning": deep_lab,
            "quantum": quantum_lab,
        },
        "block_bootstrap": bootstrap_block,
        "confirmation_queue": queue_state,
        "replication_gate": gate,
        "cycle_states": CYCLE_STATES,
        "open_hypotheses": generate_hypotheses(
            [h for h in rlab.PRE_REGISTERED.values()]),
        "baselines": baselines_block,             # point 3
        "diagnostics": diagnostics,               # point 4
        "permutation_tests": permutation_block,   # point 5
        "multiple_testing": {                     # point 6
            "method": "Benjamini-Hochberg (FDR)",
            "alpha": rlab.ALPHA,
            "tests": len(results),
            "significant_after_correction": sum(1 for r in results if r.get("significant_corrected")),
        },
        "golden_holdout": golden_block,           # point 7
        "pipeline": [                             # point 8 + v4 architecture
            "api gateway", "auditoría de datos", "split + golden holdout",
            "laboratorio estadístico", "laboratorio ML clásico",
            "laboratorio deep learning", "quantum challenger",
            "baselines separados", "walk-forward", "permutación temporal",
            "block bootstrap", "corrección múltiple", "golden holdout",
            "confirmation queue", "champion/challenger", "motor de candidatos",
        ],
        "experiments": results,
        "best": best,
        "verdict": verdict,
        "verdict_text": verdict_text,
        "promotion": promotion,
        "champion": ({"model_name": champion_row.model_name, "version": champion_row.version,
                      "score": champion_row.score, "baseline_score": champion_row.baseline_score,
                      "windows": champion_row.windows} if champion_row is not None else None),
        "candidates": candidates_block,
        "models_under_study": MLResearcher().propose(cfg),
        "acceptance_rules": backtester.acceptance_rules(),
        "rejected_recorded": rejected_recorded,
        "max_weight_delta": round(max_weight_delta, 4),
        "max_weight_delta_cap": MAX_WEIGHT_DELTA_PER_DRAW,
        # constitution v3 evidence
        "additional_number_excluded": True,   # only `numbers` is ever read
        "pre_registered": len(rlab.PRE_REGISTERED),
        "pre_registered_results": {c: ok for c, (ok, _) in prereg_results.items()},
        "llm_wrote_predictions": False,
    }
    run["constitution"] = check_compliance(run)
    return run
