import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { PageHeader } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, SectionTitle, gameTheme } from "../components/ui";
import { NumberBall } from "../components/NumberBall";
import { LiquidModal } from "../components/LiquidModal";
import { useToast } from "../context/ToastContext";
import type { AdminUser } from "../api/types";

interface Overview {
  total_users: number;
  total_admins: number;
  total_predictions: number;
  total_draws: number;
  total_evaluations: number;
  best_hits_global: number;
}

export default function AdminUsers() {
  const { user } = useAuth();
  const { notify } = useToast();
  const nav = useNavigate();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<AdminUser | null>(null);
  const [newPwd, setNewPwd] = useState("");

  useEffect(() => {
    if (user && !user.is_admin) {
      nav("/perfil");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  async function load() {
    setLoading(true);
    try {
      const [o, u] = await Promise.all([
        api.get<Overview>("/admin/overview"),
        api.get<{ users: AdminUser[] }>("/admin/users"),
      ]);
      setOverview(o);
      setUsers(u.users);
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setLoading(false);
    }
  }

  async function openDetail(id: number) {
    try {
      setDetail(await api.get<AdminUser>(`/admin/users/${id}`));
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  async function resetPwd(id: number) {
    if (newPwd.length < 6) return notify("Mínimo 6 caracteres", "error");
    try {
      await api.post(`/admin/users/${id}/reset-password`, { new_password: newPwd });
      notify("Contraseña restablecida", "success");
      setNewPwd("");
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  async function removeUser(id: number) {
    try {
      await api.del(`/admin/users/${id}`);
      notify("Usuario eliminado", "info");
      setDetail(null);
      load();
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  return (
    <>
      <PageHeader title="Usuarios" subtitle="Panel de administración" right={
        <button onClick={() => nav("/perfil")} className="glass rounded-2xl px-3 py-2 text-xs font-semibold active:scale-95">← Perfil</button>
      } />

      {loading ? (
        <Spinner />
      ) : (
        <div className="space-y-5 animate-fade-in">
          {overview && (
            <div className="grid grid-cols-3 gap-3">
              <Tile label="Usuarios" value={overview.total_users} />
              <Tile label="Predicciones" value={overview.total_predictions} />
              <Tile label="Evaluaciones" value={overview.total_evaluations} />
              <Tile label="Admins" value={overview.total_admins} />
              <Tile label="Sorteos" value={overview.total_draws} />
              <Tile label="Mejor acierto" value={`${overview.best_hits_global}✓`} />
            </div>
          )}

          <div>
            <SectionTitle title={`${users.length} usuarios registrados`} />
            <div className="space-y-3">
              {users.map((u) => (
                <GlassCard key={u.id} className="!p-4" onClick={() => openDetail(u.id)}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-11 h-11 rounded-2xl flex items-center justify-center font-bold text-sm ${u.is_admin ? "bg-gradient-to-br from-amber-400 to-orange-500 text-black" : "bg-gradient-to-br from-violet-600 to-cyan-500"}`}>
                        {u.name?.[0]?.toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-semibold flex items-center gap-2">
                          {u.name}
                          {u.is_admin && <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">ADMIN</span>}
                        </p>
                        <p className="text-[11px] text-white/40">{u.email}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-bold tnum">{u.best_hits}✓</p>
                      <p className="text-[10px] text-white/40">mejor</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-2 mt-3">
                    <Mini label="Predicc." value={u.total_predictions} />
                    <Mini label="Evaluadas" value={u.evaluated_predictions} />
                    <Mini label="Prom." value={u.average_hits} />
                  </div>
                </GlassCard>
              ))}
            </div>
          </div>
        </div>
      )}

      <LiquidModal open={!!detail} onClose={() => setDetail(null)} title={detail?.name}>
        {detail && (
          <div className="space-y-4">
            <p className="text-xs text-white/50">{detail.email} · desde {new Date(detail.created_at).toLocaleDateString()}</p>
            <div className="grid grid-cols-4 gap-2">
              <Mini label="Predicc." value={detail.total_predictions} />
              <Mini label="Eval." value={detail.evaluated_predictions} />
              <Mini label="Mejor" value={`${detail.best_hits}✓`} />
              <Mini label="Prom." value={detail.average_hits} />
            </div>

            {detail.best_combination && (
              <div>
                <p className="text-xs text-white/50 mb-2">🏆 Mejor combinación ({detail.best_combination.hits} aciertos)</p>
                <div className="flex gap-1.5 flex-wrap">
                  {detail.best_combination.numbers.map((n, i) => (
                    <NumberBall key={n} n={n} size="sm" index={i}
                      variant={detail.best_combination!.matched.includes(n) ? "matched" : "default"}
                      grad={gameTheme(detail.best_combination!.game_type).grad} />
                  ))}
                </div>
              </div>
            )}

            <div>
              <p className="text-xs text-white/50 mb-2">Predicciones recientes</p>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {(detail.predictions || []).length === 0 && <p className="text-xs text-white/30">Sin predicciones</p>}
                {(detail.predictions || []).map((p) => (
                  <div key={p.id} className="bg-white/[0.05] rounded-2xl p-3">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[11px] text-white/50">{gameTheme(p.game_type).emoji} {p.strategy}</span>
                      <span className="text-[11px] font-bold text-emerald-300">{p.best_hits}✓ · {p.status}</span>
                    </div>
                    <div className="flex gap-1 flex-wrap">
                      {p.numbers.map((n) => <NumberBall key={n} n={n} size="xs" grad={gameTheme(p.game_type).grad} />)}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="text-xs text-white/50 mb-2">🔑 Restablecer contraseña</p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newPwd}
                  onChange={(e) => setNewPwd(e.target.value)}
                  className="glass-input flex-1 !py-2 text-sm"
                  placeholder="Nueva contraseña (mín. 6)"
                />
                <GlassButton variant="ghost" onClick={() => resetPwd(detail.id)} className="!py-2">
                  Aplicar
                </GlassButton>
              </div>
            </div>

            {!detail.is_admin && (
              <GlassButton full variant="danger" onClick={() => removeUser(detail.id)}>
                Eliminar usuario
              </GlassButton>
            )}
          </div>
        )}
      </LiquidModal>
    </>
  );
}

function Tile({ label, value }: { label: string; value: string | number }) {
  return (
    <GlassCard className="!p-3 text-center">
      <p className="text-lg font-extrabold tnum">{value}</p>
      <p className="text-[10px] text-white/45 mt-0.5">{label}</p>
    </GlassCard>
  );
}
function Mini({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white/[0.05] rounded-xl py-2 text-center">
      <p className="text-sm font-bold tnum">{value}</p>
      <p className="text-[9px] text-white/40">{label}</p>
    </div>
  );
}
