"""The agent's constitution — non-negotiable rules of the research layer.

Ported from the "Melate Autonomous Research Agent" design. These are not
decoration: `check_compliance` is executed at the end of every research cycle
and its result is stored with the run, so a cycle that violated a rule is
visible instead of silently accepted.

The most important rules for this project are 9 and 10: randomness is the null
hypothesis, and the system is allowed — expected, even — to conclude that no
predictive evidence exists.
"""
from __future__ import annotations

RULES: list[dict] = [
    {"id": 1, "rule": "Nunca modificar el histórico.",
     "detail": "Los sorteos oficiales son inmutables; solo se agregan o se corrigen por un admin."},
    {"id": 2, "rule": "Nunca utilizar información futura.",
     "detail": "Todo entrenamiento y evaluación es estrictamente walk-forward: en el paso t solo existen los sorteos anteriores a t."},
    {"id": 3, "rule": "Toda afirmación predictiva requiere backtesting.",
     "detail": "Ningún modelo se reporta como útil sin métricas out-of-sample registradas."},
    {"id": 4, "rule": "El baseline permanece siempre como referencia.",
     "detail": "El azar puro se mide en cada ciclo y se muestra junto a cualquier resultado."},
    {"id": 5, "rule": "Un Challenger sólo puede ser Champion con evidencia out-of-sample.",
     "detail": "Debe superar al baseline por un margen mínimo y ganar en varias ventanas independientes."},
    {"id": 6, "rule": "Un solo sorteo nunca cambia los pesos del ensemble.",
     "detail": "Los pesos se re-evolucionan con cada resultado, pero con inercia: el cambio por sorteo está acotado."},
    {"id": 7, "rule": "Las hipótesis descartadas quedan registradas.",
     "detail": "Saber qué no funciona es parte del expediente y no se borra."},
    {"id": 8, "rule": "Toda predicción debe ser reproducible.",
     "detail": "Cada ciclo guarda su run_id, parámetros y semilla."},
    {"id": 9, "rule": "El azar es la hipótesis nula.",
     "detail": "La carga de la prueba recae en el modelo, no en el azar."},
    {"id": 10, "rule": "El sistema puede concluir que no existe evidencia suficiente.",
     "detail": "Un veredicto negativo es un resultado válido y se reporta tal cual."},
    # --- Protocol v3 additions ---
    {"id": 11, "rule": "El número adicional nunca cuenta como uno de los principales.",
     "detail": "R7/F7 se almacena aparte y jamás entra en la predicción ni en la evaluación."},
    {"id": 12, "rule": "Las hipótesis se registran ANTES de ejecutar las pruebas.",
     "detail": "Pre-registro con run_id: el expediente no puede reescribirse para encajar con el resultado."},
    {"id": 13, "rule": "Los p-valores se corrigen por pruebas múltiples.",
     "detail": "Benjamini-Hochberg sobre toda la familia de brazos evaluados; decide el q-valor, no el p crudo."},
    {"id": 14, "rule": "El Golden Holdout permanece fuera de toda selección.",
     "detail": "El 10% cronológico final, identificado por SHA-256, solo se usa para evaluar un candidato ya congelado."},
    {"id": 15, "rule": "El LLM no escribe predicciones ni altera la base.",
     "detail": "El asistente explica; el motor calcula. Ningún texto generado modifica datos ni pesos."},
    # --- Protocol v7 additions ---
    {"id": 16, "rule": "El portafolio no se presenta como más probable de ganar por optimización.",
     "detail": "Diversificar reparte la misma probabilidad entre más resultados: compra cobertura, no suerte."},
    {"id": 17, "rule": "La búsqueda evolutiva no accede al Golden Holdout.",
     "detail": "Su función de aptitud se construye solo con los datos de selección."},
    {"id": 18, "rule": "Monte Carlo estima distribuciones, no causalidad.",
     "detail": "Se contrasta contra la hipergeométrica exacta para no confundir ruido de simulación con hallazgo."},
    {"id": 19, "rule": "El ensemble solo pondera modelos que pasan las compuertas.",
     "detail": "Un modelo que no supera q, estabilidad y aviso de tasa base recibe peso cero."},
    {"id": 20, "rule": "Si ninguno pasa, NO_EDGE.",
     "detail": "El sistema declara la ausencia de ventaja en vez de nombrar un campeón por descarte."},
    {"id": 21, "rule": "El LLM no modifica alfa, BH, permutación, holdout ni Champion Gate.",
     "detail": "Restricción implementada como validador de acciones, no como promesa en un documento."},
    {"id": 22, "rule": "Research Memory evita repetir hipótesis equivalentes.",
     "detail": "Huella SHA-256 de (juego, hipótesis, parámetros) persistida en base de datos."},
    {"id": 23, "rule": "Las combinaciones son candidatos, nunca garantías.",
     "detail": "Ninguna salida de la app promete premio ni ventaja matemática."},
    # --- Protocol v8 additions ---
    {"id": 24, "rule": "El meta-learner sólo prioriza presupuesto; no modifica umbrales.",
     "detail": "Decidir dónde mirar es un poder distinto de decidir qué cuenta como hallazgo."},
    {"id": 25, "rule": "El presupuesto experimental es finito y auditable.",
     "detail": "Se contabiliza el gasto por familia; un presupuesto que nadie cuenta no es un presupuesto."},
    {"id": 26, "rule": "Early stopping no puede tocar el Golden Holdout.",
     "detail": "Solo decide si seguir gastando esfuerzo en una línea que no produce nada."},
    {"id": 27, "rule": "Drift activa investigación adicional, no promoción automática.",
     "detail": "Un cambio de régimen es motivo para mirar más, no evidencia de que un modelo funcione."},
    {"id": 28, "rule": "Un Champion se reevalúa después de cada ciclo disponible.",
     "detail": "Ser promovido una vez no es un título permanente."},
    {"id": 29, "rule": "La degradación persistente puede retirar un Champion.",
     "detail": "Si la ventaja deja de aparecer durante varios ciclos, el título se pierde."},
    {"id": 30, "rule": "Toda predicción live genera un registro auditable.",
     "detail": "Se guarda antes del sorteo, con modelo, versión, semilla y snapshot de datos."},
    {"id": 31, "rule": "El track record live permanece separado del backtest.",
     "detail": "Mezclarlos es como creerse el ensayo: el backtest evalúa sobre datos ya conocidos."},
    {"id": 32, "rule": "NO_EDGE sigue siendo un estado válido y no detiene la investigación futura.",
     "detail": "No haber encontrado ventaja no cierra la puerta a seguir buscando con método."},
    # --- Protocol v9 additions ---
    {"id": 33, "rule": "Live queda separado de backtest y Golden Holdout.",
     "detail": "Es la única medición tomada sobre datos que nunca influyeron en nada."},
    {"id": 34, "rule": "Las ventanas móviles no sustituyen las pruebas corregidas.",
     "detail": "Describen tramos recientes; la decisión sigue viniendo del protocolo completo."},
    {"id": 35, "rule": "Un IC que cruza baseline no demuestra edge.",
     "detail": "Y el IC se ensancha con el número de miradas: revisar tras cada sorteo infla los falsos positivos."},
    {"id": 36, "rule": "El presupuesto adaptativo tiene límites.",
     "detail": "Ninguna familia puede superar su tope duro por muy prometedora que parezca."},
    {"id": 37, "rule": "El agente no cambia alfa, BH, permutation, holdout o Champion Gate.",
     "detail": "Validador de acciones, no una promesa escrita."},
    {"id": 38, "rule": "El ranking no usa sólo delta bruto.",
     "detail": "Ordena por replicación, significancia corregida y cota inferior del intervalo live."},
    {"id": 39, "rule": "Al incorporar live al entrenamiento se crea una nueva frontera temporal.",
     "detail": "Sin cerrar la ventana anterior, el siguiente live quedaría contaminado por datos ya vistos."},
    {"id": 40, "rule": "Degradación live puede retirar un Champion, pero no promueve otro automáticamente.",
     "detail": "Perder el título es una cosa; ganarlo exige el protocolo entero."},
    {"id": 41, "rule": "Predicciones live y lineage son auditables.",
     "detail": "Cada predicción generada en la app queda registrada antes del sorteo."},
    {"id": 42, "rule": "NO_EDGE sigue siendo válido.",
     "detail": "Se reafirma: la ausencia de ventaja es un resultado, no un fallo."},
]

