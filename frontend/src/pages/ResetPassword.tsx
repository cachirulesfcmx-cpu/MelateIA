import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useToast } from "../context/ToastContext";
import { GlassButton } from "../components/ui";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { notify } = useToast();
  const [token, setToken] = useState(params.get("token") || "");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (next.length < 6) return notify("La contraseña debe tener al menos 6 caracteres", "error");
    if (next !== confirm) return notify("Las contraseñas no coinciden", "error");
    setBusy(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: next });
      notify("Contraseña restablecida. Ya puedes iniciar sesión.", "success");
      nav("/login");
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-aurora min-h-screen flex flex-col justify-center px-6 relative">
      <div className="relative z-10 mx-auto w-full max-w-sm animate-slide-up">
        <div className="text-center mb-6">
          <div className="mx-auto w-16 h-16 rounded-[22px] bg-gradient-to-br from-violet-600 to-cyan-500 shadow-glow flex items-center justify-center text-3xl mb-3">🔑</div>
          <h1 className="text-2xl font-extrabold tracking-tight text-gradient">Restablecer contraseña</h1>
        </div>
        <div className="glass-strong rounded-4xl p-6 space-y-4">
          {!params.get("token") && (
            <div>
              <label className="text-xs text-white/50 ml-1">Token</label>
              <input value={token} onChange={(e) => setToken(e.target.value)} className="glass-input w-full mt-1 text-xs" placeholder="Pega tu token" />
            </div>
          )}
          <div>
            <label className="text-xs text-white/50 ml-1">Nueva contraseña</label>
            <input type="password" value={next} onChange={(e) => setNext(e.target.value)} className="glass-input w-full mt-1" placeholder="Mínimo 6 caracteres" />
          </div>
          <div>
            <label className="text-xs text-white/50 ml-1">Confirmar</label>
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="glass-input w-full mt-1" placeholder="••••••••" />
          </div>
          <GlassButton type="button" full size="lg" onClick={submit} disabled={busy || !token}>
            {busy ? "Restableciendo…" : "Restablecer contraseña"}
          </GlassButton>
          <p className="text-center text-sm text-white/50">
            <Link to="/login" className="text-cyan-300 font-semibold">Volver a iniciar sesión</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
