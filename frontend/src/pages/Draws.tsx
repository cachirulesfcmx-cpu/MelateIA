import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useGames } from "../hooks";
import { PageHeader } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, gameTheme, SectionTitle } from "../components/ui";
import { GameSelector } from "../components/GameSelector";
import { NumberBall } from "../components/NumberBall";
import { NumberHeatmap, HeatLegend } from "../components/NumberHeatmap";
import { AddDrawModal } from "../components/AddDrawModal";
import { FloatingActionButton } from "../components/LiquidModal";
import { useToast } from "../context/ToastContext";
import { useAuth } from "../context/AuthContext";
import type { Draw, DrawStats } from "../api/types";
import { getDefaultGame } from "../settings";

interface TrackerNum {
  number: number;
  frequency: number;
  recent: number;
  gap: number;
  last_date: string | null;
  days_since: number | null;
  heat: number;
  temp: "hot" | "cold";
}
interface Tracker {
  max_number: number;
  total_draws: number;
  window: number;
  hot: TrackerNum[];
  cold: TrackerNum[];
  overdue: TrackerNum[];
}

export default function Draws() {
  const games = useGames();
  const { notify } = useToast();
  const { user } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);

  const [game, setGame] = useState(getDefaultGame());
  const [stats, setStats] = useState<DrawStats | null>(null);
  const [tracker, setTracker] = useState<Tracker | null>(null);
  const [pairs, setPairs] = useState<{ a: number; b: number; count: number }[]>([]);
  const [draws, setDraws] = useState<Draw[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"balls" | "table">("balls");
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [s, t, d, pr] = await Promise.all([
        api.get<DrawStats>(`/draws/stats?game_type=${game}`),
        api.get<Tracker>(`/draws/number-tracker?game_type=${game}`),
        api.get<{ draws: Draw[] }>(`/draws?game_type=${game}&limit=60`),
        api.get<{ pairs: { a: number; b: number; count: number }[] }>(`/draws/pairs?game_type=${game}`),
      ]);
      setStats(s);
      setTracker(t);
      setDraws(d.draws);
      setPairs(pr.pairs);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game]);

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await api.uploadCsv(game, file);
      notify(`${res.imported} sorteos importados`, "success");
      load();
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const theme = gameTheme(game);
  const filtered = search
    ? draws.filter((d) => d.numbers.includes(parseInt(search)) || String(d.draw_number).includes(search))
    : draws;

  return (
    <>
      <PageHeader
        title="Sorteos"
        subtitle="Historial completo y estadísticas"
        right={
          user?.is_admin ? (
            <button
              onClick={() => fileRef.current?.click()}
              className="glass rounded-2xl px-3 py-2 text-xs font-semibold active:scale-95"
              disabled={uploading}
            >
              {uploading ? "…" : "⬆ CSV"}
            </button>
          ) : undefined
        }
      />
      <input ref={fileRef} type="file" accept=".csv" hidden onChange={upload} />

      <div className="mb-4">
        <GameSelector games={games} value={game} onChange={setGame} />
      </div>

      {loading || !stats ? (
        <Spinner />
      ) : (
        <div className="space-y-5 animate-fade-in">
          {/* Frequency stats */}
          <GlassCard>
            <SectionTitle title="Estadísticas" subtitle={`${stats.total_draws} sorteos analizados`} />
            <div className="grid grid-cols-3 gap-2 mb-4">
              <Stat label="Suma prom." value={stats.averages.sum} />
              <Stat label="Rango prom." value={stats.averages.range} />
              <Stat label="Par/Impar" value={`${stats.averages.even}/${stats.averages.odd}`} />
              <Stat label="Primos" value={stats.averages.primes} />
              <Stat label="Consec." value={stats.averages.consecutive} />
              <Stat label="Repite ant." value={stats.averages.repeats_vs_previous} />
            </div>

            <p className="text-xs text-white/50 mb-2 ml-1">🔥 Más frecuentes</p>
            <div className="flex gap-1.5 flex-wrap mb-3">
              {stats.most_frequent.slice(0, 8).map((f, i) => (
                <div key={f.number} className="flex flex-col items-center">
                  <NumberBall n={f.number} size="sm" variant="hot" index={i} />
                  <span className="text-[9px] text-white/40 mt-0.5 tnum">{f.count}</span>
                </div>
              ))}
            </div>

            <p className="text-xs text-white/50 mb-2 ml-1">❄️ Menos frecuentes</p>
            <div className="flex gap-1.5 flex-wrap mb-3">
              {stats.least_frequent.slice(0, 8).map((f, i) => (
                <div key={f.number} className="flex flex-col items-center">
                  <NumberBall n={f.number} size="sm" variant="cold" index={i} />
                  <span className="text-[9px] text-white/40 mt-0.5 tnum">{f.count}</span>
                </div>
              ))}
            </div>

            <p className="text-xs text-white/50 mb-2 ml-1">⏰ Más atrasados (gaps)</p>
            <div className="flex gap-1.5 flex-wrap">
              {stats.overdue.slice(0, 8).map((o, i) => (
                <div key={o.number} className="flex flex-col items-center">
                  <NumberBall n={o.number} size="sm" index={i} />
                  <span className="text-[9px] text-white/40 mt-0.5 tnum">{o.gap}</span>
                </div>
              ))}
            </div>
          </GlassCard>

          {/* Hot/Cold ranking */}
          {tracker && (
            <GlassCard>
              <SectionTitle title="🔥 Ranking caliente / frío" subtitle={`Últimas ${tracker.window} extracciones`} />
              <p className="text-[11px] text-rose-300/80 mb-2">Más calientes</p>
              <div className="space-y-1.5 mb-4">
                {tracker.hot.slice(0, 6).map((t, i) => (
                  <RankRow key={t.number} idx={i + 1} num={t.number} variant="hot" value={t.recent} maxValue={tracker.hot[0].recent} sub={`${t.recent} apar.`} />
                ))}
              </div>
              <p className="text-[11px] text-sky-300/80 mb-2">Más fríos</p>
              <div className="space-y-1.5">
                {tracker.cold.slice(0, 6).map((t, i) => (
                  <RankRow key={t.number} idx={i + 1} num={t.number} variant="cold" value={t.recent} maxValue={Math.max(1, tracker.hot[0].recent)} sub={`${t.recent} apar.`} />
                ))}
              </div>
            </GlassCard>
          )}

          {/* Frequency heatmap */}
          {stats.frequency && (
            <GlassCard>
              <SectionTitle title="🗺️ Mapa de calor de frecuencias" subtitle="Qué tan seguido ha salido cada número" />
              {(() => {
                const entries = Object.entries(stats.frequency).map(([k, v]) => ({ number: +k, count: v as number }));
                const max = Math.max(1, ...entries.map((e) => e.count));
                return (
                  <>
                    <NumberHeatmap items={entries.sort((a, b) => a.number - b.number).map((e) => ({ number: e.number, rel: e.count / max }))} />
                    <HeatLegend />
                  </>
                );
              })()}
            </GlassCard>
          )}

          {/* Hot pairs */}
          {pairs.length > 0 && (
            <GlassCard>
              <SectionTitle title="🔗 Pares más frecuentes" subtitle="Números que más han salido juntos" />
              <div className="space-y-2">
                {pairs.slice(0, 8).map((p, i) => (
                  <div key={`${p.a}-${p.b}`} className="flex items-center gap-3 bg-white/[0.04] rounded-2xl px-3 py-2">
                    <span className="w-4 text-[11px] text-white/40 tnum">{i + 1}</span>
                    <NumberBall n={p.a} size="sm" grad={theme.grad} />
                    <span className="text-white/30">+</span>
                    <NumberBall n={p.b} size="sm" grad={theme.grad} />
                    <div className="flex-1" />
                    <span className="text-sm font-bold tnum text-white/80">{p.count}×</span>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {/* Appearance timer (cronómetro) */}
          {tracker && (
            <GlassCard>
              <SectionTitle title="⏱️ Cronómetro de aparición" subtitle="Tiempo desde la última vez que salió cada número" />
              <div className="space-y-2">
                {tracker.overdue.slice(0, 8).map((t) => (
                  <div key={t.number} className="flex items-center gap-3 bg-white/[0.04] rounded-2xl px-3 py-2">
                    <NumberBall n={t.number} size="sm" />
                    <div className="flex-1">
                      <div className="flex items-baseline gap-2">
                        <span className="text-base font-extrabold tnum text-amber-300">{t.gap}</span>
                        <span className="text-[11px] text-white/50">sorteos sin salir</span>
                      </div>
                      <p className="text-[10px] text-white/40">
                        {t.days_since != null ? `hace ~${t.days_since} días` : "—"}
                        {t.last_date && ` · última: ${t.last_date}`}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-[10px] text-white/40">aparece</p>
                      <p className="text-xs font-semibold tnum">{t.frequency}×</p>
                    </div>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {/* Draw list */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar número o concurso…"
                className="glass-input flex-1 !py-2 text-sm"
                inputMode="numeric"
              />
              <div className="flex gap-1 p-1 bg-white/5 rounded-xl">
                <button onClick={() => setView("balls")} className={`px-2.5 py-1.5 rounded-lg text-xs ${view === "balls" ? "bg-white/15" : "text-white/50"}`}>🎱</button>
                <button onClick={() => setView("table")} className={`px-2.5 py-1.5 rounded-lg text-xs ${view === "table" ? "bg-white/15" : "text-white/50"}`}>☰</button>
              </div>
            </div>

            {view === "balls" ? (
              <div className="space-y-2">
                {filtered.map((d) => (
                  <GlassCard key={d.id} className="!p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-white/40 tnum">#{d.draw_number}</span>
                      <span className="text-[10px] text-white/30">{d.draw_date} · {d.source}</span>
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      {d.numbers.map((n, i) => (
                        <NumberBall key={n} n={n} size="sm" grad={theme.grad} index={i} />
                      ))}
                      {d.additional != null && <NumberBall n={d.additional} size="sm" variant="gold" />}
                    </div>
                  </GlassCard>
                ))}
              </div>
            ) : (
              <GlassCard className="!p-0 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-white/40 text-xs border-b border-white/10">
                      <th className="text-left p-3">Concurso</th>
                      <th className="text-left p-3">Números</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((d) => (
                      <tr key={d.id} className="border-b border-white/5">
                        <td className="p-3 tnum text-white/60">#{d.draw_number}</td>
                        <td className="p-3 tnum font-semibold">{d.numbers.join(" · ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </GlassCard>
            )}
          </div>
        </div>
      )}

      {user?.is_admin && <FloatingActionButton onClick={() => setModal(true)} />}
      <AddDrawModal open={modal} onClose={() => setModal(false)} games={games} defaultGame={game} onSaved={load} />
    </>
  );
}

function RankRow({ idx, num, variant, value, maxValue, sub }: { idx: number; num: number; variant: "hot" | "cold"; value: number; maxValue: number; sub: string }) {
  const pct = Math.max(6, (value / Math.max(1, maxValue)) * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="w-4 text-[11px] text-white/40 tnum">{idx}</span>
      <NumberBall n={num} size="sm" variant={variant} />
      <div className="flex-1 h-2.5 rounded-full bg-white/[0.07] overflow-hidden">
        <div className={`h-full rounded-full ${variant === "hot" ? "bg-gradient-to-r from-rose-500 to-orange-400" : "bg-gradient-to-r from-sky-500 to-indigo-500"}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-white/45 w-14 text-right">{sub}</span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white/[0.05] rounded-2xl py-2.5 text-center">
      <p className="text-base font-bold tnum">{value}</p>
      <p className="text-[10px] text-white/40">{label}</p>
    </div>
  );
}
