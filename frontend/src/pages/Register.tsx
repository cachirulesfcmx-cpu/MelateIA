import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { GlassButton } from "../components/ui";

export default function Register() {
  const { register } = useAuth();
  const { notify } = useToast();
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password.length < 6) return notify("La contraseña debe tener al menos 6 caracteres", "error");
    if (password !== confirm) return notify("Las contraseñas no coinciden", "error");
    setLoading(true);
    try {
      await register(name, email, password);
      notify("Cuenta creada ✦", "success");
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
        <div className="text-center mb-6">
          <div className="mx-auto w-16 h-16 rounded-[22px] bg-gradient-to-br from-violet-600 to-cyan-500 shadow-glow flex items-center justify-center text-3xl mb-3">
            🎰
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-gradient">Crear cuenta</h1>
        </div>

        <form onSubmit={submit} className="glass-strong rounded-4xl p-6 space-y-4">
          <div>
            <label className="text-xs text-white/50 ml-1">Nombre</label>
            <input required value={name} onChange={(e) => setName(e.target.value)} className="glass-input w-full mt-1" placeholder="Tu nombre" />
          </div>
          <div>
            <label className="text-xs text-white/50 ml-1">Email</label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="glass-input w-full mt-1" placeholder="tu@email.com" />
          </div>
          <div>
            <label className="text-xs text-white/50 ml-1">Contraseña</label>
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="glass-input w-full mt-1" placeholder="Mínimo 6 caracteres" />
          </div>
          <div>
            <label className="text-xs text-white/50 ml-1">Confirmar contraseña</label>
            <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} className="glass-input w-full mt-1" placeholder="••••••••" />
          </div>
          <GlassButton type="submit" full size="lg" disabled={loading}>
            {loading ? "Creando…" : "Crear cuenta"}
          </GlassButton>
          <p className="text-center text-sm text-white/50">
            ¿Ya tienes cuenta?{" "}
            <Link to="/login" className="text-cyan-300 font-semibold">
              Inicia sesión
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
