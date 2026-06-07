import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useGames } from "../hooks";
import { PageHeader, Disclaimer } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, SectionTitle, gameTheme } from "../components/ui";
import { GameSelector } from "../components/GameSelector";
import { BarList, VBars, AreaChart } from "../components/Charts";
import { useToast } from "../context/ToastContext";

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
interface Analytics {
  strategies: Strat[];
  evolution: EvoPoint[];
  learning_events: number;
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
  const [game, setGame] = useState("melate");
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);

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
