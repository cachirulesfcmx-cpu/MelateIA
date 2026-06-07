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

export default function Predictions() {
  const games = useGames();
  const strategies = useStrategies();
  const { notify } = useToast();

  const [game, setGame] = useState("melate");
  const [strategy, setStrategy] = useState("hibrida");
  const [count, setCount] = useState(5);
  const [combos, setCombos] = useState<GeneratedCombo[]>([]);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState<Set<number>>(new Set());

  const theme = gameTheme(game);

  async function generate() {
    setLoading(true);
    setCombos([]);
    setSaved(new Set());
    try {
      const res = await api.post<{ combos: GeneratedCombo[] }>("/predictions/generate", {
        game_type: game,
        strategy,
        count,
      });
      setCombos(res.combos);
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
              <ComboCard key={i} combo={c} gameType={game} grad={theme.grad} saved={saved.has(i)} onSave={() => save(c, i)} rank={i + 1} />
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
}: {
  combo: GeneratedCombo;
  gameType: string;
  grad: string;
  saved: boolean;
  onSave: () => void;
  rank: number;
}) {
  const [open, setOpen] = useState(false);
  const pct = Math.round(combo.score * 100);
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
          <NumberBall key={n} n={n} grad={grad} index={idx} />
        ))}
      </div>
      <button onClick={() => setOpen((o) => !o)} className="w-full mt-3 text-[11px] text-white/45 flex items-center justify-center gap-1">
        {open ? "Ocultar análisis ▲" : "Ver análisis matemático ▼"}
      </button>
      {open && (
        <div className="mt-2 animate-fade-in space-y-2">
          <p className="text-[11px] text-white/60 leading-relaxed">{combo.explanation}</p>
          <div className="grid grid-cols-3 gap-2 text-center">
            <Mini label="Suma" value={combo.features.sum} />
            <Mini label="Par/Impar" value={`${combo.features.even}/${combo.features.odd}`} />
            <Mini label="Primos" value={combo.features.primes} />
            <Mini label="Rango" value={combo.features.range} />
            <Mini label="Consec." value={combo.features.consecutive} />
            <Mini label="Popular." value={`${Math.round(combo.features.popularity * 100)}%`} />
          </div>
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
