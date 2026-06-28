import { useState } from "react";
import { LiquidModal } from "./LiquidModal";
import { BallSelector } from "./BallSelector";
import { PositionalSelector } from "./PositionalSelector";
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

type DrawRes = {
  draw: { draw_number: number; game_type: string };
  evaluated_predictions: number;
  users_affected: number;
  new_hits: unknown[];
  retrained?: { trained?: boolean } | null;
};

// Melate, Revancha and Revanchita are the SAME physical draw (same concurso & date).
const GROUPED = ["melate", "revancha", "revanchita"];

export function AddDrawModal({ open, onClose, games, defaultGame, onSaved }: Props) {
  const { notify } = useToast();
  const [game, setGame] = useState(defaultGame || games[0]?.key || "melate");
  const [mode, setMode] = useState<"balls" | "text">("balls");
  const [selected, setSelected] = useState<number[]>([]);
  const [posValue, setPosValue] = useState<(number | null)[]>([]);
  const [text, setText] = useState("");
  const [drawNumber, setDrawNumber] = useState("");
  const [date, setDate] = useState("");
  const [saving, setSaving] = useState(false);

  // grouped (3-en-1) state
  const groupedAvailable = GROUPED.every((g) => games.some((x) => x.key === g));
  const [grouped, setGrouped] = useState(false);
  const [gNums, setGNums] = useState<Record<string, number[]>>({ melate: [], revancha: [], revanchita: [] });
  const [gText, setGText] = useState<Record<string, string>>({ melate: "", revancha: "", revanchita: "" });
  const [bonus, setBonus] = useState("");
  const [tab, setTab] = useState("melate");

  const cfg = games.find((g) => g.key === game);
  const theme = gameTheme(game);
  const positional = cfg?.kind === "positional";

  function toggle(n: number) {
    setSelected((s) => (s.includes(n) ? s.filter((x) => x !== n) : s.length < (cfg?.pick || 6) ? [...s, n] : s));
  }

  function changeGame(key: string) {
    setGame(key);
    setSelected([]);
    const g = games.find((x) => x.key === key);
    setPosValue(g?.kind === "positional" ? Array(g.pick).fill(null) : []);
  }

  function reset() {
    setSelected([]);
    setPosValue(positional && cfg ? Array(cfg.pick).fill(null) : []);
    setText("");
    setDrawNumber("");
    setDate("");
    setGNums({ melate: [], revancha: [], revanchita: [] });
    setGText({ melate: "", revancha: "", revanchita: "" });
    setBonus("");
    setTab("melate");
  }

  function toggleGrouped(g: string, n: number) {
    setGNums((s) => {
      const cur = s[g] || [];
      const next = cur.includes(n) ? cur.filter((x) => x !== n) : cur.length < 6 ? [...cur, n] : cur;
      return { ...s, [g]: next };
    });
  }

  async function saveGrouped() {
    // build entries from balls or text
    const entries: Record<string, { numbers?: number[]; text?: string; additional?: number }> = {};
    let any = false;
    for (const g of GROUPED) {
      const hasText = mode === "text" && gText[g].trim();
      const hasBalls = mode === "balls" && (gNums[g] || []).length > 0;
      if (!hasText && !hasBalls) continue;
      if (mode === "balls" && gNums[g].length !== 6) {
        notify(`${games.find((x) => x.key === g)?.label}: selecciona 6 números (llevas ${gNums[g].length})`, "error");
        return;
      }
      const e: { numbers?: number[]; text?: string; additional?: number } = {};
      if (mode === "balls") e.numbers = [...gNums[g]].sort((a, b) => a - b);
      else e.text = gText[g];
      if (g === "melate" && bonus) e.additional = parseInt(bonus);
      entries[g] = e;
      any = true;
    }
    if (!any) {
      notify("Ingresa el resultado de al menos un sorteo", "error");
      return;
    }
    setSaving(true);
    try {
      const res = await api.post<{ draw_number: number; results: DrawRes[]; errors: { game_type: string; error: string }[] }>(
        "/draws/grouped",
        { draw_number: drawNumber ? parseInt(drawNumber) : undefined, draw_date: date || undefined, ...entries },
      );
      const ok = res.results.map((r) => games.find((x) => x.key === r.draw.game_type)?.label || r.draw.game_type);
      const totalEval = res.results.reduce((s, r) => s + r.evaluated_predictions, 0);
      const parts = [`Concurso #${res.draw_number}: ${ok.join(" · ")} guardados`];
      if (totalEval > 0) parts.push(`${totalEval} predicción(es) evaluadas`);
      notify(parts.join(" · "), "success");
      if (res.errors.length) notify(res.errors.map((e) => `${e.game_type}: ${e.error}`).join(" · "), "error");
      reset();
      onSaved?.();
      onClose();
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  async function save() {
    if (grouped) return saveGrouped();
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        game_type: game,
        draw_number: drawNumber ? parseInt(drawNumber) : undefined,
        draw_date: date || undefined,
      };
      let res: DrawRes;
      if (mode === "balls") {
        if (positional) {
          if (posValue.length !== (cfg?.pick || 5) || posValue.some((v) => v === null)) {
            notify(`Completa las ${cfg?.pick} posiciones`, "error");
            setSaving(false);
            return;
          }
          res = await api.post<DrawRes>("/draws", { ...payload, numbers: posValue });
        } else {
          if (selected.length !== (cfg?.pick || 6)) {
            notify(`Selecciona ${cfg?.pick} números`, "error");
            setSaving(false);
            return;
          }
          res = await api.post<DrawRes>("/draws", { ...payload, numbers: selected });
        }
      } else {
        res = await api.post<DrawRes>("/draws/text", { ...payload, text });
      }
      const hits = res.new_hits?.length || 0;
      const parts = [`Sorteo #${res.draw.draw_number} guardado`];
      if (res.evaluated_predictions > 0)
        parts.push(`${res.evaluated_predictions} predicción(es) de ${res.users_affected} usuario(s) evaluadas`);
      if (hits > 0) parts.push(`¡${hits} con aciertos!`);
      if (res.retrained?.trained) parts.push("sistema reentrenado");
      notify(parts.join(" · "), "success");
      reset();
      onSaved?.();
      onClose();
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  const tabTheme = gameTheme(tab);
  const tabCount = (gNums[tab] || []).length;

  return (
    <LiquidModal open={open} onClose={onClose} title={grouped ? "Agregar sorteo (3 en 1)" : "Agregar sorteo real"}>
      <div className="space-y-4">
        {groupedAvailable && (
          <div className="flex gap-2 p-1 bg-white/5 rounded-2xl">
            <button
              onClick={() => setGrouped(false)}
              className={`flex-1 py-2 rounded-xl text-sm font-semibold transition ${!grouped ? "bg-white/15 text-white" : "text-white/50"}`}
            >
              Individual
            </button>
            <button
              onClick={() => setGrouped(true)}
              className={`flex-1 py-2 rounded-xl text-sm font-semibold transition ${grouped ? "bg-gradient-to-r from-rose-500 to-amber-400 text-white" : "text-white/50"}`}
            >
              🎰 Melate · Revancha · Revanchita
            </button>
          </div>
        )}

        {grouped && (
          <p className="text-[11px] text-white/45 -mt-1 px-1">
            Son el mismo sorteo: comparten concurso y fecha. Captura los 3 resultados aquí.
          </p>
        )}

        {!grouped && (
          <div className="flex gap-2 overflow-x-auto pb-1 no-scrollbar">
            {games.map((g) => (
              <Capsule key={g.key} active={g.key === game} onClick={() => changeGame(g.key)}>
                {gameTheme(g.key).emoji} {g.label}
              </Capsule>
            ))}
          </div>
        )}

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

        {grouped ? (
          <div className="space-y-3">
            {/* per-game tabs with completion badges */}
            <div className="flex gap-2">
              {GROUPED.map((g) => {
                const done = mode === "text" ? gText[g].trim().length > 0 : (gNums[g] || []).length === 6;
                const partial = mode === "balls" && (gNums[g] || []).length > 0 && (gNums[g] || []).length < 6;
                return (
                  <button
                    key={g}
                    onClick={() => setTab(g)}
                    className={`flex-1 py-2 rounded-xl text-xs font-semibold transition flex items-center justify-center gap-1 ${
                      tab === g ? "bg-white/15 text-white ring-1 ring-white/20" : "bg-white/5 text-white/50"
                    }`}
                  >
                    {gameTheme(g).emoji} {games.find((x) => x.key === g)?.label}
                    {done && <span className="text-emerald-400">✓</span>}
                    {partial && <span className="text-amber-400">…</span>}
                  </button>
                );
              })}
            </div>

            {mode === "balls" ? (
              <>
                {(gNums[tab] || []).length > 0 && (
                  <div className="flex gap-1.5 flex-wrap justify-center py-1">
                    {[...(gNums[tab] || [])].sort((a, b) => a - b).map((n, i) => (
                      <NumberBall key={n} n={n} size="sm" grad={tabTheme.grad} index={i} onClick={() => toggleGrouped(tab, n)} />
                    ))}
                  </div>
                )}
                <div className="text-[11px] text-white/40 text-center -mt-1">{tabCount}/6 números</div>
                <BallSelector maxNumber={56} pick={6} selected={gNums[tab] || []} onToggle={(n) => toggleGrouped(tab, n)} grad={tabTheme.grad} />
                {tab === "melate" && (
                  <div>
                    <label className="text-xs text-white/50 ml-1">Número adicional (R7, opcional)</label>
                    <input value={bonus} onChange={(e) => setBonus(e.target.value)} className="glass-input w-full mt-1 tnum" placeholder="—" inputMode="numeric" />
                  </div>
                )}
              </>
            ) : (
              <div className="space-y-2">
                {GROUPED.map((g) => (
                  <div key={g}>
                    <label className="text-xs text-white/50 ml-1 flex items-center gap-1">
                      {gameTheme(g).emoji} {games.find((x) => x.key === g)?.label}
                    </label>
                    <input
                      value={gText[g]}
                      onChange={(e) => setGText((s) => ({ ...s, [g]: e.target.value }))}
                      className="glass-input w-full mt-1 tnum tracking-wide"
                      placeholder="12 18 23 34 45 51"
                    />
                  </div>
                ))}
                <div>
                  <label className="text-xs text-white/50 ml-1">Adicional Melate (R7, opcional)</label>
                  <input value={bonus} onChange={(e) => setBonus(e.target.value)} className="glass-input w-full mt-1 tnum" placeholder="—" inputMode="numeric" />
                </div>
              </div>
            )}
          </div>
        ) : mode === "balls" ? (
          positional ? (
            <PositionalSelector
              length={cfg?.pick || 5}
              lo={cfg?.min_number ?? 0}
              hi={cfg?.max_number ?? 9}
              value={posValue.length ? posValue : Array(cfg?.pick || 5).fill(null)}
              onChange={setPosValue}
              grad={theme.grad}
            />
          ) : (
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
          )
        ) : (
          <div>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="glass-input w-full tnum text-lg tracking-wide"
              placeholder={positional ? "5 8 0 5 2" : "12 18 23 34 45 51"}
            />
            <p className="text-xs text-white/40 mt-2 ml-1">
              {positional
                ? "El orden importa · 5 dígitos 0–9, se repiten · ej: 5,8,0,5,2"
                : "Separa con espacios o comas · ej: 12,18,23,34,45,51"}
            </p>
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
          {saving ? "Guardando…" : grouped ? "Guardar los 3 y comparar" : "Guardar y comparar"}
        </GlassButton>
        <p className="text-[11px] text-white/40 text-center">
          Al guardar se comparará automáticamente con tus predicciones pendientes.
        </p>
      </div>
    </LiquidModal>
  );
}
