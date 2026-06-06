import { ReactNode } from "react";
import { BottomNav } from "./BottomNav";

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="bg-aurora min-h-screen relative">
      <div className="relative z-10 mx-auto max-w-md px-4 pt-[max(env(safe-area-inset-top),16px)] pb-36">
        {children}
      </div>
      <BottomNav />
    </div>
  );
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <header className="flex items-center justify-between mb-5 mt-1 animate-fade-in">
      <div>
        <h1 className="text-[26px] font-extrabold tracking-tight leading-none">{title}</h1>
        {subtitle && <p className="text-sm text-white/50 mt-1">{subtitle}</p>}
      </div>
      {right}
    </header>
  );
}

export function Disclaimer() {
  return (
    <div className="glass rounded-2xl px-4 py-3 mb-4 flex gap-3 items-start border-amber-400/20">
      <span className="text-amber-300 text-lg leading-none mt-0.5">⚠️</span>
      <p className="text-[11px] text-white/55 leading-relaxed">
        Melate es un juego de <b className="text-white/80">azar</b>. Ninguna IA puede garantizar premios.
        MelateAI Pro genera combinaciones <b className="text-white/80">estadísticamente optimizadas</b> y mide su
        desempeño histórico — no promete resultados.
      </p>
    </div>
  );
}