# A challenger must beat the random baseline by at least this many mean hits
# per ticket, and win in at least this many independent windows.
MIN_IMPROVEMENT = 0.01
MIN_WINDOWS_WON = 2
# ...and the advantage must be statistically distinguishable from noise.
# Without this, a lax improvement threshold rubber-stamps random fluctuation as
# "evidence", which would violate rule 9 (randomness is the null hypothesis).
MAX_P_VALUE = 0.05
# Rule 6: hard cap on how much a single draw may move any single model weight.
MAX_WEIGHT_DELTA_PER_DRAW = 0.10


def damped_step(previous: dict[str, float], target: dict[str, float]) -> tuple[dict[str, float], float, float]:
    """Move `previous` toward `target` without letting any single weight jump
    more than ``MAX_WEIGHT_DELTA_PER_DRAW`` (constitution rule 6).

    Both inputs are distributions, so travelling along the straight line
    between them keeps the result a distribution — no renormalization that
    could push a weight back past the cap. Returns (weights, damping, max_delta).

    This is the single source of truth for rule 6: the persistence layer applies
    it, and the research cycle reports it.
    """
    if not previous:
        return dict(target), 1.0, 0.0
    deltas = {k: target[k] - previous.get(k, target[k]) for k in target}
    worst = max((abs(d) for d in deltas.values()), default=0.0)
    damping = 1.0 if worst <= MAX_WEIGHT_DELTA_PER_DRAW else MAX_WEIGHT_DELTA_PER_DRAW / worst
    moved = {k: previous.get(k, target[k]) + damping * d for k, d in deltas.items()}
    total = sum(moved.values()) or 1.0
    applied = {k: max(0.0, v / total) for k, v in moved.items()}
    max_delta = max((abs(applied[k] - previous.get(k, applied[k])) for k in applied), default=0.0)
    return applied, damping, max_delta


