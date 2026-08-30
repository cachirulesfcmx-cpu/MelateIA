"""Autonomous research endpoints — the scientific governance layer.

Exposes the agent's constitution, lets an admin run a full research cycle, and
serves the resulting record: experiments, hypotheses (including the rejected
ones) and the champion/challenger registry.
"""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_current_admin
from ..database import get_db
from ..models import Experiment, Hypothesis, ModelCard, ModelVersion, User
from ..engine.constitution import (MAX_P_VALUE, MAX_WEIGHT_DELTA_PER_DRAW,
                                   MIN_IMPROVEMENT, MIN_WINDOWS_WON, RULES)
from ..engine.game_config import GAME_KEYS, get_game
from ..engine.research import (DEFAULT_PERM_WINDOW, DEFAULT_PERMUTATIONS,
                               DEFAULT_WINDOW_SIZE, DEFAULT_WINDOWS, run_research)
from ..engine.agents import MasterAgent, MLResearcher
from ..engine.research_lab import ALPHA, MIN_IMPROVEMENT_V3, PRE_REGISTERED
from ..engine.labs import ClassicalMLLab, DeepLearningLab, QuantumLab
from ..engine import confirmation
from ..engine import model_cards
from ..engine.confirmation import REQUIRED_CONFIRMATIONS
from ..engine.autonomous_cycle import (AutonomousResearchCycle, generate_hypotheses,
                                       replication_gate)
from ..engine.autonomous_researcher import (PROTECTED as PROTECTED_KEYS,
                                            AutonomousResearcher, ResearchAction,
                                            validate as validate_action)
from ..services import load_draw_rows

router = APIRouter(prefix="/api/research", tags=["research"])


def _loads(raw: str | None) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


@router.get("/constitution")
def constitution():
    """The non-negotiable rules the research layer is held to (v3: 15 rules)."""
    return {
        "rules": RULES,
        "thresholds": {
            "minimum_improvement": MIN_IMPROVEMENT,
            "minimum_windows_won": MIN_WINDOWS_WON,
            "max_weight_delta_per_draw": MAX_WEIGHT_DELTA_PER_DRAW,
            "maximum_q_value": MAX_P_VALUE,
            "correction": "Benjamini-Hochberg (FDR)",
        },
    }


@router.get("/plan")
def plan(game_type: str, user: User = Depends(get_current_user)):
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    cfg = get_game(game_type)
    return {"plan": MasterAgent().plan(game_type),
            "models_under_study": MLResearcher().propose(cfg)}


@router.post("/run")
def run(game_type: str, windows: int = DEFAULT_WINDOWS,
        window_size: int = DEFAULT_WINDOW_SIZE, seed: int = 42,
        permutations: int = DEFAULT_PERMUTATIONS,
        perm_window: int = DEFAULT_PERM_WINDOW,
        include_ml_lab: bool = True,
        db: Session = Depends(get_db), user: User = Depends(get_current_admin)):
    """Run a full autonomous research cycle, protocol v3 (admin only — it is
    expensive: multi-window walk-forward plus temporal permutation tests)."""
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    cfg = get_game(game_type)
    if cfg.kind == "positional":
        raise HTTPException(status_code=400,
                            detail="El ciclo de investigación aplica a juegos de combinación.")
    windows = max(1, min(int(windows), 5))
    window_size = max(10, min(int(window_size), 80))
    permutations = max(0, min(int(permutations), 200))
    perm_window = max(5, min(int(perm_window), 60))
    history = [r["numbers"] for r in load_draw_rows(db, game_type)]
    if not history:
        raise HTTPException(status_code=400, detail="No hay sorteos cargados para este juego.")
    return run_research(db, cfg, history, windows=windows, window_size=window_size,
                        seed=seed, permutations=permutations, perm_window=perm_window,
                        include_ml_lab=include_ml_lab)


