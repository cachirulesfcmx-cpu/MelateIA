import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useGames, gameLabel } from "../hooks";
import { PageHeader } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, Capsule, gameTheme, SectionTitle } from "../components/ui";
import { NumberBall } from "../components/NumberBall";
import { useToast } from "../context/ToastContext";
import { sharePrediction } from "../shareImage";
import type { Prediction } from "../api/types";

const STATUS_LABEL: Record<string, { t: string; c: string }> = {
  pendiente: { t: "Pendiente", c: "bg-amber-500/20 text-amber-200" },
  comparada: { t: "Comparada", c: "bg-cyan-500/20 text-cyan-200" },
  usada: { t: "Usada", c: "bg-violet-500/20 text-violet-200" },
};

export default function History() {
  const games = useGames();
  const { notify } = useToast();
  const [preds, setPreds] = useState<Prediction[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterGame, setFilterGame] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState<string>("");

  async function load() {
    setLoading(true);
    try {
      const q = new URLSearchParams();
      if (filterGame) q.set("game_type", filterGame);
      if (filterStatus) q.set("status", filterStatus);
      setPreds(await api.get<Prediction[]>(`/predictions/history?${q.toString()}`));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterGame, filterStatus]);

  async function reanalyze(id: number) {
    try {
      const res = await api.get<{ hits: number; draw_number: number }>(`/evaluate/prediction/${id}`);
      notify(`Evaluado vs sorteo #${res.draw_number}: ${res.hits} aciertos`, res.hits >= 3 ? "success" : "info");
      load();
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  async function remove(id: number) {
    try {
      await api.del(`/predictions/${id}`);
      setPreds((p) => p.filter((x) => x.id !== id));
      notify("Predicción eliminada", "info");
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  async function markUsed(id: number) {
    try {
      await api.post(`/predictions/${id}/mark-used`);
      notify("Marcada como usada", "success");
      load();
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  async function exportCsv() {
    try {
      await api.download("/predictions/export", "predicciones_melateai.csv");
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  return (
    <>
      <PageHeader
        title="Historial"
        subtitle="Tus predicciones y su desempeño"
        right={
          <button onClick={exportCsv} className="glass rounded-2xl px-3 py-2 text-xs font-semibold active:scale-95">
            ⬇ CSV
          </button>
        }
      />

      <div className="space-y-2 mb-4">
        <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1">
          <Capsule active={!filterGame} onClick={() => setFilterGame("")}>Todos</Capsule>
          {games.map((g) => (
            <Capsule key={g.key} active={filterGame === g.key} onClick={() => setFilterGame(g.key)}>
              {gameTheme(g.key).emoji} {g.label}
            </Capsule>
          ))}
        </div>
        <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1">
          <Capsule active={!filterStatus} onClick={() => setFilterStatus("")}>Cualquier estado</Capsule>
          {["pendiente", "comparada", "usada"].map((s) => (
            <Capsule key={s} active={filterStatus === s} onClick={() => setFilterStatus(s)}>
              {STATUS_LABEL[s].t}
            </Capsule>
          ))}
        </div>
      </div>

      {loading ? (
        <Spinner />
      ) : preds.length === 0 ? (
        <Empty />
      ) : (
        <div className="space-y-3 animate-fade-in">
          {preds.map((p) => (
            <PredCard
              key={p.id}
              p={p}
              gameName={gameLabel(games, p.game_type)}
              positional={games.find((g) => g.key === p.game_type)?.kind === "positional"}
              onReanalyze={() => reanalyze(p.id)}
              onDelete={() => remove(p.id)}
              onMarkUsed={() => markUsed(p.id)}
            />
          ))}
        </div>
      )}
    </>
  );
}

function PredCard({
  p,
  gameName,
  positional,
  onReanalyze,
  onDelete,
  onMarkUsed,
}: {
  p: Prediction;
  gameName: string;
  positional?: boolean;
  onReanalyze: () => void;
  onDelete: () => void;
  onMarkUsed: () => void;
}) {
  const t = gameTheme(p.game_type);
  const st = STATUS_LABEL[p.status] || STATUS_LABEL.pendiente;
  const result = p.results[0];
  const matched = new Set(result?.matched_numbers || []);

  return (
    <GlassCard className="!p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span>{t.emoji}</span>
          <div>
            <p className="text-sm font-semibold">{gameName}</p>
            <p className="text-[10px] text-white/40">
              {p.strategy} · {new Date(p.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {p.best_hits >= 3 && (
            <span className="text-xs font-bold px-2 py-1 rounded-lg bg-emerald-500/20 text-emerald-300">
              {p.best_hits} aciertos
            </span>
          )}
          <span className={`text-[10px] font-semibold px-2 py-1 rounded-lg ${st.c}`}>{st.t}</span>
        </div>
      </div>

      <div className="flex gap-1.5 flex-wrap justify-center">
        {p.numbers.map((n, i) => (
          positional ? (
            <div key={i} className="flex flex-col items-center">
              <span className="text-[9px] text-white/40 mb-0.5">P{i + 1}</span>
              <NumberBall n={n} size="sm" index={i} grad={t.grad} />
            </div>
          ) : (
            <NumberBall
              key={i}
              n={n}
              size="sm"
              index={i}
              variant={result ? (matched.has(n) ? "matched" : "missed") : "default"}
              grad={t.grad}
            />
          )
        ))}
      </div>

      {result && (
        <div className="mt-3 text-center text-[11px] text-white/45">
          Evaluado vs sorteo #{result.draw_number} ·{" "}
          <span className="text-emerald-300 font-semibold">{result.hits} aciertos</span> ·{" "}
          {result.missed_numbers.length} fallos
        </div>
      )}

      <div className="flex items-center gap-2 mt-3">
        <GlassButton size="sm" variant="outline" onClick={onReanalyze} className="flex-1 !py-2">
          {p.can_evaluate && p.latest_draw_number
            ? `🎯 Evaluar con sorteo #${p.latest_draw_number}`
            : "🔄 Reanalizar"}
        </GlassButton>
        {!p.used && (
          <GlassButton size="sm" variant="ghost" onClick={onMarkUsed} className="flex-1 !py-2">
            ✓ Usar
          </GlassButton>
        )}
        <GlassButton size="sm" variant="ghost" onClick={() => sharePrediction({ numbers: p.numbers, gameType: p.game_type, strategy: p.strategy, score: p.score })} className="!py-2 !px-3">
          ↗
        </GlassButton>
        <GlassButton size="sm" variant="danger" onClick={onDelete} className="!py-2 !px-3">
          🗑
        </GlassButton>
      </div>
    </GlassCard>
  );
}

function Empty() {
  return (
    <GlassCard className="text-center py-10">
      <div className="text-5xl mb-3 opacity-40">📭</div>
      <p className="text-white/60 font-semibold">Sin predicciones aún</p>
      <p className="text-xs text-white/40 mt-1">Genera tu primera predicción desde la pestaña Predicción.</p>
    </GlassCard>
  );
}
