import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useGames } from "../hooks";
import { PageHeader, Disclaimer } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, SectionTitle, gameTheme } from "../components/ui";
import { GameSelector } from "../components/GameSelector";
import { BarList, VBars, AreaChart } from "../components/Charts";
import { NumberHeatmap, HeatLegend } from "../components/NumberHeatmap";
import { NumberBall } from "../components/NumberBall";
import { useToast } from "../context/ToastContext";
import { getDefaultGame } from "../settings";

interface Probs {
  backend: string;
  trained: boolean;
  kind?: string;
  numbers: { number: number; prob: number; rel: number }[];
  top: { number: number; prob: number; rel: number }[];
  positions?: { position: number; top: number; digits: { digit: number; prob: number; rel: number }[] }[];
}

interface Strat {
  strategy: string;
  label: string;
  total_predictions: number;
  average_hits: number;
  best_hits: number;
  weight: number;
  normalized_weight: number;
}
interface EvoPoint { i: number; cum_avg_hits: number; weight: number; strategy: string; hits: number; }
interface CtxBlock { context: string; strategies: { strategy: string; weight: number; normalized: number; evaluations: number; average_hits: number }[]; }
interface Analytics {
  strategies: Strat[];
  evolution: EvoPoint[];
  learning_events: number;
  current_context: string | null;
  contextual: CtxBlock[];
  user: {
    hits_distribution: Record<string, number>;
    timeline: { date: string; avg_hits: number; count: number }[];
    total_predictions: number;
    total_evaluations: number;
    average_hits: number;
    best_hits: number;
  };
}

const BT_STRATS = ["conservadora", "balanceada", "agresiva", "hibrida", "anti_popular"];

