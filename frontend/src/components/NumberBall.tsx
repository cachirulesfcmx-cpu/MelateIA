interface Props {
  n: number;
  size?: "xs" | "sm" | "md" | "lg";
  variant?: "default" | "matched" | "missed" | "hot" | "cold" | "gold";
  grad?: string;
  onClick?: () => void;
  selected?: boolean;
  index?: number;
}

const sizeMap = {
  xs: "w-7 h-7 text-[11px]",
  sm: "w-9 h-9 text-xs",
  md: "w-11 h-11 text-sm",
  lg: "w-14 h-14 text-lg",
};

export function NumberBall({ n, size = "md", variant = "default", grad, onClick, selected, index = 0 }: Props) {
  const base =
    "relative rounded-full flex items-center justify-center font-bold tnum select-none transition-all duration-200 shadow-lg";

  let style = "";
  switch (variant) {
    case "matched":
      style = "bg-gradient-to-br from-emerald-400 to-green-600 text-white ring-2 ring-emerald-300/50 shadow-glow-cyan";
      break;
    case "missed":
      style = "bg-white/[0.06] text-white/40 border border-white/10";
      break;
    case "hot":
      style = "bg-gradient-to-br from-rose-500 to-orange-500 text-white";
      break;
    case "cold":
      style = "bg-gradient-to-br from-sky-500 to-indigo-600 text-white";
      break;
    case "gold":
      style = "bg-gradient-to-br from-amber-300 to-yellow-500 text-black";
      break;
    default:
      style = grad
        ? `bg-gradient-to-br ${grad} text-white`
        : "bg-white/[0.10] backdrop-blur-xl text-white border border-white/15";
  }

  if (selected) style += " ring-2 ring-white/70 scale-105";

  return (
    <button
      type="button"
      onClick={onClick}
      style={{ animationDelay: `${index * 35}ms` }}
      className={`${base} ${sizeMap[size]} ${style} ${
        onClick ? "active:scale-90 cursor-pointer" : ""
      } animate-pop`}
    >
      <span className="absolute inset-0 rounded-full bg-gradient-to-b from-white/30 to-transparent opacity-50 pointer-events-none" />
      {n}
    </button>
  );
}
