import { NavLink } from "react-router-dom";

const items = [
  { to: "/", label: "Inicio", icon: HomeIcon },
  { to: "/predicciones", label: "Predicción", icon: SparkIcon },
  { to: "/historial", label: "Historial", icon: ClockIcon },
  { to: "/sorteos", label: "Sorteos", icon: GridIcon },
  { to: "/perfil", label: "Perfil", icon: UserIcon },
];

export function BottomNav() {
  return (
    <nav className="fixed bottom-0 inset-x-0 z-40 px-4 pb-[max(env(safe-area-inset-bottom),12px)] pt-2 pointer-events-none">
      <div className="pointer-events-auto mx-auto max-w-md glass-strong rounded-[28px] px-2 py-2 flex justify-between shadow-glass">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `relative flex-1 flex flex-col items-center gap-1 py-2 rounded-2xl transition-all ${
                isActive ? "text-white" : "text-white/45 hover:text-white/70"
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span className="absolute inset-1 rounded-2xl bg-gradient-to-br from-violet-500/30 to-cyan-500/25 border border-white/15 shadow-glow -z-0" />
                )}
                <Icon className={`w-[22px] h-[22px] relative z-10 ${isActive ? "scale-110" : ""} transition-transform`} />
                <span className="text-[10px] font-medium relative z-10">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

type IP = { className?: string };
function HomeIcon({ className }: IP) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" />
    </svg>
  );
}
function SparkIcon({ className }: IP) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4" /><path d="M12 8a4 4 0 0 0 4 4 4 4 0 0 0-4 4 4 4 0 0 0-4-4 4 4 0 0 0 4-4Z" />
    </svg>
  );
}
function ClockIcon({ className }: IP) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
    </svg>
  );
}
function GridIcon({ className }: IP) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7" cy="7" r="3" /><circle cx="17" cy="7" r="3" /><circle cx="7" cy="17" r="3" /><circle cx="17" cy="17" r="3" />
    </svg>
  );
}
function UserIcon({ className }: IP) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
    </svg>
  );
}
