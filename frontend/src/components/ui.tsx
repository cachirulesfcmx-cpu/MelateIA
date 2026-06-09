import { ButtonHTMLAttributes, ReactNode } from "react";

/** Game theming shared across the app. */
export const GAME_THEME: Record<string, { grad: string; ring: string; emoji: string }> = {
  melate: { grad: "from-emerald-400 to-teal-500", ring: "ring-emerald-400/40", emoji: "🟢" },
  revancha: { grad: "from-fuchsia-500 to-purple-600", ring: "ring-fuchsia-400/40", emoji: "🟣" },
  melate_retro: { grad: "from-amber-400 to-orange-500", ring: "ring-amber-400/40", emoji: "🟠" },
  revanchita: { grad: "from-sky-400 to-blue-600", ring: "ring-sky-400/40", emoji: "🔵" },
  chispazo: { grad: "from-rose-400 to-pink-600", ring: "ring-rose-400/40", emoji: "⚡" },
  tris: { grad: "from-lime-400 to-emerald-600", ring: "ring-lime-400/40", emoji: "🎯" },
};

export function gameTheme(key: string) {
  return GAME_THEME[key] || { grad: "from-violet-500 to-cyan-500", ring: "ring-violet-400/40", emoji: "🎲" };
}

export function GlassCard({
  children,
  className = "",
  onClick,
  glow = false,
}: {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  glow?: boolean;
}) {
  return (
    <div
      onClick={onClick}
      className={`glass rounded-4xl p-5 relative overflow-hidden ${
        glow ? "shadow-glow" : ""
      } ${onClick ? "active:scale-[0.98] transition cursor-pointer" : ""} ${className}`}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/30 to-transparent" />
      {children}
    </div>
  );
}

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost" | "outline" | "danger";
  size?: "sm" | "md" | "lg";
  full?: boolean;
  children: ReactNode;
}

export function GlassButton({
  variant = "primary",
  size = "md",
  full,
  className = "",
  children,
  ...props
}: BtnProps) {
  const sizes = {
    sm: "px-4 py-2 text-sm",
    md: "px-5 py-3 text-[15px]",
    lg: "px-6 py-4 text-base",
  };
  const variants = {
    primary:
      "bg-gradient-to-r from-violet-600 via-indigo-500 to-cyan-500 text-white shadow-glow hover:brightness-110",
    ghost: "bg-white/10 text-white hover:bg-white/15 backdrop-blur-xl",
    outline: "bg-transparent border border-white/20 text-white hover:bg-white/10 backdrop-blur-xl",
    danger: "bg-rose-500/20 border border-rose-400/40 text-rose-100 hover:bg-rose-500/30",
  };
  return (
    <button
      {...props}
      className={`relative rounded-2xl font-semibold tracking-tight transition-all duration-200
        active:scale-95 disabled:opacity-40 disabled:active:scale-100
        ${sizes[size]} ${variants[variant]} ${full ? "w-full" : ""} ${className}`}
    >
      {children}
    </button>
  );
}

export function Capsule({ children, active, onClick }: { children: ReactNode; active?: boolean; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all active:scale-95 ${
        active
          ? "bg-gradient-to-r from-violet-600 to-cyan-500 text-white shadow-glow"
          : "bg-white/[0.07] text-white/70 border border-white/10 hover:bg-white/10"
      }`}
    >
      {children}
    </button>
  );
}

export function SectionTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="flex items-end justify-between mb-3 px-1">
      <div>
        <h2 className="text-lg font-bold tracking-tight">{title}</h2>
        {subtitle && <p className="text-xs text-white/50 mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10 text-white/60">
      <div className="w-9 h-9 rounded-full border-2 border-white/15 border-t-cyan-300 animate-spin" />
      {label && <p className="text-sm">{label}</p>}
    </div>
  );
}
