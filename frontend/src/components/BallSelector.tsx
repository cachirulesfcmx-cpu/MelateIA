import { useMemo } from "react";

interface Props {
  maxNumber: number;
  pick: number;
  selected: number[];
  onToggle: (n: number) => void;
  grad?: string;
}

/** Visual ball grid selector: tap to pick `pick` unique numbers in 1..maxNumber. */
export function BallSelector({ maxNumber, pick, selected, onToggle, grad = "from-violet-500 to-cyan-500" }: Props) {
  const numbers = useMemo(() => Array.from({ length: maxNumber }, (_, i) => i + 1), [maxNumber]);
  const full = selected.length >= pick;

  return (
    <div>
      <div className="flex items-center justify-between mb-3 px-1">
        <span className="text-sm text-white/60">
          Selecciona <b className="text-white">{pick}</b> números (1–{maxNumber})
        </span>
        <span className={`text-sm font-bold ${full ? "text-emerald-300" : "text-white/70"}`}>
          {selected.length}/{pick}
        </span>
      </div>
      <div className="grid grid-cols-7 sm:grid-cols-8 gap-2">
        {numbers.map((n) => {
          const isSel = selected.includes(n);
          const disabled = !isSel && full;
          return (
            <button
              key={n}
              type="button"
              disabled={disabled}
              onClick={() => onToggle(n)}
              className={`aspect-square rounded-full text-sm font-bold tnum flex items-center justify-center transition-all duration-150 active:scale-90
                ${
                  isSel
                    ? `bg-gradient-to-br ${grad} text-white shadow-glow ring-2 ring-white/50 scale-105`
                    : disabled
                    ? "bg-white/[0.03] text-white/20"
                    : "bg-white/[0.07] text-white/80 border border-white/10 hover:bg-white/[0.12]"
                }`}
            >
              {n}
            </button>
          );
        })}
      </div>
    </div>
  );
}
