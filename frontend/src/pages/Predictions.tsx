import { useState } from "react";
import { api } from "../api/client";
import { useGames, useStrategies } from "../hooks";
import { PageHeader, Disclaimer } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, gameTheme, SectionTitle } from "../components/ui";
import { GameSelector } from "../components/GameSelector";
import { StrategySelector } from "../components/StrategySelector";
import { NumberBall } from "../components/NumberBall";
import { useToast } from "../context/ToastContext";
import { sharePrediction } from "../shareImage";
import type { GeneratedCombo } from "../api/types";
import { getDefaultGame } from "../settings";

type ResearchInfo = {
  applied: boolean;
  requested: number;
  returned: number;
  risk_filter: { rejected: Record<string, number>; rejected_count: number };
  diversification: {
    overlap_limit: number; mean_overlap: number; max_overlap: number;
    distinct_numbers: number; coverage_share: number;
  };
  audited_predictions: number;
  edge_mode: string;
  edge_message: string | null;
  live: null | {
    overall_games: number; overall_mean_hits: number; random_mean_hits: number | null;
    strategy_games: number; strategy_mean_hits: number | null; strategy_edge: number | null;
    reading: string | null;
  };
  sequential: null | { status: string; ci_low: number; ci_high: number; looks: number; reading: string };
  disclaimer: string;
};

