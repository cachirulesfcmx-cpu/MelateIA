import { useState } from "react";
import { LiquidModal } from "./LiquidModal";
import { BallSelector } from "./BallSelector";
import { GlassButton, Capsule, gameTheme } from "./ui";
import { NumberBall } from "./NumberBall";
import { api } from "../api/client";
import { useToast } from "../context/ToastContext";
import type { Game } from "../api/types";

interface Props {
  open: boolean;
  onClose: () => void;
  games: Game[];
  defaultGame?: string;
  onSaved?: () => void;
}

export function AddDrawModal({ open, onClose, games, defaultGame, onSaved }: Props) {
  const { notify } = useToast();
  const [game, setGame] = useState(defaultGame || games[0]?.key || "melate");
  const [mode, setMode] = useState<"balls" | "text">("balls");
  const [selected, setSelected] = useState<number[]>([]);
  const [text, setText] = useState("");
  const [drawNumber, setDrawNumber] = useState("");
  const [date, setDate] = useState("");
  const [saving, setSaving] = useState(false);

  const cfg = games.find((g) => g.key === game);
  const theme = gameTheme(game);

  function toggle(n: number) {
    setSelected((s) => (s.includes(n) ? s.filter((x) => x !== n) : s.length < (cfg?.pick || 6) ? [...s, n] : s));
  }

  function reset() {
    setSelected([]);
    setText("");
    setDrawNumber("");
    setDate("");
  }

  async function save() {
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        game_type: game,
        draw_number: drawNumber ? parseInt(drawNumber) : undefined,
        draw_date: date || undefined,
      };
      let res;
      if (mode === "balls") {
        if (selected.length !== (cfg?.pick || 6)) {
          notify(`Selecciona ${cfg?.pick} números`, "error");
          setSaving(false);
          return;
        }
        res = await api.post<{ draw: { draw_number: number }; evaluated_predictions: number; new_hits: any[] }>(
          "/draws",
          { ...payload, numbers: selected }
        );
      } else {
        res = await api.post<{ draw: { draw_number: number }; evaluated_predictions: number; new_hits: any[] }>(
          "/draws/text",
          { ...payload, text }
        );
      }
      const hits = res.new_hits?.length || 0;
      notify(
        hits > 0
          ? `Sorteo #${res.draw.draw_number} guardado · ¡${hits} predicción(es) con aciertos!`
          : `Sorteo #${res.draw.draw_number} guardado y comparado`,
        "success"
      );
      reset();
      onSaved?.();
      onClose();
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <LiquidModal open={open} onClose={onClose} title="Agregar sorteo real">
      <div className="space-y-4">
        <div className="flex gap-2 overflow-x-auto pb-1 no-scrollbar">
          {games.map((g) => (
            <Capsule key={g.key} active={g.key === game} onClick={() => { setGame(g.key); setSelected([]); }}>
              {gameTheme(g.key).emoji} {g.label}
            </Capsule>
          ))}
        </div>

        <div className="flex gap-2 p-1 bg-white/5 rounded-2xl">
          <button
            onClick={() => setMode("balls")}
            className={`flex-1 py-2 rounded-xl text-sm font-semibold transition ${mode === "balls" ? "bg-white/15 text-white" : "text-white/50"}`}
          >
            🎱 Selector visual
          </button>
          <button
            onClick={() => setMode("text")}
            className={`flex-1 py-2 rounded-xl text-sm font-semibold transition ${mode === "text" ? "bg-white/15 text-white" : "text-white/50"}`}
          >
            ⌨️ Texto
          </button>
        </div>

        {mode === "balls" ? (
          <>
            {selected.length > 0 && (
              <div className="flex gap-1.5 flex-wrap justify-center py-2">
                {[...selected].sort((a, b) => a - b).map((n, i) => (
                  <NumberBall key={n} n={n} size="sm" grad={theme.grad} index={i} onClick={() => toggle(n)} />
                ))}
              </div>
            )}
            <BallSelector
              maxNumber={cfg?.max_number || 56}
              pick={cfg?.pick || 6}
              selected={selected}
              onToggle={toggle}
              grad={theme.grad}
            />
          </>
        ) : (
          <div>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="glass-input w-full tnum text-lg tracking-wide"
              placeholder="12 18 23 34 45 51"
            />
            <p className="text-xs text-white/40 mt-2 ml-1">Separa con espacios o comas · ej: 12,18,23,34,45,51</p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-white/50 ml-1">Concurso (opcional)</label>
            <input value={drawNumber} onChange={(e) => setDrawNumber(e.target.value)} className="glass-input w-full mt-1 tnum" placeholder="Auto" inputMode="numeric" />
          </div>
          <div>
            <label className="text-xs text-white/50 ml-1">Fecha (opcional)</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="glass-input w-full mt-1" />
          </div>
        </div>

        <GlassButton full size="lg" onClick={save} disabled={saving}>
          {saving ? "Guardando…" : "Guardar y comparar"}
        </GlassButton>
        <p className="text-[11px] text-white/40 text-center">
          Al guardar se comparará automáticamente con tus predicciones pendientes.
        </p>
      </div>
    </LiquidModal>
  );
}
