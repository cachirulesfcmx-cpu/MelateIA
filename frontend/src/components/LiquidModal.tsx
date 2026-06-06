import { ReactNode, useEffect } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

export function LiquidModal({ open, onClose, title, children }: Props) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = "";
      };
    }
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[90] flex items-end sm:items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-md animate-fade-in"
        onClick={onClose}
      />
      <div className="relative w-full sm:max-w-md max-h-[90vh] overflow-y-auto glass-strong rounded-t-[32px] sm:rounded-[32px] p-5 pb-8 animate-slide-up safe-bottom">
        <div className="flex items-center justify-between mb-4">
          <div className="absolute left-1/2 -translate-x-1/2 top-2 w-10 h-1 rounded-full bg-white/25 sm:hidden" />
          {title && <h3 className="text-lg font-bold tracking-tight">{title}</h3>}
          <button
            onClick={onClose}
            className="ml-auto w-9 h-9 rounded-full bg-white/10 flex items-center justify-center text-white/70 hover:bg-white/20 active:scale-90 transition"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function FloatingActionButton({ onClick, label = "+" }: { onClick: () => void; label?: string }) {
  return (
    <button
      onClick={onClick}
      className="fixed right-5 bottom-28 z-40 w-14 h-14 rounded-full bg-gradient-to-br from-violet-600 to-cyan-500 shadow-glow flex items-center justify-center text-2xl font-light text-white active:scale-90 transition animate-float"
    >
      {label}
    </button>
  );
}
