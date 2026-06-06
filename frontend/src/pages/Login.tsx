import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { GlassButton } from "../components/ui";
import { LiquidModal } from "../components/LiquidModal";
import { api } from "../api/client";

function ForgotPasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { notify } = useToast();
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);

  async function request() {
    setBusy(true);
    try {
      const r = await api.post<{ reset_token?: string; message: string }>("/auth/forgot-password", { email });
      if (r.reset_token) {
        setToken(r.reset_token);
        setStep(2);
        notify("Token de recuperación generado", "success");
      } else {
        notify(r.message, "info");
      }
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    if (next.length < 6) return notify("Mínimo 6 caracteres", "error");
    setBusy(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: next });
      notify("Contraseña restablecida. Inicia sesión.", "success");
      setStep(1); setEmail(""); setToken(""); setNext("");
      onClose();
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <LiquidModal open={open} onClose={onClose} title="Recuperar contraseña">
      {step === 1 ? (
        <div className="space-y-3">
          <p className="text-xs text-white/50">Ingresa tu email para generar un token de recuperación.</p>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="glass-input w-full" placeholder="tu@email.com" />
          <GlassButton full size="lg" onClick={request} disabled={busy}>
            {busy ? "…" : "Generar token"}
          </GlassButton>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-[11px] text-amber-200/80 leading-relaxed bg-amber-500/10 rounded-xl p-2">
            Sin servicio de email configurado: usa este token para restablecer tu contraseña.
          </p>
          <input value={token} onChange={(e) => setToken(e.target.value)} className="glass-input w-full text-xs" placeholder="Token" />
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} className="glass-input w-full" placeholder="Nueva contraseña" />
          <GlassButton full size="lg" onClick={reset} disabled={busy}>
            {busy ? "…" : "Restablecer contraseña"}
          </GlassButton>
        </div>
      )}
    </LiquidModal>
  );
}

export default function Login() {
  const { login } = useAuth();
  const { notify } = useToast();
  const nav = useNavigate();
  const [email, setEmail] = useState("demo@melateai.pro");
  const [password, setPassword] = useState("demo1234");
  const [loading, setLoading] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      notify("Bienvenido de vuelta ✦", "success");
      nav("/");
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-aurora min-h-screen flex flex-col justify-center px-6 relative">
      <div className="relative z-10 mx-auto w-full max-w-sm animate-slide-up">
        <div className="text-center mb-8">
          <div className="mx-auto w-20 h-20 rounded-[26px] bg-gradient-to-br from-violet-600 via-indigo-500 to-cyan-500 shadow-glow flex items-center justify-center text-4xl mb-4 animate-float">
            🎰
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-gradient">MelateAI Pro</h1>
          <p className="text-sm text-white/50 mt-1">Análisis predictivo de sorteos</p>
        </div>

        <form onSubmit={submit} className="glass-strong rounded-4xl p-6 space-y-4">
          <h2 className="text-xl font-bold mb-1">Iniciar sesión</h2>
          <div>
            <label className="text-xs text-white/50 ml-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="glass-input w-full mt-1"
              placeholder="tu@email.com"
            />
          </div>
          <div>
            <label className="text-xs text-white/50 ml-1">Contraseña</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="glass-input w-full mt-1"
              placeholder="••••••••"
            />
          </div>
          <button type="button" onClick={() => setForgotOpen(true)} className="text-xs text-cyan-300/80 ml-1 block">
            ¿Olvidaste tu contraseña?
          </button>
          <GlassButton type="submit" full size="lg" disabled={loading}>
            {loading ? "Entrando…" : "Entrar"}
          </GlassButton>
          <p className="text-center text-sm text-white/50">
            ¿No tienes cuenta?{" "}
            <Link to="/register" className="text-cyan-300 font-semibold">
              Regístrate
            </Link>
          </p>
        </form>
        <p className="text-center text-[11px] text-white/30 mt-4">
          Cuenta demo precargada · demo@melateai.pro / demo1234
        </p>
      </div>
      <ForgotPasswordModal open={forgotOpen} onClose={() => setForgotOpen(false)} />
    </div>
  );
}
