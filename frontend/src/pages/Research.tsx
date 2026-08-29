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
  const [tab, setTab] = useState<"ciclo" | "hipotesis" | "reglas">("ciclo");

  const combinationGames = games.filter((g) => g.kind !== "positional");

  useEffect(() => {
    api.get<Constitution>("/research/constitution").then(setConstitution).catch(() => {});
  }, []);

  useEffect(() => {
    api.get<Hypothesis[]>(`/research/hypotheses?game_type=${game}&limit=40`).then(setHyps).catch(() => setHyps([]));
    api.get<Champion>(`/research/champion?game_type=${game}`).then(setChamp).catch(() => setChamp(null));
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
        {(["ciclo", "hipotesis", "reglas"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition ${
              tab === t ? "bg-white/15 text-white" : "bg-white/[0.05] text-white/50"
            }`}
          >
            {t === "ciclo" ? "Ciclo" : t === "hipotesis" ? "Hipótesis" : "Constitución"}
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

              <GlassCard className="!p-3">
                <p className="text-[11px] text-white/40 uppercase tracking-wide mb-2">Línea base del azar</p>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div>
                    <p className="text-lg font-bold tnum">{run.baseline?.mean_hits.toFixed(3)}</p>
                    <p className="text-[10px] text-white/40">azar medido</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold tnum">{run.baseline?.expected_random.toFixed(3)}</p>
                    <p className="text-[10px] text-white/40">esperado teórico</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold tnum">{run.tested_draws}</p>
                    <p className="text-[10px] text-white/40">sorteos probados</p>
                  </div>
                </div>
              </GlassCard>

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
                    Aceptado = supera el umbral, gana varias ventanas y es significativo (p &lt; 0.05)
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
