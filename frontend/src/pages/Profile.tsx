import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { PageHeader } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, SectionTitle } from "../components/ui";
import { LiquidModal } from "../components/LiquidModal";
import { GameSelector } from "../components/GameSelector";
import { useGames } from "../hooks";
import { getDefaultGame, setDefaultGame } from "../settings";
import { pushSupported, isSubscribed, enableNotifications, disableNotifications, sendTestNotification } from "../push";
import type { ProfileStats } from "../api/types";

function ChangePasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { notify } = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (next.length < 6) return notify("La nueva contraseña debe tener al menos 6 caracteres", "error");
    if (next !== confirm) return notify("Las contraseñas no coinciden", "error");
    setSaving(true);
    try {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      notify("Contraseña actualizada ✦", "success");
      setCurrent(""); setNext(""); setConfirm("");
      onClose();
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <LiquidModal open={open} onClose={onClose} title="Cambiar contraseña">
      <div className="space-y-3">
        <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} className="glass-input w-full" placeholder="Contraseña actual" />
        <input type="password" value={next} onChange={(e) => setNext(e.target.value)} className="glass-input w-full" placeholder="Nueva contraseña" />
        <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="glass-input w-full" placeholder="Confirmar nueva contraseña" />
        <GlassButton full size="lg" onClick={submit} disabled={saving}>
          {saving ? "Guardando…" : "Actualizar contraseña"}
        </GlassButton>
      </div>
    </LiquidModal>
  );
}

interface PerfRow {
  strategy: string;
  game_type: string;
  total_predictions: number;
  average_hits: number;
  best_hits: number;
  weight: number;
}

