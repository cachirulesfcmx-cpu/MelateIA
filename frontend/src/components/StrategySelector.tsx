import type { Strategy } from "../api/types";

const ICONS: Record<string, string> = {
  conservadora: "🛡️",
  balanceada: "⚖️",
  agresiva: "🔥",
  genetica: "🧬",
  anti_popular: "🎭",
  calientes: "♨️",
  frios: "❄️",
  hibrida: "✨",
  adaptativa: "🤖",
  evolutiva: "🧠",
};

export function StrategySelector({
  strategies,
  value,
  onChange,
}: {
  strategies: Strategy[];
  value: string;
  onChange: (k: string) => void;
}) {
  const current = strategies.find((s) => s.key === value);
  // surface the flagship engine first
  const ordered = [...strategies].sort((a, b) => (a.key === "evolutiva" ? -1 : b.key === "evolutiva" ? 1 : 0));
  return (
    <div>
      <div className="grid grid-cols-2 gap-2">
        {ordered.map((s) => {
          const active = s.key === value;
          return (
            <button
              key={s.key}
              onClick={() => onChange(s.key)}
              className={`flex items-center gap-2 px-3 py-3 rounded-2xl text-left transition-all active:scale-95 ${
                active
                  ? "bg-gradient-to-br from-violet-600/40 to-cyan-500/30 border border-white/25 shadow-glow"
                  : "bg-white/[0.05] border border-white/10 hover:bg-white/[0.09]"
              }`}
            >
              <span className="text-lg">{ICONS[s.key] || "🎯"}</span>
              <span className="text-[13px] font-semibold leading-tight">{s.label}</span>
            </button>
          );
        })}
      </div>
      {current && (
        <p className="text-xs text-white/55 mt-3 px-1 leading-relaxed animate-fade-in">{current.desc}</p>
      )}
    </div>
  );
}
