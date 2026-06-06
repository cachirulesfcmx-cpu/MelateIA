import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useGames } from "../hooks";
import { PageHeader } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, gameTheme, SectionTitle } from "../components/ui";
import { GameSelector } from "../components/GameSelector";
import { NumberBall } from "../components/NumberBall";
import { AddDrawModal } from "../components/AddDrawModal";
import { FloatingActionButton } from "../components/LiquidModal";
import { useToast } from "../context/ToastContext";
import { useAuth } from "../context/AuthContext";
import type { Draw, DrawStats } from "../api/types";

export default function Draws() {
  const games = useGames();
  const { notify } = useToast();
  const { user } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);

  const [game, setGame] = useState("melate");
  const [stats, setStats] = useState<DrawStats | null>(null);
  const [draws, setDraws] = useState<Draw[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"balls" | "table">("balls");
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [s, d] = await Promise.all([
        api.get<DrawStats>(`/draws/stats?game_type=${game}`),
        api.get<{ draws: Draw[] }>(`/draws?game_type=${game}&limit=60`),
      ]);
      setStats(s);
      setDraws(d.draws);
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

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white/[0.05] rounded-2xl py-2.5 text-center">
      <p className="text-base font-bold tnum">{value}</p>
      <p className="text-[10px] text-white/40">{label}</p>
    </div>
  );
}