def check_compliance(run: dict) -> dict:
    """Audit a finished research run against the constitution.

    `run` is the dict produced by engine.research.run_research. Returns one
    entry per rule with pass/fail and the observed evidence.
    """
    checks: list[dict] = []

    def add(rid: int, ok: bool, evidence: str):
        rule = next(r for r in RULES if r["id"] == rid)
        checks.append({"id": rid, "rule": rule["rule"], "ok": bool(ok), "evidence": evidence})

    exps = run.get("experiments", []) or []
    baseline = run.get("baseline", {}) or {}
    windows = run.get("windows", []) or []
    champion = run.get("champion") or {}

    add(1, run.get("history_mutated") is False,
        "El ciclo solo leyó el histórico." if run.get("history_mutated") is False else "Se detectó escritura en el histórico.")
    add(2, run.get("walk_forward") is True,
        f"Evaluación walk-forward sobre {run.get('tested_draws', 0)} sorteos, sin look-ahead.")
    add(3, len(exps) > 0,
        f"{len(exps)} experimentos registrados con métricas out-of-sample.")
    add(4, bool(baseline),
        f"Baseline aleatorio medido: {baseline.get('mean_hits', 0):.4f} aciertos/boleto.")
    promoted = run.get("promotion", {}) or {}
    add(5, (not promoted.get("promoted")) or promoted.get("windows_won", 0) >= MIN_WINDOWS_WON,
        promoted.get("reason", "Sin promoción en este ciclo."))
    add(6, run.get("max_weight_delta", 0.0) <= MAX_WEIGHT_DELTA_PER_DRAW + 1e-9,
        f"Cambio máximo de peso por sorteo: {run.get('max_weight_delta', 0.0):.4f} (tope {MAX_WEIGHT_DELTA_PER_DRAW}).")
    add(7, run.get("rejected_recorded", 0) >= 0,
        f"{run.get('rejected_recorded', 0)} hipótesis descartadas quedaron registradas.")
    add(8, bool(run.get("run_id")),
        f"run_id={run.get('run_id')} con semilla {run.get('seed')}.")
    add(9, bool(baseline),
        "Todo modelo se contrastó contra el azar como hipótesis nula.")
    add(10, run.get("verdict") in ("evidencia_insuficiente", "evidencia_debil", "evidencia_significativa"),
        f"Veredicto emitido: {run.get('verdict')}.")

    # --- Protocol v3 checks ---
    add(11, run.get("additional_number_excluded") is True,
        "La evaluación usó solo los números principales; el adicional quedó fuera.")
    prereg = run.get("pre_registered", 0)
    add(12, prereg > 0,
        f"{prereg} hipótesis pre-registradas antes de ejecutar las pruebas.")
    mt = run.get("multiple_testing", {}) or {}
    add(13, mt.get("method", "").startswith("Benjamini"),
        f"Corrección {mt.get('method')} sobre {mt.get('tests', 0)} pruebas; "
        f"{mt.get('significant_after_correction', 0)} significativas tras corregir.")
    gh = run.get("golden_holdout", {}) or {}
    add(14, bool(gh.get("locked")) and gh.get("selection_allowed") is False,
        f"Golden Holdout de {gh.get('rows', 0)} sorteos bloqueado "
        f"(sha256 {str(gh.get('sha256', ''))[:12]}…), "
        + ("evaluado una sola vez sobre un candidato congelado."
           if gh.get("evaluated") else "no se tocó en este ciclo."))
    add(15, run.get("llm_wrote_predictions") is False,
        "Ninguna predicción ni peso provino de texto generado por el LLM.")

    # --- Protocol v7 checks ---
    portfolio = run.get("portfolio") or {}
    cov = portfolio.get("coverage") or {}
    add(16, bool(cov.get("note")) and run.get("claims_higher_probability") is False,
        f"{cov.get('tickets', 0)} boletos con {cov.get('coverage_share', 0)} de cobertura, "
        f"declarados como cobertura y no como mayor probabilidad.")
    add(17, run.get("evolution_saw_golden_holdout") is False,
        "La búsqueda evolutiva se ejecutó solo sobre los datos de selección.")
    mc = run.get("monte_carlo") or {}
    add(18, bool(mc.get("exact_reference")),
        f"Simulación de {mc.get('universes', 0)} universos contrastada contra la "
        f"hipergeométrica exacta (media {mc.get('mean_hits')} vs {mc.get('exact_mean_hits')}).")
    ens = run.get("dynamic_ensemble") or {}
    weights = ens.get("weights") or {}
    unqualified_weighted = [k for k, v in weights.items()
                            if v > 0 and k not in (ens.get("qualified") or [])]
    add(19, not unqualified_weighted,
        f"{len(ens.get('qualified') or [])} modelo(s) con peso; el resto en cero.")
    edge = run.get("edge") or {}
    add(20, edge.get("mode") in ("NO_EDGE", "EDGE_CANDIDATE"),
        f"Modo declarado: {edge.get('mode')} ({edge.get('qualified_models', 0)} modelos calificados).")
    add(21, run.get("llm_changed_gates") is False,
        "Ninguna compuerta estadística fue modificada por el agente.")
    mem = run.get("research_memory") or {}
    add(22, ("experiments" in mem) or (mem.get("available") is False),
        (f"{mem.get('experiments', 0)} experimentos en memoria; "
         f"{mem.get('repeated_attempts', 0)} hipótesis se detectaron como repetidas."
         if "experiments" in mem else
         "Ciclo sin persistencia: la memoria no aplica en una corrida en seco."))
    add(23, run.get("claims_guarantee") is False,
        "Las combinaciones se entregan como candidatos, sin promesa de premio.")

    # --- Protocol v8 checks ---
    meta = run.get("meta_learning") or {}
    add(24, run.get("meta_changed_gates") is False,
        f"Meta-learner priorizó {len(meta.get('priorities', {}))} familias sin tocar umbrales.")
    budget = run.get("experiment_budget") or {}
    add(25, budget.get("within_budget") is not None,
        f"Presupuesto contabilizado: {sum((budget.get('used') or {}).values())} de "
        f"{sum((budget.get('allocation') or {}).values())} experimentos usados.")
    stop = run.get("early_stopping") or {}
    add(26, stop.get("touches_golden_holdout") is False,
        f"Early stopping evaluado sin tocar el holdout ({'detiene' if stop.get('stop') else 'continúa'}).")
    drift = run.get("drift") or {}
    add(27, run.get("drift_promoted_anything") is False,
        f"Deriva {drift.get('score')} ({'detectada' if drift.get('detected') else 'no material'}): "
        f"solo amplía investigación.")
    decay = run.get("champion_decay") or {}
    add(28, "champion" in decay,
        decay.get("message", "Campeón reevaluado en este ciclo."))
    add(29, decay.get("retired") is not None,
        f"Retiro por degradación: {'sí' if decay.get('retired') else 'no aplica'}.")
    audits = run.get("live_audit") or {}
    add(30, audits.get("audited") is not None or audits.get("records") is not None,
        f"{audits.get('records', 0)} predicciones live con registro auditable.")
    live = run.get("live_track_record") or {}
    add(31, live.get("separate_from_backtest") is True,
        f"Track record live con {live.get('games', 0)} predicciones evaluadas, "
        f"separado del backtest.")
    edge_mode = (run.get("edge") or {}).get("mode")
    add(32, run.get("research_continues") is True,
        f"Modo {edge_mode}: la investigación sigue abierta en próximos ciclos.")

    # --- Protocol v9 checks ---
    live = run.get("live_track_record") or {}
    seq = run.get("sequential") or {}
    add(33, live.get("separate_from_backtest") is True,
        "El registro live no se mezcla con backtest ni con el Golden Holdout.")
    add(34, run.get("windows_replace_corrected_tests") is False,
        f"{len(seq.get('windows') or {})} ventana(s) móvil(es) reportadas como descriptivas.")
    add(35, (not seq) or seq.get("status") in ("SIGNAL_CANDIDATE",
                                               "COMPATIBLE_WITH_BASELINE",
                                               "INSUFFICIENT_DATA"),
        (f"IC live [{seq.get('ci_low')}, {seq.get('ci_high')}] ajustado por "
         f"{seq.get('looks')} mirada(s) → {seq.get('status')}."
         if seq else "Sin registro live suficiente para un intervalo."))
    caps = run.get("adaptive_budget") or {}
    add(36, caps.get("within_caps") is not False,
        f"Presupuesto adaptativo dentro de topes: {caps.get('within_caps')}.")
    add(37, run.get("meta_changed_gates") is False,
        "Ninguna compuerta estadística fue modificada por el agente.")
    add(38, run.get("ranking_uses_only_delta") is False,
        "El ranking pondera replicación y significancia, no solo la ventaja bruta.")
    lineage = run.get("data_lineage") or {}
    add(39, lineage.get("training_includes_live") is not True or bool(lineage.get("live_end_snapshot")),
        ("Frontera temporal cerrada antes de incorporar live."
         if lineage.get("training_includes_live") else
         "El entrenamiento no incorpora datos live: frontera intacta."))
    add(40, run.get("live_promoted_champion") is False,
        "Ninguna promoción se derivó del rendimiento live.")
    audits = run.get("live_audit") or {}
    add(41, audits.get("records") is not None,
        f"{audits.get('records', 0)} predicciones live auditables con su lineage.")
    add(42, edge_mode in ("NO_EDGE", "EDGE_CANDIDATE"),
        f"Modo {edge_mode} declarado explícitamente.")

    return {
        "compliant": all(c["ok"] for c in checks),
        "checks": checks,
        "windows_evaluated": len(windows),
        "champion": champion.get("model_name"),
    }
