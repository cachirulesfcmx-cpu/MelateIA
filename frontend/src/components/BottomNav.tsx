import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { createPortal } from "react-dom";

const items = [
  { to: "/", label: "Inicio", icon: HomeIcon },
  { to: "/predicciones", label: "Predicción", icon: SparkIcon },
  { to: "/historial", label: "Historial", icon: ClockIcon },
  { to: "/sorteos", label: "Sorteos", icon: GridIcon },
  { to: "/perfil", label: "Perfil", icon: UserIcon },
];

export function BottomNav() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const lastY = useRef(0);

  // Collapse to a single "current page" pill when scrolling down, expand back
  // to the full bar when scrolling up or near the top (like the reference apps).
  useEffect(() => {
    lastY.current = window.scrollY;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const y = window.scrollY;
        if (y < 56) setCollapsed(false);
        else if (y > lastY.current + 8) setCollapsed(true);
        else if (y < lastY.current - 8) setCollapsed(false);
        lastY.current = y;
        ticking = false;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Always show the full bar right after navigating.
  useEffect(() => {
    setCollapsed(false);
    lastY.current = window.scrollY;
  }, [location.pathname]);

  const active =
    items.find((i) => (i.to === "/" ? location.pathname === "/" : location.pathname.startsWith(i.to))) || items[0];
  const ActiveIcon = active.icon;

  const nav = (
    <nav className="fixed bottom-0 inset-x-0 z-40 px-4 pb-[max(env(safe-area-inset-bottom),12px)] pt-2 pointer-events-none flex justify-center">
      {collapsed ? (
        <button
          onClick={() => setCollapsed(false)}
          aria-label={`${active.label} — tocar para expandir el menú`}
          className="pointer-events-auto glass-strong rounded-full pl-3.5 pr-5 py-2.5 flex items-center gap-2.5 shadow-glass animate-scale-in active:scale-95"
        >
          <span className="relative flex items-center justify-center w-9 h-9">
            <span className="absolute inset-0 rounded-full bg-gradient-to-br from-violet-500/35 to-cyan-500/30 border border-white/15 shadow-glow" />
            <ActiveIcon className="w-[20px] h-[20px] relative z-10 text-white" />
          </span>
          <span className="text-[13px] font-semibold text-white">{active.label}</span>
        </button>
      ) : (
        <div className="pointer-events-auto w-full max-w-md glass-strong rounded-[28px] px-2 py-2 flex justify-between shadow-glass animate-fade-in">
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
      )}
    </nav>
  );

  // Portal to <body> so the fixed positioning is anchored to the viewport and
  // never trapped by an ancestor with a transform/filter (which would otherwise
  // make the bar float in the middle of the page).
  return createPortal(nav, document.body);
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
