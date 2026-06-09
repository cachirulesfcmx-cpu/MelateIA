import { useState } from "react";

interface Props {
  length: number;          // number of positions (Tris: 5)
  lo: number;              // smallest digit (Tris: 0)
  hi: number;              // largest digit (Tris: 9)
  value: (number | null)[];
  onChange: (v: (number | null)[]) => void;
  grad?: string;
}

/** Positional digit selector for Tris: pick a digit per ordered position.
 *  Repeats are allowed and the order matters — each slot is independent. */
export function PositionalSelector({ length, lo, hi, value, onChange, grad = "from-lime-400 to-emerald-600" }: Props) {
  const [active, setActive] = useState(0);
  const digits = Array.from({ length: hi - lo + 1 }, (_, i) => i + lo);
  const filled = value.filter((v) => v !== null).length;

  function setDigit(d: number) {
    const next = [...value];
    next[active] = d;
    onChange(next);
    // advance to the next empty slot (wrapping), so tapping is fast
    let nxt = active + 1;
    for (let step = 0; step < length; step++) {
      const idx = (active + 1 + step) % length;
      if (next[idx] === null) { nxt = idx; break; }
      nxt = (active + 1) % length;
    }
    setActive(nxt);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3 px-1">
        <span className="text-sm text-white/60">
          La <b className="text-white">posición</b> importa · dígitos {lo}–{hi} (se repiten)
        </span>
        <span className={`text-sm font-bold ${filled === length ? "text-emerald-300" : "text-white/70"}`}>
          {filled}/{length}
        </span>
      </div>

      {/* position slots */}
      <div className="flex gap-2 justify-center mb-4">
        {value.map((v, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setActive(i)}
            className={`relative w-14 h-16 rounded-2xl flex flex-col items-center justify-center font-extrabold text-2xl tnum transition-all active:scale-95
              ${active === i ? "ring-2 ring-white/70 scale-105" : "ring-1 ring-white/10"}
              ${v !== null ? `bg-gradient-to-br ${grad} text-white shadow-glow` : "bg-white/[0.06] text-white/30"}`}
          >
            <span className="absolute top-1 left-0 right-0 text-[9px] font-semibold text-white/50">P{i + 1}</span>
            {v !== null ? v : "·"}
          </button>
        ))}
      </div>

      {/* digit pad */}
      <div className="grid grid-cols-5 gap-2">
        {digits.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setDigit(d)}
            className="aspect-square rounded-xl text-lg font-bold tnum flex items-center justify-center transition-all active:scale-90 bg-white/[0.07] text-white/85 border border-white/10 hover:bg-white/[0.13]"
          >
            {d}
          </button>
        ))}
      </div>
    </div>
  );
}