export default function Analytics() {
  const games = useGames();
  const nav = useNavigate();
  const { notify } = useToast();
  const [game, setGame] = useState(getDefaultGame());
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);

  const [probs, setProbs] = useState<Probs | null>(null);
  const [probsLoading, setProbsLoading] = useState(false);
  const [bt, setBt] = useState<{ strategy: string; avg: number; random: number; edge: number; best: number }[]>([]);
  const [btRunning, setBtRunning] = useState(false);
  const [btProgress, setBtProgress] = useState(0);

  async function load() {
    setLoading(true);
    try {
      setData(await api.get<Analytics>(`/ml/analytics?game_type=${game}`));
    } finally {
      setLoading(false);
    }
  }
  async function loadProbs() {
    setProbsLoading(true);
    setProbs(null);
    try {
      setProbs(await api.get<Probs>(`/ml/probabilities?game_type=${game}`));
    } catch {
      /* insufficient history etc. */
    } finally {
      setProbsLoading(false);
    }
  }
  useEffect(() => {
    loadProbs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game]);
  useEffect(() => {
    load();
    setBt([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game]);

  async function runBacktests() {
    setBtRunning(true);
    setBt([]);
    setBtProgress(0);
    const out: typeof bt = [];
    try {
      for (let i = 0; i < BT_STRATS.length; i++) {
        const s = BT_STRATS[i];
        const r = await api.post<any>("/backtesting", {
          game_type: game, strategy: s, last_n: 25, combos_per_draw: 3, cost_per_combination: 21,
        });
        out.push({ strategy: s, avg: r.average_hits, random: r.random_average_hits, edge: r.edge_vs_random, best: r.best_hits });
        setBt([...out]);
        setBtProgress(Math.round(((i + 1) / BT_STRATS.length) * 100));
      }
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setBtRunning(false);
    }
  }

  const dist = data ? Array.from({ length: 7 }, (_, i) => data.user.hits_distribution[String(i)] || 0) : [];

  return (
    <>
      <PageHeader
        title="Rendimiento"
        subtitle="Desempeño y evolución de la IA"
        right={<button onClick={() => nav("/")} className="glass rounded-2xl px-3 py-2 text-xs font-semibold active:scale-95">← Inicio</button>}
      />
      <div className="mb-4">
        <GameSelector games={games} value={game} onChange={setGame} />
      </div>

      {loading || !data ? (
        <Spinner />
      ) : (
        <div className="space-y-5 animate-fade-in">
          {/* ML per-number probabilities */}
          <GlassCard glow>
            <SectionTitle
              title="🔮 Probabilidades del modelo IA"
              subtitle={probs ? `Motor: ${probs.backend}${probs.trained ? "" : " (heurístico)"}` : "Probabilidad de aparición por número"}
            />
            {probsLoading ? (
              <Spinner label="Calculando con el modelo…" />
            ) : !probs ? (
              <p className="text-center text-xs text-white/30 py-4">Sin datos suficientes.</p>
            ) : probs.kind === "positional" && probs.positions ? (
              <div className="space-y-3">
                <p className="text-[11px] text-white/55">Dígito más probable por posición (la posición importa en Tris):</p>
                {probs.positions.map((p) => {
                  const mx = Math.max(...p.digits.map((d) => d.prob));
                  return (
                    <div key={p.position} className="bg-white/[0.04] rounded-2xl p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-white/70">Posición {p.position}</span>
                        <span className="text-[10px] text-white/40">top: <b className="text-white/80">{p.top}</b></span>
                      </div>
                      <div className="flex gap-0.5 items-end h-12">
                        {p.digits.sort((a, b) => a.digit - b.digit).map((d) => (
                          <div key={d.digit} className="flex-1 flex flex-col items-center justify-end">
                            <span className="text-[8px] text-white/40 tnum mb-0.5">{(d.prob * 100).toFixed(0)}</span>
                            <div className="w-full rounded-sm bg-gradient-to-t from-lime-400 to-emerald-500" style={{ height: `${(d.prob / mx) * 100}%`, minHeight: 2 }} />
                            <span className="text-[8px] text-white/40 tnum mt-0.5">{d.digit}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
                <p className="text-[10px] text-white/35 text-center">El modelo estima probabilidades por posición; Tris sigue siendo azar.</p>
              </div>
            ) : (
              <>
                <p className="text-[11px] text-white/55 mb-2">Top {probs.top.length} números más probables (modelo):</p>
                <div className="flex gap-1.5 flex-wrap justify-center mb-4">
                  {probs.top.map((t, i) => (
                    <div key={t.number} className="flex flex-col items-center">
                      <NumberBall n={t.number} size="sm" variant="gold" index={i} />
                      <span className="text-[9px] text-white/40 mt-0.5 tnum">{(t.prob * 100).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
                <p className="text-[11px] text-white/55 mb-2">Mapa de calor (todos los números):</p>
                <NumberHeatmap items={probs.numbers} highlight={probs.top.map((t) => t.number)} />
                <HeatLegend />
                <p className="text-[10px] text-white/35 mt-3 text-center">El modelo estima probabilidades relativas; la lotería sigue siendo azar.</p>
              </>
            )}
          </GlassCard>

          {/* Contextual learning */}
          {data.contextual.length > 0 && (
            <GlassCard>
              <SectionTitle title="🧭 Aprendizaje contextual" subtitle={`Régimen actual: ${data.current_context ?? "—"}`} />
              <div className="space-y-3">
                {data.contextual.map((cb) => (
                  <div key={cb.context} className={`rounded-2xl p-3 ${cb.context === data.current_context ? "bg-gradient-to-br from-violet-600/25 to-cyan-500/15 border border-white/15" : "bg-white/[0.04]"}`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold">{cb.context}{cb.context === data.current_context && <span className="ml-2 text-[9px] px-1.5 py-0.5 rounded bg-cyan-500/25 text-cyan-200">ACTUAL</span>}</span>
                      <span className="text-[10px] text-white/40">mejor: {cb.strategies[0]?.strategy}</span>
                    </div>
                    <BarList items={cb.strategies.slice(0, 4).map((s) => ({ label: s.strategy.replace("_", " "), value: s.normalized * 100, sub: `${s.evaluations} eval` }))} format={(v) => `${v.toFixed(0)}%`} accent="from-fuchsia-500 to-cyan-400" />
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {/* AI learning over time */}
          <GlassCard>
            <SectionTitle title="🧠 Evolución del aprendizaje" subtitle={`${data.learning_events} eventos de aprendizaje (refuerzo)`} />
            {data.evolution.length > 0 ? (
              <>
                <p className="text-[11px] text-white/50 mb-1">Aciertos promedio acumulados del sistema</p>
                <AreaChart points={data.evolution.map((e) => ({ x: String(e.i), y: e.cum_avg_hits }))} />
              </>
            ) : (
              <p className="text-center text-xs text-white/30 py-4">El sistema aún no registra eventos de aprendizaje. Aparecen cuando el admin carga resultados oficiales.</p>
            )}
            <p className="text-[11px] text-white/50 mt-3 mb-2">Confianza actual por estrategia</p>
            <BarList
              items={data.strategies.map((s) => ({ label: s.label, value: s.normalized_weight * 100, sub: `${s.total_predictions} eval` }))}
              format={(v) => `${v.toFixed(1)}%`}
              accent="from-violet-500 to-fuchsia-400"
            />
          </GlassCard>

          {/* Avg hits per strategy */}
          <GlassCard>
            <SectionTitle title="🎯 Aciertos promedio por estrategia" subtitle="Histórico evaluado del sistema" />
            <BarList
              items={data.strategies.map((s) => ({ label: s.label, value: s.average_hits, sub: `mejor ${s.best_hits}✓` }))}
              format={(v) => v.toFixed(2)}
              accent="from-emerald-500 to-cyan-400"
            />
          </GlassCard>

          {/* User accuracy timeline */}
          <GlassCard>
            <SectionTitle title="📈 Tu precisión en el tiempo" subtitle={`${data.user.total_evaluations} evaluaciones · prom ${data.user.average_hits} · mejor ${data.user.best_hits}✓`} />
            <AreaChart points={data.user.timeline.map((t) => ({ x: t.date, y: t.avg_hits }))} />
          </GlassCard>

          {/* Hits distribution */}
          <GlassCard>
            <SectionTitle title="📊 Distribución de tus aciertos" />
            {data.user.total_evaluations === 0 ? (
              <p className="text-center text-xs text-white/30 py-6">Aún no tienes predicciones evaluadas. Guarda predicciones y espera a que el admin cargue resultados.</p>
            ) : (
              <VBars data={dist} labels={["0", "1", "2", "3", "4", "5", "6"]} highlightFrom={3} />
            )}
          </GlassCard>

          {/* Backtest comparison */}
          <GlassCard>
            <SectionTitle title="⚔️ Comparativa de estrategias vs azar" subtitle="Backtest sobre sorteos reales (últimos 25)" />
            <GlassButton full variant="ghost" onClick={runBacktests} disabled={btRunning} className="mb-3">
              {btRunning ? `Simulando… ${btProgress}%` : "▶ Ejecutar comparativa"}
            </GlassButton>
            {btRunning && <div className="h-1.5 rounded-full bg-white/10 overflow-hidden mb-3"><div className="h-full bg-gradient-to-r from-violet-500 to-cyan-400" style={{ width: `${btProgress}%` }} /></div>}
            {bt.length > 0 && (
              <>
                <p className="text-[11px] text-white/50 mb-2">Aciertos promedio (estrategia)</p>
                <BarList items={bt.map((b) => ({ label: b.strategy.replace("_", " "), value: b.avg, sub: `azar ${b.random}` }))} format={(v) => v.toFixed(3)} accent="from-amber-400 to-orange-500" />
                <p className="text-[11px] text-white/50 mt-4 mb-2">Ventaja vs azar (edge)</p>
                <BarList items={bt.map((b) => ({ label: b.strategy.replace("_", " "), value: Math.max(0, b.edge) }))} format={(v) => (v > 0 ? `+${v.toFixed(3)}` : v.toFixed(3))} accent="from-emerald-500 to-teal-400" />
              </>
            )}
          </GlassCard>

          <Disclaimer />
        </div>
      )}
    </>
  );
}
