import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useGames } from "../hooks";
import { PageHeader } from "../components/AppLayout";
import { GlassCard, Spinner, gameTheme } from "../components/ui";
import { GameSelector } from "../components/GameSelector";

interface Msg { role: "user" | "assistant"; content: string; }

const SUGGESTIONS = [
  "¿Qué estrategia me conviene y por qué?",
  "Explícame los números calientes y fríos de hoy",
  "¿Qué significa el backtesting y la ventaja vs azar?",
  "¿Cómo funciona el aprendizaje del sistema?",
];

export default function AssistantChat() {
  const games = useGames();
  const nav = useNavigate();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [game, setGame] = useState("melate");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<{ enabled: boolean }>("/assistant/status").then((s) => setEnabled(s.enabled)).catch(() => setEnabled(false));
  }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const history = msgs.slice(-8);
    setMsgs((m) => [...m, { role: "user", content: q }]);
    setInput("");
    setBusy(true);
    try {
      const r = await api.post<{ reply: string }>("/assistant/chat", { message: q, history, game_type: game });
      setMsgs((m) => [...m, { role: "assistant", content: r.reply }]);
    } catch (err) {
      setMsgs((m) => [...m, { role: "assistant", content: (err as Error).message }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Asistente IA"
        subtitle="Pregúntale sobre estrategias y estadísticas"
        right={<button onClick={() => nav("/")} className="glass rounded-2xl px-3 py-2 text-xs font-semibold active:scale-95">← Inicio</button>}
      />

      {enabled === null ? (
        <Spinner />
      ) : enabled === false ? (
        <GlassCard className="text-center py-8">
          <div className="text-5xl mb-3">🤖</div>
          <p className="text-white/70 font-semibold">El asistente IA aún no está activo</p>
          <p className="text-xs text-white/40 mt-1">Configura <code>ANTHROPIC_API_KEY</code> para habilitarlo.</p>
        </GlassCard>
      ) : (
        <>
          <div className="mb-3"><GameSelector games={games} value={game} onChange={setGame} /></div>

          <div className="space-y-3 mb-4">
            {msgs.length === 0 && (
              <GlassCard>
                <p className="text-sm text-white/70 mb-3">👋 Soy tu asistente. Pregúntame sobre estrategias, números calientes/fríos, backtesting o el estimador.</p>
                <div className="grid grid-cols-1 gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)} className="text-left text-[13px] glass rounded-2xl px-3 py-2.5 hover:bg-white/10 active:scale-[0.98] transition">
                      {s}
                    </button>
                  ))}
                </div>
              </GlassCard>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-3xl px-4 py-2.5 text-[14px] leading-relaxed whitespace-pre-wrap ${
                  m.role === "user"
                    ? `bg-gradient-to-br ${gameTheme(game).grad} text-white`
                    : "glass text-white/90"
                }`}>
                  {m.content}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="glass rounded-3xl px-4 py-3 text-white/60 text-sm">escribiendo…</div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <div className="fixed bottom-24 inset-x-0 px-4 z-30">
            <div className="mx-auto max-w-md flex items-center gap-2 glass-strong rounded-3xl p-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send(input)}
                placeholder="Escribe tu pregunta…"
                className="flex-1 bg-transparent outline-none px-3 text-sm text-white placeholder-white/40"
              />
              <button onClick={() => send(input)} disabled={busy || !input.trim()} className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-600 to-cyan-500 flex items-center justify-center text-white disabled:opacity-40 active:scale-90 transition">
                ➤
              </button>
            </div>
          </div>
          <div className="h-16" />
        </>
      )}
    </>
  );
}
