import { useState } from "react";
import { api } from "../api/client";
import { useGames, useStrategies } from "../hooks";
import { PageHeader, Disclaimer } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, SectionTitle, Capsule } from "../components/ui";
import { GameSelector } from "../components/GameSelector";
import { useToast } from "../context/ToastContext";

interface Scenario {
  hits: number;
  probability_single: number;
  odds_one_in: number | null;
  probability_any_in_set: number;
  prize_estimate: number;
  expected_return: number;
  net_if_hit: number;
  roi_if_hit_percent: number | null;
}
interface Estimate {
  game_label: string;
  combinations: number;
  total_cost: number;
  scenarios: Scenario[];
  expected_total_return: number;
  expected_roi_percent: number | null;
  jackpot_odds_one_in: number;
  jackpot_probability_any: number;
  risk: string;
  disclaimer: string;
}

const fmt = (n: number) => new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 }).format(n);
const money = (n: number) => "$" + new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 }).format(n);

export default function Earnings() {
  const games = useGames();
  const strategies = useStrategies();
  const { notify } = useToast();

  const [game, setGame] = useState("melate");
  const [combinations, setCombinations] = useState(10);
  const [cost, setCost] = useState(21);
  const [prizes, setPrizes] = useState<Record<number, string>>({});
  const [est, setEst] = useState<Estimate | null>(null);
  const [loading, setLoading] = useState(false);

  const [strategy, setStrategy] = useState("hibrida");
  const [backtest, setBacktest] = useState<any>(null);
  const [btLoading, setBtLoading] = useState(false);

  async function estimate() {
    setLoading(true);
    try {
      const custom: Record<string, number> = {};
      Object.entries(prizes).forEach(([k, v]) => {
        if (v) custom[k] = parseFloat(v);
      });
      const res = await api.post<Estimate>("/earnings/estimate", {
        game_type: game,
        combinations,
        cost_per_combination: cost,
        custom_prizes: Object.keys(custom).length ? custom : undefined,
      });
      setEst(res);
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setLoading(false);
    }
  }

  async function runBacktest() {
    setBtLoading(true);
    setBacktest(null);
    try {
      const res = await api.post("/backtesting", {
        game_type: game,
        strategy,
        last_n: 50,
        combos_per_draw: combinations > 10 ? 10 : combinations,
        cost_per_combination: cost,
      });
      setBacktest(res);
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setBtLoading(false);
    }
  }

  return (
    <>
      <PageHeader title="Estimador" subtitle="Ganancias, probabilidad y ROI" />
      <Disclaimer />

      <GlassCard className="space-y-4 mb-5">
        <div>
          <SectionTitle title="Tipo de sorteo" />
          <GameSelector games={games} value={game} onChange={setGame} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-white/50 ml-1">Combinaciones</label>
            <input type="number" min={1} value={combinations} onChange={(e) => setCombinations(Math.max(1, parseInt(e.target.value) || 1))} className="glass-input w-full mt-1 tnum" />
          </div>
          <div>
            <label className="text-xs text-white/50 ml-1">Costo c/u (MXN)</label>
            <input type="number" min={0} value={cost} onChange={(e) => setCost(Math.max(0, parseFloat(e.target.value) || 0))} className="glass-input w-full mt-1 tnum" />
          </div>
        </div>
        <div>
          <label className="text-xs text-white/50 ml-1">Premios estimados (editable, opcional)</label>
          <div className="grid grid-cols-5 gap-1.5 mt-1">
            {[2, 3, 4, 5, 6].map((h) => (
              <input
                key={h}
                value={prizes[h] || ""}
                onChange={(e) => setPrizes((p) => ({ ...p, [h]: e.target.value }))}
                placeholder={`${h}✓`}
                className="glass-input !px-2 !py-2 text-center text-xs tnum"
                inputMode="numeric"
              />
            ))}
          </div>
        </div>
        <GlassButton full size="lg" onClick={estimate} disabled={loading}>
          {loading ? "Calculando…" : "💰 Estimar"}
        </GlassButton>
      </GlassCard>

      {est && (
        <div className="space-y-4 animate-slide-up">
          <div className="grid grid-cols-2 gap-3">
            <GlassCard className="!p-4 text-center">
              <p className="text-2xl font-extrabold tnum text-rose-300">{money(est.total_cost)}</p>
              <p className="text-xs text-white/50 mt-1">Gasto total</p>
            </GlassCard>
            <GlassCard className="!p-4 text-center">
              <p className="text-2xl font-extrabold tnum text-cyan-300">{est.expected_roi_percent}%</p>
              <p className="text-xs text-white/50 mt-1">ROI esperado</p>
            </GlassCard>
          </div>

          <GlassCard>
            <SectionTitle title="Tabla de escenarios" subtitle="Probabilidad por nivel de aciertos" />
            <div className="space-y-2">
              {est.scenarios.map((s) => (
                <div key={s.hits} className="flex items-center justify-between bg-white/[0.04] rounded-2xl px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center text-xs font-bold">{s.hits}✓</span>
                    <div>
                      <p className="text-xs text-white/50">1 en {s.odds_one_in ? fmt(s.odds_one_in) : "—"}</p>
                      <p className="text-[10px] text-white/35">P(alguna): {(s.probability_any_in_set * 100).toFixed(4)}%</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold tnum">{money(s.prize_estimate)}</p>
                    <p className="text-[10px] text-white/40">premio est.</p>
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>

          <GlassCard className="border-amber-400/20">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-white/60">Jackpot (6 aciertos)</span>
              <span className="text-sm font-bold tnum text-amber-300">1 en {fmt(est.jackpot_odds_one_in)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-white/60">Riesgo</span>
              <span className="text-xs text-rose-200 text-right max-w-[60%]">{est.risk}</span>
            </div>
          </GlassCard>

          {/* Backtest / comparación contra azar */}
          <GlassCard>
            <SectionTitle title="Simulación vs azar" subtitle="Backtest de la estrategia en sorteos reales" />
            <div className="flex gap-2 overflow-x-auto no-scrollbar pb-2">
              {strategies.map((s) => (
                <Capsule key={s.key} active={strategy === s.key} onClick={() => setStrategy(s.key)}>
                  {s.label}
                </Capsule>
              ))}
            </div>
            <GlassButton full variant="ghost" onClick={runBacktest} disabled={btLoading} className="mt-2">
              {btLoading ? "Simulando últimos 50 sorteos…" : "▶ Ejecutar backtesting"}
            </GlassButton>

            {btLoading && <Spinner />}
            {backtest && !backtest.error && (
              <div className="mt-4 space-y-3 animate-fade-in">
                <div className="grid grid-cols-3 gap-2 text-center">
                  <BT label="Aciertos prom." value={backtest.average_hits} hl />
                  <BT label="Azar prom." value={backtest.random_average_hits} />
                  <BT label="Ventaja" value={`${backtest.edge_vs_random > 0 ? "+" : ""}${backtest.edge_vs_random}`} hl={backtest.edge_vs_random > 0} />
                  <BT label="Mejor" value={backtest.best_hits} />
                  <BT label="ROI sim." value={`${backtest.simulated.roi_percent}%`} />
                  <BT label="ROI azar" value={`${backtest.simulated.random_roi_percent}%`} />
                </div>
                <div>
                  <p className="text-xs text-white/50 mb-2">Distribución de aciertos ({backtest.draws_tested} sorteos)</p>
                  <div className="space-y-1">
                    {Object.entries(backtest.distribution as Record<string, number>).map(([k, v]) => {
                      const total = backtest.total_combinations || 1;
                      return (
                        <div key={k} className="flex items-center gap-2">
                          <span className="w-4 text-xs text-white/50 tnum">{k}</span>
                          <div className="flex-1 h-2.5 rounded-full bg-white/10 overflow-hidden">
                            <div className="h-full bg-gradient-to-r from-violet-500 to-cyan-400" style={{ width: `${(v / total) * 100}%` }} />
                          </div>
                          <span className="w-8 text-[10px] text-white/40 tnum text-right">{v}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </GlassCard>

          <p className="text-[11px] text-white/40 text-center px-3">{est.disclaimer}</p>
        </div>
      )}
    </>
  );
}

function BT({ label, value, hl }: { label: string; value: string | number; hl?: boolean }) {
  return (
    <div className={`rounded-2xl py-2.5 ${hl ? "bg-gradient-to-br from-emerald-500/25 to-cyan-500/20" : "bg-white/[0.05]"}`}>
      <p className="text-base font-bold tnum">{value}</p>
      <p className="text-[10px] text-white/45">{label}</p>
    </div>
  );
}
