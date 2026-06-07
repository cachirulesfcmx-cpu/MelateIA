/** Heatmap grid of numbers 1..N colored by intensity (0..1). */
export function NumberHeatmap({
  items,
  highlight = [],
}: {
  items: { number: number; rel: number }[];
  highlight?: number[];
}) {
  const hi = new Set(highlight);
  return (
    <div className="grid grid-cols-7 sm:grid-cols-8 gap-1.5">
      {items.map((it) => {
        const rel = Math.max(0, Math.min(1, it.rel));
        // blue (low) -> red/orange (high)
        const hue = (1 - rel) * 210;
        const light = 26 + rel * 28;
        const isHi = hi.has(it.number);
        return (
          <div
            key={it.number}
            className={`aspect-square rounded-xl flex items-center justify-center text-[13px] font-bold tnum transition-all ${
              isHi ? "ring-2 ring-white/80 scale-105" : ""
            }`}
            style={{ backgroundColor: `hsl(${hue}, 78%, ${light}%)`, color: rel > 0.5 ? "#fff" : "rgba(255,255,255,0.85)" }}
          >
            {it.number}
          </div>
        );
      })}
    </div>
  );
}

export function HeatLegend() {
  return (
    <div className="flex items-center gap-2 mt-2 justify-center">
      <span className="text-[10px] text-white/40">Menos</span>
      <div className="h-2 w-28 rounded-full" style={{ background: "linear-gradient(90deg, hsl(210,78%,26%), hsl(105,78%,40%), hsl(0,78%,54%))" }} />
      <span className="text-[10px] text-white/40">Más</span>
    </div>
  );
}