export default function Profile() {
  const { user, logout } = useAuth();
  const { notify } = useToast();
  const nav = useNavigate();
  const [stats, setStats] = useState<ProfileStats | null>(null);
  const [perf, setPerf] = useState<PerfRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [pwOpen, setPwOpen] = useState(false);
  const [notifOn, setNotifOn] = useState(false);
  const [notifBusy, setNotifBusy] = useState(false);
  const [delOpen, setDelOpen] = useState(false);
  const games = useGames();
  const [favGame, setFavGame] = useState(getDefaultGame());

  async function exportData() {
    try {
      await api.download("/auth/export", "mis-datos-melateai.json");
      notify("Datos exportados", "success");
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }
  async function deleteAccount() {
    try {
      await api.del("/auth/me");
      notify("Cuenta eliminada", "info");
      logout();
      nav("/login");
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  useEffect(() => {
    if (pushSupported()) isSubscribed().then(setNotifOn).catch(() => {});
  }, []);

  async function toggleNotif() {
    setNotifBusy(true);
    try {
      if (notifOn) {
        await disableNotifications();
        setNotifOn(false);
        notify("Notificaciones desactivadas", "info");
      } else {
        await enableNotifications();
        setNotifOn(true);
        const n = await sendTestNotification();
        notify(n > 0 ? "Notificaciones activadas ✦" : "Activadas (sin envío de prueba)", "success");
      }
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setNotifBusy(false);
    }
  }

  useEffect(() => {
    Promise.all([
      api.get<ProfileStats>("/auth/me"),
      api.get<{ performance: PerfRow[] }>("/ml/performance"),
    ])
      .then(([s, p]) => {
        setStats(s);
        setPerf(p.performance);
      })
      .finally(() => setLoading(false));
  }, []);

  function doLogout() {
    api.post("/auth/logout").catch(() => {});
    logout();
    nav("/login");
  }

  if (loading || !stats) return <Spinner />;

  const maxWeight = Math.max(1, ...perf.map((p) => p.weight));

  return (
    <>
      <PageHeader title="Perfil" subtitle="Tu cuenta y desempeño" />

      <GlassCard glow className="mb-5">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-3xl bg-gradient-to-br from-violet-600 to-cyan-500 flex items-center justify-center text-2xl font-extrabold shadow-glow">
            {user?.name?.[0]?.toUpperCase()}
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-bold">{stats.user.name}</h2>
            <p className="text-sm text-white/50">{stats.user.email}</p>
            <p className="text-[11px] text-white/35 mt-0.5">
              Miembro desde {new Date(stats.user.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>
      </GlassCard>

      <div className="grid grid-cols-3 gap-3 mb-5">
        <Tile label="Predicciones" value={stats.total_predictions} />
        <Tile label="Sorteos" value={stats.total_draws_added} />
        <Tile label="Mejor" value={`${stats.best_hits}✓`} />
      </div>

      <SectionTitle title="Desempeño por estrategia" subtitle="Pesos ajustados por aprendizaje por refuerzo" />
      {perf.length === 0 ? (
        <GlassCard className="text-center py-6 mb-5">
          <p className="text-sm text-white/50">Aún sin datos de desempeño.</p>
          <p className="text-xs text-white/35 mt-1">Guarda predicciones y agrega sorteos reales para entrenar la memoria.</p>
        </GlassCard>
      ) : (
        <div className="space-y-2 mb-5">
          {perf
            .sort((a, b) => b.weight - a.weight)
            .map((p) => (
              <GlassCard key={`${p.strategy}-${p.game_type}`} className="!p-3.5">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-sm font-semibold capitalize">{p.strategy.replace("_", " ")}</p>
                    <p className="text-[10px] text-white/40">
                      {p.game_type} · {p.total_predictions} eval · prom {p.average_hits} · mejor {p.best_hits}
                    </p>
                  </div>
                  <span className="text-xs font-bold tnum text-cyan-300">{p.weight.toFixed(2)}</span>
                </div>
                <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-violet-500 to-cyan-400" style={{ width: `${(p.weight / maxWeight) * 100}%` }} />
                </div>
              </GlassCard>
            ))}
        </div>
      )}

      <GlassCard className="mb-5">
        <SectionTitle title="⚙️ Ajustes" subtitle="Juego favorito (se abre por defecto)" />
        <GameSelector games={games} value={favGame} onChange={(g) => { setFavGame(g); setDefaultGame(g); notify("Juego favorito actualizado", "success"); }} />
      </GlassCard>

      <div className="space-y-3">
        {user?.is_admin && (
          <GlassButton full size="lg" onClick={() => nav("/admin/usuarios")}>
            👥 Usuarios (Administración)
          </GlassButton>
        )}
        <GlassButton full variant="ghost" size="lg" onClick={() => nav("/estimador")}>
          💰 Estimador de ganancias
        </GlassButton>
        <GlassButton full variant="ghost" size="lg" onClick={() => nav("/asistente")}>
          🤖 Asistente IA
        </GlassButton>
        {pushSupported() && (
          <GlassButton full variant={notifOn ? "outline" : "ghost"} size="lg" onClick={toggleNotif} disabled={notifBusy}>
            {notifBusy ? "…" : notifOn ? "🔔 Notificaciones activadas (tocar para desactivar)" : "🔕 Activar notificaciones"}
          </GlassButton>
        )}
        <GlassButton full variant="outline" size="lg" onClick={() => setPwOpen(true)}>
          🔑 Cambiar contraseña
        </GlassButton>
        <GlassButton full variant="ghost" size="lg" onClick={() => nav("/responsable")}>
          ℹ️ Juego responsable e info
        </GlassButton>
        <div className="grid grid-cols-2 gap-3">
          <GlassButton variant="outline" onClick={exportData}>⬇ Exportar datos</GlassButton>
          <GlassButton variant="danger" onClick={() => setDelOpen(true)}>Eliminar cuenta</GlassButton>
        </div>
        <GlassButton full variant="danger" size="lg" onClick={doLogout}>
          Cerrar sesión
        </GlassButton>
      </div>

      <ChangePasswordModal open={pwOpen} onClose={() => setPwOpen(false)} />
      <LiquidModal open={delOpen} onClose={() => setDelOpen(false)} title="Eliminar cuenta">
        <div className="space-y-4">
          <p className="text-sm text-white/70">Esto borra tu cuenta y tus predicciones de forma permanente. Los sorteos oficiales que hayas cargado se conservan. Esta acción no se puede deshacer.</p>
          <GlassButton full variant="danger" size="lg" onClick={deleteAccount}>Sí, eliminar mi cuenta</GlassButton>
          <GlassButton full variant="ghost" onClick={() => setDelOpen(false)}>Cancelar</GlassButton>
        </div>
      </LiquidModal>

      <p className="text-center text-[11px] text-white/30 mt-6">MelateAI Pro · v1.0 · Juega con responsabilidad</p>
    </>
  );
}

function Tile({ label, value }: { label: string; value: string | number }) {
  return (
    <GlassCard className="!p-4 text-center">
      <p className="text-xl font-extrabold tnum">{value}</p>
      <p className="text-[10px] text-white/45 mt-0.5">{label}</p>
    </GlassCard>
  );
}