@router.get("/protocol")
def protocol():
    """The research protocol (v3) the cycle follows, points 3 to 8."""
    return {
        "version": "v3",
        "points": {
            "3": "Baselines separados: teórico, empírico exacto, de modelo y challengers. Nunca se mezclan.",
            "4": "Diagnósticos de por qué no aparece señal: uniformidad, autocorrelación, cambio de régimen y pair-lift.",
            "5": "Permutation testing temporal: se aleatoriza el orden de los sorteos conservando su composición.",
            "6": "Anti-p-hacking: hipótesis pre-registradas y corrección Benjamini-Hochberg.",
            "7": "Golden Holdout: 10% cronológico final, bloqueado e identificado por SHA-256.",
            "8": "Pipeline fijo de producción.",
        },
        "pre_registered_hypotheses": PRE_REGISTERED,
        "alpha": ALPHA,
        "minimum_improvement": MIN_IMPROVEMENT_V3,
    }


@router.get("/architecture")
def architecture():
    """The v4 pipeline, as data — the same flow the cycle actually executes."""
    lab = ClassicalMLLab()
    return {
        "version": "v4",
        "flow": [
            {"stage": "api_gateway", "detail": "MelatePro / Vercel → este backend"},
            {"stage": "autonomous_research_agent", "detail": "orquesta el ciclo completo"},
            {"stage": "statistical_lab", "detail": "χ² · información mutua · deriva · pares · change-point"},
            {"stage": "classical_ml_lab", "detail": "XGBoost · ExtraTrees · RandomForest · GradientBoosting",
             "availability": lab.available_models()},
            {"stage": "deep_learning_lab", "detail": "LSTM · Transformer",
             "availability": {c["name"]: c["status"] for c in DeepLearningLab().run()["challengers"]}},
            {"stage": "quantum_challenger", "detail": "red neuronal cuántica",
             "availability": {QuantumLab().run()["challenger"]["name"]:
                              QuantumLab().run()["challenger"]["status"]}},
            {"stage": "permutation_test", "detail": "aleatoriza el orden temporal"},
            {"stage": "block_bootstrap", "detail": "remuestreo por bloques contiguos"},
            {"stage": "multiple_testing", "detail": "Benjamini-Hochberg (FDR)"},
            {"stage": "golden_holdout", "detail": "10% final bloqueado con SHA-256"},
            {"stage": "confirmation_queue", "detail": f"replicación independiente ({REQUIRED_CONFIRMATIONS} corridas)"},
            {"stage": "champion_challenger", "detail": "promoción solo con evidencia replicada"},
            {"stage": "candidate_engine", "detail": "boletos + validación de riesgo"},
            {"stage": "melatepro", "detail": "la app consume los candidatos"},
        ],
        "note": ("Los challengers profundos y cuántico se declaran con su estado real. "
                 "El servicio web no entrena PyTorch dentro de una petición; eso vive en "
                 "un worker, y ningún laboratorio inventa métricas cuando no está disponible."),
    }


