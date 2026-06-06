/** Lightweight, dependency-free charts in the Liquid Glass style. */

export function BarList({
  items,
  format = (v) => String(v),
  accent = "from-violet-500 to-cyan-400",
}: {
  items: { label: string; value: number; sub?: string }[];
  format?: (v: number) => string;
  accent?: string;
}) {
  const max = Math.max(0.0001, ...items.map((i) => i.value));
  return (
    <div className="space-y-2.5">
      {items.map((it) => (
        <div key={it.label}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[12px] text-white/70 capitalize">{it.label}</span>
            <span className="text-[11px] font-bold tnum text-white/80">
              {format(it.value)}
              {it.sub && <span className="text-white/40 font-normal ml-1">{it.sub}</span>}
            </span>
          </div>
          <div className="h-2.5 rounded-full bg-white/[0.07] overflow-hidden">
            <div
              className={`h-full bg-gradient-to-r ${accent} rounded-full transition-all duration-700`}
              style={{ width: `${(it.value / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function VBars({
  data,
  labels,
  highlightFrom = 3,
}: {
  data: number[];
  labels: string[];
  highlightFrom?: number;
}) {
  const max = Math.max(1, ...data);
  return (
    <div className="flex items-end justify-between gap-2 h-36 pt-2">
      {data.map((v, i) => (
        <div key={i} className="flex-1 flex flex-col items-center justify-end h-full">
          <span className="text-[10px] text-white/60 tnum mb-1">{v}</span>
          <div
            className={`w-full rounded-t-lg transition-all duration-700 ${
              i >= highlightFrom
                ? "bg-gradient-to-t from-emerald-500 to-cyan-400"
                : "bg-gradient-to-t from-violet-600/70 to-indigo-400/70"
            }`}
            style={{ height: `${Math.max(4, (v / max) * 100)}%` }}
          />
          <span className="text-[10px] text-white/45 mt-1.5">{labels[i]}</span>
        </div>
      ))}
    </div>
  );
}

export function AreaChart({
  points,
  height = 120,
}: {
  points: { x: string; y: number }[];
  height?: number;
}) {
  if (points.length === 0)
    return <div className="text-center text-xs text-white/30 py-10">Sin datos aún</div>;

  const W = 320;
  const H = height;
  const pad = 8;
  const ys = points.map((p) => p.y);
  const maxY = Math.max(1, ...ys);
  const n = points.length;
  const xFor = (i: number) => (n === 1 ? W / 2 : pad + (i * (W - pad * 2)) / (n - 1));
  const yFor = (y: number) => H - pad - (y / maxY) * (H - pad * 2);
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(p.y).toFixed(1)}`).join(" ");
  const area = `${line} L${xFor(n - 1).toFixed(1)},${H - pad} L${xFor(0).toFixed(1)},${H - pad} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }}>
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(124,58,237,0.45)" />
          <stop offset="100%" stopColor="rgba(6,182,212,0.02)" />
        </linearGradient>
        <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#a78bfa" />
          <stop offset="100%" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#areaGrad)" />
      <path d={line} fill="none" stroke="url(#lineGrad)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={i} cx={xFor(i)} cy={yFor(p.y)} r="3" fill="#22d3ee" />
      ))}
    </svg>
  );
}

export function Donut({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = Math.min(1, max ? value / max : 0);
  const r = 32;
  const c = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 80 80" className="w-20 h-20 -rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="8" />
        <circle
          cx="40" cy="40" r={r} fill="none" stroke="url(#lineGrad)" strokeWidth="8" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - pct)}
        />
      </svg>
      <p className="text-sm font-bold tnum -mt-12">{value}</p>
      <p className="text-[10px] text-white/45 mt-8">{label}</p>
    </div>
  );
}
