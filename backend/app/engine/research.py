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
from .agents import (BacktestAgent, DataAgent, MasterAgent, MLResearcher,
                     OptimizerAgent, RiskAgent, StatisticianAgent,
                     paired_significance)
from .constitution import MAX_WEIGHT_DELTA_PER_DRAW, check_compliance, damped_step
from .game_config import GameConfig

# Defaults: 3 independent windows of 40 draws each, evaluated out-of-sample.
DEFAULT_WINDOWS = 3
DEFAULT_WINDOW_SIZE = 40
MIN_TRAIN = 120


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


def _hits(ticket: list[int], actual: list[int], cfg: GameConfig) -> int:
    if cfg.kind == "positional":
        return sum(1 for i, d in enumerate(ticket[:len(actual)]) if d == actual[i])
    return len(set(ticket) & set(actual))


def run_research(db: Session, cfg: GameConfig, history: list[list[int]],
                 windows: int = DEFAULT_WINDOWS, window_size: int = DEFAULT_WINDOW_SIZE,
                 seed: int = 42, persist: bool = True) -> dict:
    """Execute one full research cycle. Read-only over the history."""
    from ..models import Experiment, Hypothesis, ModelVersion

    run_id = uuid.uuid4().hex[:12]
    master = MasterAgent()
    plan = master.plan(cfg.key)
    data_agent, stat_agent = DataAgent(), StatisticianAgent()
    backtester, risk, optimizer = BacktestAgent(), RiskAgent(), OptimizerAgent()

    n = len(history)
    bounds = _window_bounds(n, windows, window_size)
    if not bounds:
        return {
            "run_id": run_id, "game_type": cfg.key, "status": "insufficient_data",
            "draws": n,
            "minimum_required": MIN_TRAIN + window_size,
            "message": (f"Se requieren al menos {MIN_TRAIN + window_size} sorteos para "
                        f"una evaluación out-of-sample; hay {n}."),
        }

    # 1. validate_data (over the raw rows we were given)
    audit = data_agent.audit([{"numbers": h, "draw_number": i} for i, h in enumerate(history)], cfg)

    # 2. run_statistics — includes the null-hypothesis test
    stats = stat_agent.analyze(history, cfg)

    # 3. run_walk_forward — every arm, every window, strictly no look-ahead
    arms: dict[str, dict] = {}          # arm -> {window_index: metrics}
    per_window_baseline: dict[int, dict] = {}
    # raw per-draw hits, kept so the arm can be tested against the baseline on
    # the very same draws (paired significance test)
    arm_hits_all: dict[str, list[int]] = {}
    baseline_hits_all: list[int] = []

    for wi, (start, end) in enumerate(bounds):
        # ensemble weights frozen with data available BEFORE the window
        pre = history[:start]
        try:
            w_info = ensemble.compute_weights(pre, cfg, force=True)
            frozen_weights = w_info["weights"]
        except Exception:
            frozen_weights = {k: 1.0 / len(ensemble.MODEL_KEYS) for k in ensemble.MODEL_KEYS}

        model_hits: dict[str, list[int]] = {k: [] for k in ensemble.MODEL_KEYS}
        ens_hits: list[int] = []
        base_hits: list[int] = []
        rng = random.Random(seed + wi)

        for t in range(start, end):
            train, actual = history[:t], history[t]
            probs_by_model = ensemble.all_model_probabilities(train, cfg)
            for k, probs in probs_by_model.items():
                model_hits[k].append(_hits(_ticket(probs, cfg), actual, cfg))
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
        arms.setdefault("ensemble_genius", {})[wi] = _summarize(ens_hits, cfg)
        arm_hits_all.setdefault("ensemble_genius", []).extend(ens_hits)
        per_window_baseline[wi] = _summarize(base_hits, cfg)
        baseline_hits_all.extend(base_hits)

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

    baseline = _aggregate(per_window_baseline)
    baseline["expected_random"] = round(cfg.pick * cfg.pick / (cfg.max_number - cfg.min_number + 1), 4)

    # 4. compare_challengers
    results = []
    for arm, per_window in arms.items():
        agg = _aggregate(per_window)
        won = sum(1 for wi, m in per_window.items()
                  if m["mean_hits"] > per_window_baseline[wi]["mean_hits"])
        sig = paired_significance(arm_hits_all.get(arm, []), baseline_hits_all)
        accepted, reason = backtester.accepts(agg, baseline, won, sig)
        results.append({
            "model_name": arm,
            "label": ("Ensamble Genius (fusionado)" if arm == "ensemble_genius"
                      else ensemble.MODEL_LABELS.get(arm, arm)),
            "metrics": agg,
            "per_window": {str(k): v for k, v in per_window.items()},
            "windows_won": won,
            "edge_vs_random": round(agg["mean_hits"] - baseline["mean_hits"], 4),
            "significance": sig,
            "accepted": accepted,
            "reason": reason,
        })
    # accepted arms first, then by edge: the champion must come from the arms
    # that actually passed the acceptance rules, not merely the luckiest one.
    results.sort(key=lambda r: (r["accepted"], r["edge_vs_random"]), reverse=True)
    best = results[0] if results else None

    # verdict — the system is allowed to say "no evidence" (rule 10)
    if best and best["accepted"]:
        verdict = "evidencia_significativa"
        verdict_text = (f"{best['label']} superó al azar por {best['edge_vs_random']:+.4f} "
                        f"aciertos/boleto en {best['windows_won']} ventanas independientes "
                        f"(p={best['significance']['p_value']:.3f}).")
    elif best and best["edge_vs_random"] > 0:
        verdict = "evidencia_debil"
        verdict_text = (f"El mejor arma ({best['label']}) queda {best['edge_vs_random']:+.4f} "
                        f"sobre el azar, pero no es distinguible del ruido "
                        f"(p={best['significance']['p_value']:.3f}). No alcanza el umbral "
                        f"de promoción: se mantiene el campeón actual.")
    else:
        verdict = "evidencia_insuficiente"
        verdict_text = ("Ningún modelo supera al azar en esta evaluación. "
                        "El resultado honesto es que no hay evidencia predictiva.")

    # 5. champion / challenger
    promotion = {"promoted": False, "reason": verdict_text,
                 "windows_won": best["windows_won"] if best else 0}
    champion_row = None
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
                promotion = {"promoted": True, "reason": best["reason"],
                             "windows_won": best["windows_won"],
                             "model_name": best["model_name"]}
            else:
                promotion["reason"] = ("El challenger cumple el umbral pero no supera al "
                                       "campeón vigente; no se promueve.")

    # 6. persist experiments + hypotheses (including the rejected ones, rule 7)
    rejected_recorded = 0
    if persist:
        db.add(Experiment(game_type=cfg.key, hypothesis="Baseline aleatorio (hipótesis nula)",
                          model_name="random_baseline", params=json.dumps({"seed": seed}),
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
        "draws": n,
        "tested_draws": sum(m["n"] for m in per_window_baseline.values()),
        "windows": [{"index": i, "from": s, "to": e, "size": e - s}
                    for i, (s, e) in enumerate(bounds)],
        "data_audit": audit,
        "statistics": stats,
        "baseline": baseline,
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
    }
    run["constitution"] = check_compliance(run)
    return run