@router.get("/cycle-plan")
def cycle_plan(game_type: str, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """What the autonomous cycle would do right now — including doing nothing.

    With no new official draw there is no new evidence, so re-running would only
    multiply tests against the same data. The honest decision is WAIT.
    """
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    current = len(load_draw_rows(db, game_type))
    last = (db.query(Experiment)
            .filter(Experiment.game_type == game_type,
                    Experiment.model_name == "random_baseline")
            .order_by(Experiment.created_at.desc(), Experiment.id.desc())
            .first())
    last_draws = None
    if last:
        last_draws = _loads(last.params).get("draws_at_run")
    plan = AutonomousResearchCycle().plan(
        game_type, last_run_draws=last_draws, current_draws=current)
    recorded = [h.statement for h in
                db.query(Hypothesis).filter(Hypothesis.game_type == game_type).all()]
    return {
        **plan,
        "draws_now": current,
        "draws_at_last_run": last_draws,
        "open_hypotheses": generate_hypotheses(recorded),
        "replication_requirements": replication_gate(1.0, 1.0, 0.0, 1.0)["requires"],
    }


@router.get("/queue")
def queue(game_type: str | None = None, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """Candidates awaiting independent replication before becoming Champion."""
    return {
        "required_confirmations": REQUIRED_CONFIRMATIONS,
        "items": confirmation.listing(db, game_type),
        "note": ("Un modelo que pasa todas las compuertas no se promueve de inmediato: "
                 "debe repetir el resultado en corridas independientes."),
    }


@router.post("/worker-result")
def worker_result(payload: dict, db: Session = Depends(get_db),
                  user: User = Depends(get_current_admin)):
    """Register a Training Worker run as a CHALLENGER (never a Champion).

    The worker trains LSTM/Transformer/QNN outside HTTP and posts the result
    here. Promotion stays blocked: a training loss — or even an edge on one
    validation slice — is not evidence. It must still clear walk-forward,
    permutation, block bootstrap, multiple-testing correction, the Golden
    Holdout and independent replication.
    """
    game_type = str(payload.get("game") or payload.get("game_type") or "")
    model = str(payload.get("model") or "")
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    if model not in ("lstm", "transformer", "qnn"):
        raise HTTPException(status_code=400, detail="Modelo de worker inválido")
    status = str(payload.get("status") or "unknown")

    version = f"worker-{model}-{uuid.uuid4().hex[:8]}"
    row = ModelVersion(
        game_type=game_type, model_name=f"worker_{model}", version=version,
        role="challenger",                       # never "champion"
        score=float(payload.get("validation_mean_hits") or 0.0),
        baseline_score=float(payload.get("random_mean_hits") or 0.0),
        windows=0,
        metrics=json.dumps(payload, default=str),
        active=status == "trained",
    )
    db.add(row)
    db.add(Experiment(
        game_type=game_type,
        hypothesis=f"El challenger {model} del worker aporta ventaja sobre el azar",
        model_name=f"worker_{model}",
        params=json.dumps({"source": "training_worker",
                           "epochs": payload.get("epochs"),
                           "lookback": payload.get("lookback")}, default=str),
        metrics=json.dumps(payload, default=str),
        status="challenger",
        run_id=version,
    ))
    # v6 — a model card is written for every worker run, so its provenance is
    # on record even though it can never be promoted from here.
    card = model_cards.card_from_worker(payload, version)
    model_cards.persist(db, card, version)
    db.commit()
    return {
        "registered": True,
        "version": version,
        "role": "challenger",
        "promotion": "blocked_until_protocol_pass",
        "model_card": card.to_dict(),
        "stability_verdict": card.stability_verdict or None,
        "note": ("Registrado como challenger. La pérdida de entrenamiento y una ventaja "
                 "en una sola partición de validación no promueven nada: hace falta el "
                 "protocolo completo y replicación independiente."),
    }


@router.get("/worker-challengers")
def worker_challengers(game_type: str | None = None, limit: int = 20,
                       db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """Challengers published by the Training Worker."""
    q = db.query(ModelVersion).filter(ModelVersion.model_name.like("worker_%"))
    if game_type:
        q = q.filter(ModelVersion.game_type == game_type)
    rows = q.order_by(ModelVersion.promoted_at.desc(), ModelVersion.id.desc()).limit(limit).all()
    return {
        "items": [{
            "game_type": r.game_type, "model_name": r.model_name, "version": r.version,
            "role": r.role, "score": r.score, "baseline_score": r.baseline_score,
            "edge_vs_random": round((r.score or 0) - (r.baseline_score or 0), 4),
            "metrics": _loads(r.metrics), "created_at": r.promoted_at,
        } for r in rows],
        "note": ("Ningún resultado del worker puede ser Champion por sí solo; "
                 "la promoción exige el protocolo completo."),
    }


@router.get("/model-cards")
def model_cards_list(game_type: str | None = None, decision: str | None = None,
                     limit: int = 40, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Provenance record of every evaluated model: data, scores, gates, decision."""
    q = db.query(ModelCard)
    if game_type:
        q = q.filter(ModelCard.game_type == game_type)
    if decision:
        q = q.filter(ModelCard.decision == decision)
    rows = q.order_by(ModelCard.created_at.desc(), ModelCard.id.desc()).limit(min(limit, 200)).all()
    return {
        "items": [{
            "game_type": r.game_type, "model": r.model_name, "version": r.version,
            "role": r.role, "decision": r.decision,
            "data_snapshot": r.data_snapshot,
            "train_samples": r.train_samples, "validation_samples": r.validation_samples,
            "walk_forward_mean_hits": r.walk_forward_mean_hits,
            "random_baseline": r.random_baseline, "observed_delta": r.observed_delta,
            "permutation_p": r.permutation_p,
            "bootstrap_ci95": [r.bootstrap_low, r.bootstrap_high],
            "bh_q": r.bh_q, "golden_holdout_score": r.golden_holdout_score,
            "replication_passed": r.replication_passed,
            "looks_like_base_rate": r.looks_like_base_rate,
            "stability_verdict": r.stability_verdict,
            "extra": _loads(r.extra), "run_id": r.run_id, "created_at": r.created_at,
        } for r in rows],
        "note": ("Cada ficha explica por qué un modelo está donde está: qué datos vio, "
                 "cómo puntuó y qué compuerta lo detuvo."),
    }


@router.get("/researcher")
def researcher(game_type: str, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """What the autonomous researcher proposes — and what it is not allowed to do.

    The limit is enforced in code: every proposed action passes through a
    validator that rejects anything touching thresholds, the correction, the
    Golden Holdout or the Champion rules.
    """
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    recorded = [h.statement for h in
                db.query(Hypothesis).filter(Hypothesis.game_type == game_type).all()]
    return AutonomousResearcher(game_type).plan(recorded)


@router.post("/researcher/validate")
def researcher_validate(action: dict, user: User = Depends(get_current_admin)):
    """Check an arbitrary action against the researcher's authority.

    Exposed so the boundary can be tested from outside, not merely asserted.
    """
    ok, reason = validate_action(ResearchAction(
        kind=str(action.get("kind") or ""), payload=action.get("payload") or {}))
    return {"allowed": ok, "reason": reason,
            "protected": sorted(PROTECTED_KEYS)}


@router.get("/experiments")
def experiments(game_type: str | None = None, run_id: str | None = None,
                limit: int = 60, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    q = db.query(Experiment)
    if game_type:
        q = q.filter(Experiment.game_type == game_type)
    if run_id:
        q = q.filter(Experiment.run_id == run_id)
    rows = q.order_by(Experiment.created_at.desc(), Experiment.id.desc()).limit(min(limit, 200)).all()
    return [{
        "id": r.id, "game_type": r.game_type, "hypothesis": r.hypothesis,
        "model_name": r.model_name, "params": _loads(r.params),
        "metrics": _loads(r.metrics), "status": r.status, "run_id": r.run_id,
        "created_at": r.created_at,
    } for r in rows]


@router.get("/hypotheses")
def hypotheses(game_type: str | None = None, status: str | None = None,
               limit: int = 60, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Recorded hypotheses. Rejected ones are kept on purpose (rule 7)."""
    q = db.query(Hypothesis)
    if game_type:
        q = q.filter(Hypothesis.game_type == game_type)
    if status:
        q = q.filter(Hypothesis.status == status)
    rows = q.order_by(Hypothesis.created_at.desc(), Hypothesis.id.desc()).limit(min(limit, 200)).all()
    return [{
        "id": r.id, "game_type": r.game_type, "statement": r.statement,
        "status": r.status, "evidence": _loads(r.evidence), "run_id": r.run_id,
        "created_at": r.created_at,
    } for r in rows]


@router.get("/champion")
def champion(game_type: str, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    rows = (db.query(ModelVersion)
            .filter(ModelVersion.game_type == game_type)
            .order_by(ModelVersion.promoted_at.desc(), ModelVersion.id.desc())
            .limit(20).all())
    current = next((r for r in rows if r.role == "champion" and r.active), None)
    return {
        "game_type": game_type,
        "champion": ({
            "model_name": current.model_name, "version": current.version,
            "score": current.score, "baseline_score": current.baseline_score,
            "edge_vs_random": round((current.score or 0) - (current.baseline_score or 0), 4),
            "windows": current.windows, "metrics": _loads(current.metrics),
            "promoted_at": current.promoted_at,
        } if current else None),
        "history": [{
            "model_name": r.model_name, "version": r.version, "role": r.role,
            "score": r.score, "baseline_score": r.baseline_score,
            "windows": r.windows, "promoted_at": r.promoted_at,
        } for r in rows],
        "note": ("Sin campeón: ningún modelo ha superado al azar con evidencia "
                 "out-of-sample suficiente." if current is None else None),
    }
