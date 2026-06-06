import { createContext, useCallback, useContext, useState, ReactNode } from "react";

type ToastKind = "success" | "error" | "info";
interface Toast {
  id: number;
  message: string;
  kind: ToastKind;
}

const ToastContext = createContext<{ notify: (msg: string, kind?: ToastKind) => void }>(null!);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const notify = useCallback((message: string, kind: ToastKind = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3800);
  }, []);

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div className="fixed top-0 inset-x-0 z-[100] flex flex-col items-center gap-2 px-4 pt-3 safe-top pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto w-full max-w-sm glass-strong rounded-2xl px-4 py-3 text-sm font-medium animate-slide-up flex items-center gap-3 ${
              t.kind === "success"
                ? "border-emerald-400/40 text-emerald-100"
                : t.kind === "error"
                ? "border-rose-400/40 text-rose-100"
                : "border-white/20 text-white"
            }`}
          >
            <span className="text-lg">
              {t.kind === "success" ? "✦" : t.kind === "error" ? "⚠" : "ℹ"}
            </span>
            <span className="flex-1">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
