import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { useGames } from "../hooks";
import { GameSelector } from "../components/GameSelector";
import { GlassCard, GlassButton, SectionTitle, Spinner } from "../components/ui";
import { getDefaultGame } from "../settings";

type Rule = { id: number; rule: string; detail: string };
type Constitution = {
  rules: Rule[];
  thresholds: {
    minimum_improvement: number;
    minimum_windows_won: number;
    max_weight_delta_per_draw: number;
  };
};
type Arm = {
  model_name: string;
  label: string;
  metrics: { mean_hits: number; hit_rate_3plus: number; hit_rate_4plus: number; max_hits: number; n: number };
  windows_won: number;
  edge_vs_random: number;
  significance: { p_value: number; significant: boolean; mean_diff: number };
  q_value?: number;
  significant_corrected?: boolean;
  lab?: string;
  accepted: boolean;
  reason: string;
};
type Run = {
  status: string;
  run_id?: string;
  message?: string;
  verdict?: string;
  verdict_text?: string;
  tested_draws?: number;
  draws?: number;
  selection_draws?: number;
  protocol_version?: string;
  baselines?: {
    teorico: { mean_hits: number; formula: string };
    empirico_exacto: { mean_hits: number; ci95_low: number; ci95_high: number; method: string };
    simulado_montecarlo: { mean_hits: number };
    de_modelo: Record<string, { mean_hits: number; edge_vs_random: number; q_value: number }>;
    nota: string;
  };
  diagnostics?: { reading: string; strongest_lag?: string; strongest_autocorrelation?: number; noise_threshold?: number };
  permutation_tests?: Record<string, { label?: string; observed_mean_hits?: number; null_mean_hits?: number; p_value?: number; q_value?: number; n_permutations?: number; error?: string }>;
  multiple_testing?: { method: string; alpha: number; tests: number; significant_after_correction: number };
  golden_holdout?: {
    rows: number; sha256: string; locked: boolean; evaluated?: boolean;
    split_rows?: Record<string, number>;
    evaluation?: { label: string; edge_vs_random: number; passed: boolean; note: string };
  };
  pre_registered_results?: Record<string, boolean>;
  labs?: {
    statistical: { signal_found: boolean; findings: string[] };
    classical_ml: { availability: Record<string, string>; evaluated: string[]; enabled: boolean };
    deep_learning: { challengers: { name: string; status: string; rationale: string }[] };
    quantum: { challenger: { name: string; status: string; rationale: string } };
  };
  block_bootstrap?: {
    draw_sums?: { ci95: number[]; observed: number };
    best_arm_hits?: null | { arm: string; ci95: number[]; excludes_random: boolean; random_baseline: number };
  };
  confirmation_queue?: null | { message: string; status: string; confirmations: number; required: number };
  replication_gate?: {
    passed: boolean;
    checks: Record<string, boolean>;
    missing: string[];
    requires: string[];
    reason: string;
  };
  cycle_states?: string[];
  baseline?: { mean_hits: number; expected_random: number };
  experiments?: Arm[];
  statistics?: { uniformity: { p_value: number; uniform: boolean; chi_square: number }; reading: string };
  data_audit?: { total: number; invalid_count: number; ok: boolean };
  promotion?: { promoted: boolean; reason: string };
  constitution?: { compliant: boolean; checks: { id: number; rule: string; ok: boolean; evidence: string }[] };
  candidates?: { accepted?: number[][]; accepted_count?: number; rejected?: Record<string, number> };
};
type Hypothesis = {
  id: number;
  statement: string;
  status: string;
  evidence: Record<string, unknown>;
  created_at: string;
};
type Architecture = {
  version: string;
  flow: { stage: string; detail: string; availability?: Record<string, string> }[];
  note: string;
};
type Queue = {
  required_confirmations: number;
  note: string;
  items: { game_type: string; model_name: string; status: string; confirmations: number; required: number }[];
};
type WorkerChallengers = {
  note: string;
  items: { game_type: string; model_name: string; version: string; role: string;
           edge_vs_random: number; metrics: Record<string, unknown> }[];
};
type Champion = {
  champion: null | { model_name: string; score: number; baseline_score: number; edge_vs_random: number; windows: number };
  note: string | null;
};

