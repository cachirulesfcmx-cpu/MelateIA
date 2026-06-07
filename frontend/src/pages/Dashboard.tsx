import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useGames } from "../hooks";
import { AppLayout, PageHeader, Disclaimer } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, gameTheme, SectionTitle } from "../components/ui";
import { NumberBall } from "../components/NumberBall";
import { AddDrawModal } from "../components/AddDrawModal";
import { FloatingActionButton } from "../components/LiquidModal";

interface Summary {
  latest_draws: Record<string, any>;
  next_draws: Record<string, any>;
  total_draws: number;
  total_predictions: number;
  active_predictions: number;
  best_combination: any;
  recent_hits: any[];
  system_average_hits: number;
  top_strategy: string | null;
}

export default function Dashboard() {
  const { user } = useAuth();
  const games = useGames();
  const nav = useNavigate();
  const [data, setData] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setData(await api.get<Summary>("/dashboard/summary"));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  const latest = data ? Object.entries(data.latest_draws) : [];

  return (
    <>
      <PageHeader
        title={`Hola, ${user?.name?.split(" ")[0] || ""} 👋`}
        subtitle="Tu centro de control predictivo"
      />
      <Disclaimer />

      {loading || !data ? (
        <Spinner label="Cargando resumen…" />
      ) : (
        <div className="space-y-5 animate-fade-in">
          {/* Stat grid */}
          <div className="grid grid-cols-2 gap-3">
            <StatTile label="Predicciones" value={data.total_predictions} icon="✨" grad="from-violet-500 to-indigo-600" />
            <StatTile label="Activas" value={data.active_predictions} icon="⏳" grad="from-cyan-500 to-blue-600" />
            <StatTile label="Sorteos en BD" value={data.total_draws} icon="🗄️" grad="from-emerald-500 to-teal-600" />
            <StatTile label="Aciertos prom." value={data.system_average_hits} icon="🎯" grad="from-amber-500 to-orange-600" />
          </div>

          {/* Best combination */}
          {data.best_combination && (
            <GlassCard glow>
              <SectionTitle title="🏆 Mejor combinación" subtitle={`${data.best_combination.hits} aciertos · ${data.best_combination.strategy}`} />
              <div className="flex gap-2 flex-wrap">
                {data.best_combination.numbers.map((n: number, i: number) => (
                  <NumberBall
                    key={n}
                    n={n}
                    index={i}
                    variant={data.best_combination.matched.includes(n) ? "matched" : "default"}
                    grad={gameTheme(data.best_combination.game_type).grad}
                  />
                ))}
              </div>
            </GlassCard>
          )}

          {/* Latest draws */}
          <div>
            <SectionTitle title="Últimos sorteos" subtitle="Resultado real más reciente por juego" />
            <div className="space-y-3">
              {latest.map(([key, d]) => {
                const t = gameTheme(key);
                return (
                  <GlassCard key={key} className="!p-4">
                    <div className="flex items-center justify-between mb-2.5">
                      <div className="flex items-center gap-2">
                        <span className="text-base">{t.emoji}</span>
                        <span className="font-semibold text-sm">{d.label}</span>
                      </div>
                      <div className="text-right">
                        <span className="text-xs text-white/40 tnum">#{d.draw_number}</span>
                        {d.draw_date && <span className="block text-[10px] text-white/30">{d.draw_date}</span>}
                      </div>
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      {d.numbers.map((n: number, i: number) => (
                        <NumberBall key={n} n={n} size="sm" grad={t.grad} index={i} />
                      ))}
                      {d.additional != null && (
                        <div className="flex items-center gap-1 ml-1">
                          <span className="text-[10px] text-white/40">+</span>
                          <NumberBall n={d.additional} size="sm" variant="gold" />
                        </div>
                      )}
                    </div>
                    <div className="mt-2.5 flex items-center justify-between">
                      <span className="text-[11px] text-white/40">Próximo: #{data.next_draws[key]?.draw_number}</span>
                    </div>
                  </GlassCard>
                );
              })}
            </div>
          </div>

          {/* Recent hits */}
          {data.recent_hits.length > 0 && (
            <div>
              <SectionTitle title="Aciertos recientes" />
              <div className="space-y-2">
                {data.recent_hits.map((h, idx) => (
                  <GlassCard key={idx} className="!p-3.5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{gameTheme(h.game_type).emoji}</span>
                      <div>
                        <p className="text-sm font-semibold">{h.hits} aciertos</p>
                        <p className="text-[11px] text-white/40">{h.strategy}</p>
                      </div>
                    </div>
                    <div className="flex gap-1">
                      {h.matched.map((n: number) => (
                        <NumberBall key={n} n={n} size="xs" variant="matched" />
                      ))}
                    </div>
                  </GlassCard>
                ))}
              </div>
            </div>
          )}

          {/* Quick actions */}
          <div className="grid grid-cols-2 gap-3">
            <GlassButton variant="ghost" size="lg" onClick={() => nav("/predicciones")}>
              ✨ Generar
            </GlassButton>
            <GlassButton variant="ghost" size="lg" onClick={() => nav("/estimador")}>
              💰 Estimador
            </GlassButton>
          </div>
          <GlassButton full variant="ghost" size="lg" onClick={() => nav("/rendimiento")}>
            📊 Rendimiento y evolución de la IA
          </GlassButton>
          <GlassButton full variant="ghost" size="lg" onClick={() => nav("/asistente")}>
            🤖 Asistente IA
          </GlassButton>
        </div>
      )}

      {user?.is_admin && <FloatingActionButton onClick={() => setModal(true)} />}
      <AddDrawModal open={modal} onClose={() => setModal(false)} games={games} onSaved={load} />
    </>
  );
}

function StatTile({ label, value, icon, grad }: { label: string; value: number | string; icon: string; grad: string }) {
  return (
    <div className={`rounded-3xl p-4 bg-gradient-to-br ${grad} relative overflow-hidden shadow-glass`}>
      <div className="absolute inset-0 bg-black/20" />
      <div className="absolute -right-3 -top-3 text-5xl opacity-20">{icon}</div>
      <div className="relative">
        <p className="text-2xl font-extrabold tnum">{value}</p>
        <p className="text-xs text-white/80 mt-0.5">{label}</p>
      </div>
    </div>
  );
}