export default function Predictions() {
  const games = useGames();
  const strategies = useStrategies();
  const { notify } = useToast();

  const [game, setGame] = useState(getDefaultGame());
  const [strategy, setStrategy] = useState("evolutiva");
  const [count, setCount] = useState(5);
  const [combos, setCombos] = useState<GeneratedCombo[]>([]);
  const [research, setResearch] = useState<ResearchInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState<Set<number>>(new Set());

  const theme = gameTheme(game);
  const positional = games.find((g) => g.key === game)?.kind === "positional";

  async function generate() {
    setLoading(true);
    setCombos([]);
    setResearch(null);
    setSaved(new Set());
    try {
      const res = await api.post<{ combos: GeneratedCombo[]; research?: ResearchInfo }>(
        "/predictions/generate", { game_type: game, strategy, count });
      setCombos(res.combos);
      setResearch(res.research ?? null);
      if (!res.combos.length) notify("No se generaron combinaciones", "error");
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setLoading(false);
    }
  }

  async function save(combo: GeneratedCombo, idx: number) {
    try {
      await api.post("/predictions/save", {
        game_type: game,
        strategy,
        numbers: combo.numbers,
        score: combo.score,
        explanation: combo.explanation,
      });
      setSaved((s) => new Set(s).add(idx));
      notify("Predicción guardada ✦", "success");
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  async function saveAll() {
    for (let i = 0; i < combos.length; i++) {
      if (!saved.has(i)) await save(combos[i], i);
    }
  }

  return (
    <>
      <PageHeader title="Predicciones" subtitle="Genera combinaciones optimizadas" />
      <Disclaimer />

      <GlassCard className="space-y-4 mb-5">
        <div>
          <SectionTitle title="Tipo de sorteo" />
          <GameSelector games={games} value={game} onChange={setGame} />
        </div>

        <div>
          <SectionTitle title="Estrategia" />
          <StrategySelector strategies={strategies} value={strategy} onChange={setStrategy} />
        </div>

        <div>
          <SectionTitle title="Combinaciones" />
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={1}
              max={20}
              value={count}
              onChange={(e) => setCount(parseInt(e.target.value))}
              className="flex-1 accent-cyan-400"
            />
            <span className="w-10 text-center font-bold tnum glass rounded-xl py-1">{count}</span>
          </div>
        </div>

        <GlassButton full size="lg" onClick={generate} disabled={loading}>
          {loading ? "Analizando historial…" : "✨ Generar predicciones"}
        </GlassButton>
      </GlassCard>

      {loading && <Spinner label="Motor híbrido evaluando miles de combinaciones…" />}

      {research?.applied && (
        <GlassCard className="!p-3 mb-4 animate-fade-in">
          <p className="text-[11px] text-white/40 uppercase tracking-wide mb-2">
            Capa de investigación aplicada
          </p>

          <div className="flex items-center gap-2 mb-2">
            <span
              className={`text-[10px] px-2 py-1 rounded-lg border ${
                research.edge_mode === "NO_EDGE"
                  ? "text-rose-300 border-rose-400/30 bg-rose-500/10"
                  : "text-emerald-300 border-emerald-400/30 bg-emerald-500/10"
              }`}
            >
              {research.edge_mode}
            </span>
            <span className="text-[10px] text-white/45 tnum">
              {research.audited_predictions} auditadas · {research.returned}/{research.requested} tras filtros
            </span>
          </div>

          <div className="space-y-1 text-[11px] text-white/65">
            {research.risk_filter.rejected_count > 0 ? (
              <p>
                Filtro de riesgo descartó{" "}
                {Object.entries(research.risk_filter.rejected)
                  .filter(([, v]) => v > 0)
                  .map(([k, v]) => `${v} por ${k.replace(/_/g, " ")}`)
                  .join(", ")}
                .
              </p>
            ) : (
              <p>Filtro de riesgo: ninguna combinación descartada.</p>
            )}
            <p className="tnum">
              Diversificación: solape medio {research.diversification.mean_overlap} (máx{" "}
              {research.diversification.max_overlap}) · {research.diversification.distinct_numbers}{" "}
              números distintos.
            </p>
            {research.live && research.live.strategy_games > 0 && (
              <p className="tnum">
                Historial real de esta estrategia: {research.live.strategy_games} predicciones ·{" "}
                {research.live.strategy_mean_hits} aciertos vs {research.live.random_mean_hits} del azar.
              </p>
            )}
            {research.sequential && (
              <p className="tnum text-white/50">
                IC ajustado por {research.sequential.looks} miradas: [
                {research.sequential.ci_low}, {research.sequential.ci_high}] →{" "}
                {research.sequential.status === "SIGNAL_CANDIDATE"
                  ? "candidato a señal"
                  : "compatible con el azar"}
                .
              </p>
            )}
          </div>

          <p className="text-[10px] text-amber-200/80 mt-2 leading-relaxed">
            {research.disclaimer}
          </p>
        </GlassCard>
      )}

      {combos.length > 0 && (
        <div className="animate-slide-up">
          <SectionTitle
            title={`${combos.length} combinaciones`}
            action={
              <button onClick={saveAll} className="text-xs text-cyan-300 font-semibold">
                Guardar todas
              </button>
            }
          />
          <div className="space-y-3">
            {combos.map((c, i) => (
              <ComboCard key={i} combo={c} gameType={game} grad={theme.grad} saved={saved.has(i)} onSave={() => save(c, i)} rank={i + 1} positional={positional} />
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function ComboCard({
  combo,
  gameType,
  grad,
  saved,
  onSave,
  rank,
  positional,
}: {
  combo: GeneratedCombo;
  gameType: string;
  grad: string;
  saved: boolean;
  onSave: () => void;
  rank: number;
  positional?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const pct = Math.round(combo.score * 100);
  const f = combo.features as unknown as Record<string, number>;
  return (
    <GlassCard className="!p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="w-6 h-6 rounded-full bg-white/10 text-xs font-bold flex items-center justify-center">{rank}</span>
          <ConfidenceBar pct={pct} />
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => sharePrediction({ numbers: combo.numbers, gameType, strategy: combo.strategy, score: combo.score })}
            className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-white/10 text-white hover:bg-white/15 active:scale-95 transition"
          >
            ↗ Compartir
          </button>
          <button
            onClick={onSave}
            disabled={saved}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition active:scale-95 ${
              saved ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10 text-white hover:bg-white/15"
            }`}
          >
            {saved ? "✓ Guardada" : "Guardar"}
          </button>
        </div>
      </div>
      <div className="flex gap-2 flex-wrap justify-center py-1">
        {combo.numbers.map((n, idx) => (
          <div key={idx} className="flex flex-col items-center">
            {positional && <span className="text-[9px] text-white/40 mb-0.5">P{idx + 1}</span>}
            <NumberBall n={n} grad={grad} index={idx} />
          </div>
        ))}
      </div>
      <button onClick={() => setOpen((o) => !o)} className="w-full mt-3 text-[11px] text-white/45 flex items-center justify-center gap-1">
        {open ? "Ocultar análisis ▲" : "Ver análisis matemático ▼"}
      </button>
      {open && (
        <div className="mt-2 animate-fade-in space-y-2">
          <p className="text-[11px] text-white/60 leading-relaxed">{combo.explanation}</p>
          {positional ? (
            <div className="grid grid-cols-3 gap-2 text-center">
              <Mini label="Suma" value={f.sum} />
              <Mini label="Par/Impar" value={`${f.even}/${f.odd}`} />
              <Mini label="Distintos" value={f.distinct} />
              <Mini label="Repetidos" value={f.repeats} />
              <Mini label="Máx" value={f.max_digit} />
              <Mini label="Mín" value={f.min_digit} />
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2 text-center">
              <Mini label="Suma" value={combo.features.sum} />
              <Mini label="Par/Impar" value={`${combo.features.even}/${combo.features.odd}`} />
              <Mini label="Primos" value={combo.features.primes} />
              <Mini label="Rango" value={combo.features.range} />
              <Mini label="Consec." value={combo.features.consecutive} />
              <Mini label="Popular." value={`${Math.round(combo.features.popularity * 100)}%`} />
            </div>
          )}
        </div>
      )}
    </GlassCard>
  );
}

function ConfidenceBar({ pct }: { pct: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2 rounded-full bg-white/10 overflow-hidden">
        <div className="h-full bg-gradient-to-r from-violet-500 to-cyan-400" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] font-bold text-white/70 tnum">{pct}%</span>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white/[0.05] rounded-xl py-1.5">
      <p className="text-sm font-bold tnum">{value}</p>
      <p className="text-[9px] text-white/40">{label}</p>
    </div>
  );
}