const VERDICT_STYLE: Record<string, { label: string; cls: string }> = {
  evidencia_significativa: { label: "Evidencia significativa", cls: "text-emerald-300 border-emerald-400/30 bg-emerald-500/10" },
  evidencia_debil: { label: "Evidencia débil (ruido)", cls: "text-amber-300 border-amber-400/30 bg-amber-500/10" },
  evidencia_insuficiente: { label: "Sin evidencia", cls: "text-rose-300 border-rose-400/30 bg-rose-500/10" },
};

export default function Research() {
  const { user } = useAuth();
  const { notify } = useToast();
  const games = useGames();
  const [game, setGame] = useState(getDefaultGame());
  const [constitution, setConstitution] = useState<Constitution | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [hyps, setHyps] = useState<Hypothesis[]>([]);
  const [champ, setChamp] = useState<Champion | null>(null);
  const [running, setRunning] = useState(false);
  const [tab, setTab] = useState<"ciclo" | "arquitectura" | "hipotesis" | "reglas">("ciclo");
  const [arch, setArch] = useState<Architecture | null>(null);
  const [queue, setQueue] = useState<Queue | null>(null);
  const [workers, setWorkers] = useState<WorkerChallengers | null>(null);

  const combinationGames = games.filter((g) => g.kind !== "positional");

  useEffect(() => {
    api.get<Constitution>("/research/constitution").then(setConstitution).catch(() => {});
    api.get<Architecture>("/research/architecture").then(setArch).catch(() => {});
  }, []);

  useEffect(() => {
    api.get<Hypothesis[]>(`/research/hypotheses?game_type=${game}&limit=40`).then(setHyps).catch(() => setHyps([]));
    api.get<Champion>(`/research/champion?game_type=${game}`).then(setChamp).catch(() => setChamp(null));
    api.get<Queue>(`/research/queue?game_type=${game}`).then(setQueue).catch(() => setQueue(null));
    api.get<WorkerChallengers>(`/research/worker-challengers?game_type=${game}`).then(setWorkers).catch(() => setWorkers(null));
  }, [game]);

  async function launch() {
    setRunning(true);
    setRun(null);
    try {
      const r = await api.post<Run>(`/research/run?game_type=${game}`, {});
      setRun(r);
      if (r.status === "insufficient_data") notify(r.message || "Historial insuficiente", "error");
      else notify("Ciclo de investigación completado", "success");
      api.get<Hypothesis[]>(`/research/hypotheses?game_type=${game}&limit=40`).then(setHyps).catch(() => {});
      api.get<Champion>(`/research/champion?game_type=${game}`).then(setChamp).catch(() => {});
      api.get<Queue>(`/research/queue?game_type=${game}`).then(setQueue).catch(() => {});
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setRunning(false);
    }
  }

  const verdict = run?.verdict ? VERDICT_STYLE[run.verdict] : null;

  return (
    <div className="space-y-4">
      <SectionTitle
        title="Investigación autónoma"
        subtitle="El sistema audita sus propios modelos contra el azar y puede concluir que no hay evidencia."
      />

      <GameSelector games={combinationGames} value={game} onChange={setGame} />

      <div className="flex gap-2">
        {(["ciclo", "arquitectura", "hipotesis", "reglas"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition ${
              tab === t ? "bg-white/15 text-white" : "bg-white/[0.05] text-white/50"
            }`}
          >
            {t === "ciclo" ? "Ciclo" : t === "arquitectura" ? "Arquitectura" : t === "hipotesis" ? "Hipótesis" : "Constitución"}
          </button>
        ))}
      </div>

      {tab === "ciclo" && (
        <div className="space-y-3">
          {champ && (
            <GlassCard className="!p-3">
              <p className="text-[11px] text-white/40 uppercase tracking-wide mb-1">Campeón vigente</p>
              {champ.champion ? (
                <div>
                  <p className="font-semibold">{champ.champion.model_name}</p>
                  <p className="text-xs text-white/60 tnum">
                    {champ.champion.score.toFixed(3)} aciertos/boleto · ventaja {champ.champion.edge_vs_random > 0 ? "+" : ""}
                    {champ.champion.edge_vs_random.toFixed(4)} · {champ.champion.windows} ventanas
                  </p>
                </div>
              ) : (
                <p className="text-xs text-white/60">{champ.note}</p>
              )}
            </GlassCard>
          )}

          {user?.is_admin ? (
            <GlassButton full size="lg" onClick={launch} disabled={running}>
              {running ? "Investigando… (puede tardar)" : "🔬 Ejecutar ciclo de investigación"}
            </GlassButton>
          ) : (
            <p className="text-xs text-white/40 px-1">
              Solo un administrador puede lanzar un ciclo. Abajo se muestra el expediente registrado.
            </p>
          )}

          {running && <Spinner label="Walk-forward sobre ventanas independientes…" />}

          {run?.status === "ok" && (
            <>
              {verdict && (
                <GlassCard className={`!p-4 border ${verdict.cls}`}>
                  <p className="text-[11px] uppercase tracking-wide opacity-70 mb-1">Veredicto</p>
                  <p className="font-bold text-base mb-1">{verdict.label}</p>
                  <p className="text-xs text-white/70 leading-relaxed">{run.verdict_text}</p>
                </GlassCard>
              )}

              {run.baselines && (
                <GlassCard className="!p-3">
                  <p className="text-[11px] text-white/40 uppercase tracking-wide mb-2">
                    Baselines separados <span className="text-white/25">· nunca se mezclan</span>
                  </p>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between">
                      <span className="text-white/60">Teórico ({run.baselines.teorico.formula})</span>
                      <span className="tnum font-semibold">{run.baselines.teorico.mean_hits.toFixed(4)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Empírico exacto (hipergeométrico)</span>
                      <span className="tnum font-semibold">{run.baselines.empirico_exacto.mean_hits.toFixed(4)}</span>
                    </div>
                    <div className="flex justify-between text-white/40">
                      <span>IC 95% de la media</span>
                      <span className="tnum">
                        {run.baselines.empirico_exacto.ci95_low.toFixed(3)} – {run.baselines.empirico_exacto.ci95_high.toFixed(3)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Simulado (una realización)</span>
                      <span className="tnum">{run.baselines.simulado_montecarlo.mean_hits.toFixed(4)}</span>
                    </div>
                    {Object.entries(run.baselines.de_modelo).map(([name, m]) => (
                      <div key={name} className="flex justify-between">
                        <span className="text-white/60">Modelo · {name}</span>
                        <span className="tnum">
                          {m.mean_hits.toFixed(3)} <span className="text-white/35">(q={m.q_value?.toFixed(2)})</span>
                        </span>
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-white/35 mt-2 leading-relaxed">{run.baselines.nota}</p>
                </GlassCard>
              )}

              {run.multiple_testing && (
                <GlassCard className="!p-3">
                  <p className="text-[11px] text-white/40 uppercase tracking-wide mb-1">
                    Corrección por pruebas múltiples
                  </p>
                  <p className="text-xs text-white/70 leading-relaxed">
                    {run.multiple_testing.method} sobre <span className="tnum">{run.multiple_testing.tests}</span> pruebas
                    (α={run.multiple_testing.alpha}):{" "}
                    <span className={run.multiple_testing.significant_after_correction > 0 ? "text-emerald-300" : "text-white/90"}>
                      {run.multiple_testing.significant_after_correction} significativas
                    </span>{" "}
                    tras corregir. Sin esto, probar {run.multiple_testing.tests} modelos a la vez fabrica un
                    "ganador" por puro azar.
                  </p>
                </GlassCard>
              )}

              {run.golden_holdout && (
                <GlassCard className="!p-3">
                  <p className="text-[11px] text-white/40 uppercase tracking-wide mb-1">
                    Golden Holdout · <span className="text-amber-300/80">bloqueado</span>
                  </p>
                  <p className="text-xs text-white/70 leading-relaxed">
                    <span className="tnum">{run.golden_holdout.rows}</span> sorteos finales (10%) reservados y fuera de
                    toda selección. Identidad SHA-256{" "}
                    <span className="tnum text-white/45">{run.golden_holdout.sha256.slice(0, 16)}…</span>
                  </p>
                  {run.golden_holdout.split_rows && (
                    <p className="text-[10px] text-white/35 mt-1 tnum">
                      train {run.golden_holdout.split_rows.train} · val {run.golden_holdout.split_rows.validation} ·
                      test {run.golden_holdout.split_rows.test} · golden {run.golden_holdout.split_rows.golden}
                    </p>
                  )}
                  <p className="text-[10px] text-white/50 mt-1.5">
                    {run.golden_holdout.evaluated
                      ? run.golden_holdout.evaluation?.note
                      : "No se tocó en este ciclo: ningún candidato llegó a la evaluación final."}
                  </p>
                </GlassCard>
              )}

              {run.labs && (
                <GlassCard className="!p-3">
                  <p className="text-[11px] text-white/40 uppercase tracking-wide mb-2">Laboratorios</p>
                  <div className="space-y-2 text-xs">
                    <div>
                      <p className="text-white/75 font-medium">
                        Estadístico ·{" "}
                        <span className={run.labs.statistical.signal_found ? "text-amber-300" : "text-white/50"}>
                          {run.labs.statistical.signal_found ? "señal detectada" : "sin señal"}
                        </span>
                      </p>
                      {run.labs.statistical.findings.map((f, i) => (
                        <p key={i} className="text-[10px] text-white/50 leading-relaxed">· {f}</p>
                      ))}
                    </div>
                    <div>
                      <p className="text-white/75 font-medium">
                        ML clásico · {run.labs.classical_ml.evaluated.length} challengers evaluados
                      </p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {Object.entries(run.labs.classical_ml.availability).map(([k, v]) => (
                          <span
                            key={k}
                            className={`text-[9px] px-1.5 py-0.5 rounded-md border ${
                              v === "disponible"
                                ? "text-emerald-300 border-emerald-400/25 bg-emerald-500/10"
                                : "text-white/35 border-white/10 bg-white/[0.04]"
                            }`}
                          >
                            {k}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-white/75 font-medium">Deep learning y cuántico</p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {[...run.labs.deep_learning.challengers, run.labs.quantum.challenger].map((c) => (
                          <span
                            key={c.name}
                            className={`text-[9px] px-1.5 py-0.5 rounded-md border ${
                              c.status === "disponible"
                                ? "text-emerald-300 border-emerald-400/25 bg-emerald-500/10"
                                : "text-white/35 border-white/10 bg-white/[0.04]"
                            }`}
                          >
                            {c.name}
                          </span>
                        ))}
                      </div>
                      <p className="text-[10px] text-white/35 mt-1 leading-relaxed">
                        No instalados en el servicio web: se declara su estado real en vez de reportar
                        métricas inventadas.
                      </p>
                    </div>
                  </div>
                </GlassCard>
              )}

              {run.block_bootstrap?.best_arm_hits && (
                <GlassCard className="!p-3">
                  <p className="text-[11px] text-white/40 uppercase tracking-wide mb-1">
                    Block bootstrap · mejor brazo
                  </p>
                  <p className="text-xs text-white/70 leading-relaxed">
                    IC 95% de aciertos:{" "}
                    <span className="tnum">
                      [{run.block_bootstrap.best_arm_hits.ci95[0]}, {run.block_bootstrap.best_arm_hits.ci95[1]}]
                    </span>{" "}
                    frente al azar {run.block_bootstrap.best_arm_hits.random_baseline}.{" "}
                    {run.block_bootstrap.best_arm_hits.excludes_random ? (
                      <span className="text-emerald-300">El intervalo excluye al azar.</span>
                    ) : (
                      <span className="text-amber-300">El intervalo contiene al azar: la ventaja no es sólida.</span>
                    )}
                  </p>
                </GlassCard>
              )}

              {run.replication_gate && (
                <GlassCard className="!p-3">
                  <p className="text-[11px] text-white/40 uppercase tracking-wide mb-2">
                    Compuerta de replicación ·{" "}
                    <span className={run.replication_gate.passed ? "text-emerald-300" : "text-white/60"}>
                      {run.replication_gate.passed ? "superada" : "no superada"}
                    </span>
                  </p>
                  <div className="space-y-1">
                    {Object.entries(run.replication_gate.checks).map(([k, ok]) => (
                      <div key={k} className="flex gap-2 text-[11px]">
                        <span className={ok ? "text-emerald-400" : "text-rose-400"}>{ok ? "✓" : "✕"}</span>
                        <span className="text-white/65">{k.replace(/_/g, " ")}</span>
                      </div>
                    ))}
                  </div>
                </GlassCard>
              )}

              {run.diagnostics?.reading && (
                <GlassCard className="!p-3">
                  <p className="text-[11px] text-white/40 uppercase tracking-wide mb-1">
                    Diagnóstico: ¿por qué no aparece señal?
                  </p>
                  <p className="text-xs text-white/70 leading-relaxed">{run.diagnostics.reading}</p>
                </GlassCard>
              )}

              {run.permutation_tests && Object.keys(run.permutation_tests).length > 0 && (
                <GlassCard className="!p-3">
                  <p className="text-[11px] text-white/40 uppercase tracking-wide mb-2">
                    Permutación temporal · ¿el orden de los sorteos informa?
                  </p>
                  <div className="space-y-1.5">
                    {Object.entries(run.permutation_tests).map(([k, v]) =>
                      v.error ? null : (
                        <div key={k} className="flex items-center justify-between text-xs">
                          <span className="text-white/70 truncate">{v.label || k}</span>
                          <span className="tnum text-white/50 shrink-0">
                            {v.observed_mean_hits?.toFixed(3)} vs {v.null_mean_hits?.toFixed(3)} · p=
                            {v.p_value?.toFixed(3)}
                          </span>
                        </div>
                      ),
                    )}
                  </div>
                  <p className="text-[10px] text-white/35 mt-2 leading-relaxed">
                    Se aleatoriza el orden cronológico conservando los números de cada sorteo. Si el resultado real cae
                    dentro de esa distribución, lo aprendido no dependía del tiempo.
                  </p>
                </GlassCard>
              )}

              {run.statistics && (
                <GlassCard className="!p-3">
                  <p className="text-[11px] text-white/40 uppercase tracking-wide mb-1">
                    Prueba de uniformidad (χ² = {run.statistics.uniformity.chi_square}, p ={" "}
                    {run.statistics.uniformity.p_value})
                  </p>
                  <p className="text-xs text-white/70 leading-relaxed">{run.statistics.reading}</p>
                </GlassCard>
              )}

              <GlassCard className="!p-0 overflow-hidden">
                <div className="p-3 border-b border-white/10">
                  <p className="text-xs font-semibold">Modelos contra el azar</p>
                  <p className="text-[10px] text-white/40">
                    Aceptado = supera el umbral, gana varias ventanas y sigue siendo significativo tras corregir por
                    pruebas múltiples (q &lt; 0.05)
                  </p>
                </div>
                <div className="max-h-[420px] overflow-y-auto divide-y divide-white/5">
                  {run.experiments?.map((a) => (
                    <div key={a.model_name} className="p-3 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{a.label}</p>
                        <p className="text-[10px] text-white/45 tnum">
                          {a.metrics.mean_hits.toFixed(3)} aciertos · ventaja {a.edge_vs_random > 0 ? "+" : ""}
                          {a.edge_vs_random.toFixed(4)} · {a.windows_won} vent. · p={a.significance.p_value.toFixed(3)}
                          {a.q_value !== undefined && (
                            <span className="text-white/60"> · q={a.q_value.toFixed(3)}</span>
                          )}
                        </p>
                      </div>
                      <span
                        className={`shrink-0 text-[10px] px-2 py-1 rounded-lg border ${
                          a.accepted
                            ? "text-emerald-300 border-emerald-400/30 bg-emerald-500/10"
                            : "text-white/45 border-white/10 bg-white/[0.04]"
                        }`}
                      >
                        {a.accepted ? "aceptado" : "rechazado"}
                      </span>
                    </div>
                  ))}
                </div>
              </GlassCard>

              {run.constitution && (
                <GlassCard className="!p-3">
                  <p className="text-[11px] text-white/40 uppercase tracking-wide mb-2">
                    Auditoría de la constitución ·{" "}
                    <span className={run.constitution.compliant ? "text-emerald-300" : "text-rose-300"}>
                      {run.constitution.compliant ? "cumple" : "incumple"}
                    </span>
                  </p>
                  <div className="space-y-1.5">
                    {run.constitution.checks.map((c) => (
                      <div key={c.id} className="flex gap-2 text-[11px]">
                        <span className={c.ok ? "text-emerald-400" : "text-rose-400"}>{c.ok ? "✓" : "✕"}</span>
                        <span className="text-white/70">
                          <span className="text-white/90">{c.rule}</span>{" "}
                          <span className="text-white/40">{c.evidence}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </GlassCard>
              )}
            </>
          )}

          {run?.status === "insufficient_data" && (
            <GlassCard className="!p-3">
              <p className="text-xs text-white/70">{run.message}</p>
            </GlassCard>
          )}
        </div>
      )}

      {tab === "arquitectura" && (
        <div className="space-y-2">
          {queue && (
            <GlassCard className="!p-3">
              <p className="text-[11px] text-white/40 uppercase tracking-wide mb-1">
                Cola de confirmación · requiere {queue.required_confirmations} corridas independientes
              </p>
              {queue.items.length === 0 ? (
                <p className="text-xs text-white/60">
                  Vacía: ningún candidato ha superado todas las compuertas todavía.
                </p>
              ) : (
                <div className="space-y-1.5">
                  {queue.items.map((it) => (
                    <div key={it.model_name} className="flex items-center justify-between text-xs">
                      <span className="text-white/75">{it.model_name}</span>
                      <span className="tnum text-white/50">
                        {it.confirmations}/{it.required} · {it.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-white/35 mt-2 leading-relaxed">{queue.note}</p>
            </GlassCard>
          )}

          {workers && (
            <GlassCard className="!p-3">
              <p className="text-[11px] text-white/40 uppercase tracking-wide mb-1">
                Training Worker · challengers publicados
              </p>
              {workers.items.length === 0 ? (
                <p className="text-xs text-white/60">
                  Ninguno todavía. El worker entrena LSTM/Transformer/QNN fuera del servicio web
                  y publica el resultado aquí como challenger.
                </p>
              ) : (
                <div className="space-y-1.5">
                  {workers.items.map((w) => (
                    <div key={w.version} className="flex items-center justify-between text-xs">
                      <span className="text-white/75">{w.model_name.replace("worker_", "")}</span>
                      <span className="tnum text-white/50">
                        ventaja {w.edge_vs_random > 0 ? "+" : ""}
                        {w.edge_vs_random.toFixed(4)} · {w.role}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-white/35 mt-2 leading-relaxed">{workers.note}</p>
            </GlassCard>
          )}

          {arch && (
            <GlassCard className="!p-0 overflow-hidden">
              <div className="p-3 border-b border-white/10">
                <p className="text-xs font-semibold">Pipeline {arch.version}</p>
                <p className="text-[10px] text-white/40">El orden que el ciclo ejecuta de verdad</p>
              </div>
              <div className="divide-y divide-white/5">
                {arch.flow.map((s, i) => (
                  <div key={s.stage} className="p-3">
                    <div className="flex items-start gap-2">
                      <span className="text-[10px] text-white/30 tnum mt-0.5 w-5 shrink-0">{i + 1}</span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{s.stage.replace(/_/g, " ")}</p>
                        <p className="text-[11px] text-white/50 leading-relaxed">{s.detail}</p>
                        {s.availability && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {Object.entries(s.availability).map(([k, v]) => (
                              <span
                                key={k}
                                className={`text-[9px] px-1.5 py-0.5 rounded-md border ${
                                  v === "disponible"
                                    ? "text-emerald-300 border-emerald-400/25 bg-emerald-500/10"
                                    : "text-white/40 border-white/10 bg-white/[0.04]"
                                }`}
                              >
                                {k}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-white/35 p-3 border-t border-white/10 leading-relaxed">{arch.note}</p>
            </GlassCard>
          )}
        </div>
      )}

      {tab === "hipotesis" && (
        <div className="space-y-2">
          <p className="text-[11px] text-white/40 px-1">
            Las hipótesis descartadas se conservan a propósito: saber qué no funciona es parte del expediente.
          </p>
          {hyps.length === 0 && <p className="text-xs text-white/40 px-1">Aún no hay hipótesis registradas.</p>}
          {hyps.map((h) => (
            <GlassCard key={h.id} className="!p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm leading-snug">{h.statement}</p>
                <span
                  className={`shrink-0 text-[10px] px-2 py-1 rounded-lg border ${
                    h.status === "confirmada"
                      ? "text-emerald-300 border-emerald-400/30 bg-emerald-500/10"
                      : "text-rose-300/80 border-rose-400/20 bg-rose-500/10"
                  }`}
                >
                  {h.status}
                </span>
              </div>
              {typeof h.evidence?.reason === "string" && (
                <p className="text-[10px] text-white/45 mt-1.5 leading-relaxed">{h.evidence.reason as string}</p>
              )}
            </GlassCard>
          ))}
        </div>
      )}

      {tab === "reglas" && constitution && (
        <div className="space-y-2">
          <GlassCard className="!p-3">
            <p className="text-[11px] text-white/40 uppercase tracking-wide mb-1">Umbrales de promoción</p>
            <p className="text-xs text-white/70 tnum">
              mejora mínima {constitution.thresholds.minimum_improvement} · ventanas mínimas{" "}
              {constitution.thresholds.minimum_windows_won} · cambio máx. de peso por sorteo{" "}
              {constitution.thresholds.max_weight_delta_per_draw}
            </p>
          </GlassCard>
          {constitution.rules.map((r) => (
            <GlassCard key={r.id} className="!p-3">
              <p className="text-sm font-medium">
                <span className="text-white/40 tnum mr-1.5">{r.id}.</span>
                {r.rule}
              </p>
              <p className="text-[11px] text-white/50 mt-1 leading-relaxed">{r.detail}</p>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
}
