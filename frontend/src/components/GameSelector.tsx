import { gameTheme } from "./ui";
import type { Game } from "../api/types";

export function GameSelector({
  games,
  value,
  onChange,
}: {
  games: Game[];
  value: string;
  onChange: (k: string) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 no-scrollbar">
      {games.map((g) => {
        const t = gameTheme(g.key);
        const active = g.key === value;
        return (
          <button
            key={g.key}
            onClick={() => onChange(g.key)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-2xl whitespace-nowrap transition-all active:scale-95 ${
              active
                ? `bg-gradient-to-r ${t.grad} text-white shadow-glow`
                : "bg-white/[0.06] text-white/70 border border-white/10"
            }`}
          >
            <span className="text-sm">{t.emoji}</span>
            <span className="text-sm font-semibold">{g.label}</span>
          </button>
        );
      })}
    </div>
  );
}
