import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useGames } from "../hooks";
import { PageHeader, Disclaimer } from "../components/AppLayout";
import { GlassCard, GlassButton, Spinner, SectionTitle, gameTheme } from "../components/ui";
import { GameSelector } from "../components/GameSelector";
import { BallSelector } from "../components/BallSelector";
import { PositionalSelector } from "../components/PositionalSelector";
import { NumberBall } from "../components/NumberBall";
import { HeatLegend } from "../components/NumberHeatmap";
import { useToast } from "../context/ToastContext";
import { sharePrediction } from "../shareImage";
import { getDefaultGame } from "../settings";

interface ScoreRes {
  score: number;
  features: Record<string, number>;
  tips: string[];
  number_probs: { number: number; prob: number; rel: number }[];
}

export default function Builder() {
  const games = useGames();
  const nav = useNavigate();
  const { notify } = useToast();
  const [game, setGame] = useState(getDefaultGame());
  const [intensity, setIntensity] = useState<Record<number, number>>({});
  const [selected, setSelected] = useState<number[]>([]);
  const [res, setRes] = useState<ScoreRes | null>(null);
  const [scoring, setScoring] = useState(false);

  const cfg = games.find((g) => g.key === game);
  const theme = gameTheme(game);
  const pick = cfg?.pick || 6;
  const positional = cfg?.kind === "positional";
  const [posValue, setPosValue] = useState<(number | null)[]>([]);

  useEffect(() => {
    setSelected([]);
    setPosValue(cfg?.kind === "positional" ? Array(cfg.pick).fill(null) : []);
    setRes(null);
    if (cfg?.kind === "positional") { setIntensity({}); return; }
    api.get<{ numbers: { number: number; rel: number }[] }>(`/ml/probabilities?game_type=${game}`)
      .then((p) => setIntensity(Object.fromEntries(p.numbers.map((n) => [n.number, n.rel]))))
      .catch(() => setIntensity({}));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game]);

  useEffect(() => {
    if (positional) {
      if (posValue.length !== pick || posValue.some((v) => v === null)) { setRes(null); return; }
      let cancel = false;
      setScoring(true);
      api.post<ScoreRes>("/predictions/score", { game_type: game, numbers: posValue })
        .then((r) => { if (!cancel) setRes(r); })
        .catch((e) => notify((e as Error).message, "error"))
        .finally(() => { if (!cancel) setScoring(false); });
      return () => { cancel = true; };
    }
    if (selected.length !== pick) { setRes(null); return; }
    let cancel = false;
    setScoring(true);
    api.post<ScoreRes>("/predictions/score", { game_type: game, numbers: selected })
      .then((r) => { if (!cancel) setRes(r); })
      .catch((e) => notify((e as Error).message, "error"))
      .finally(() => { if (!cancel) setScoring(false); });
    return () => { cancel = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, posValue, game]);

  function toggle(n: number) {
    setSelected((s) => (s.includes(n) ? s.filter((x) => x !== n) : s.length < pick ? [...s, n] : s));
  }

  const complete = positional ? posValue.length === pick && posValue.every((v) => v !== null) : selected.length === pick;
  const playNumbers = positional ? (posValue as number[]) : selected;

  async function save() {
    try {
      await api.post("/predictions/save", { game_type: game, strategy: "balanceada", numbers: playNumbers, score: res?.score || 0, explanation: "Construida manualmente" });
      notify("Jugada guardada ✦", "success");
    } catch (e) { notify((e as Error).message, "error"); }
  }

  const pct = res ? Math.round(res.score * 100) : 0;

  return (
    <>
      <PageHeader title="Constructor" subtitle="Arma tu jugada con la IA" right={<button onClick={() => nav("/")} className="glass rounded-2xl px-3 py-2 text-xs font-semibold active:scale-95">← Inicio</button>} />
      <div className="mb-4"><GameSelector games={games} value={game} onChange={setGame} /></div>

      <GlassCard className="mb-4">
        <SectionTitle title="Elige tus números" subtitle={positional ? "La posición importa · dígitos 0–9 (se repiten)" : "Color = probabilidad del modelo IA"} />
        {positional ? (
          <PositionalSelector
            length={pick}
            lo={cfg?.min_number ?? 0}
            hi={cfg?.max_number ?? 9}
            value={posValue.length ? posValue : Array(pick).fill(null)}
            onChange={setPosValue}
            grad={theme.grad}
          />
        ) : (
          <>
            {selected.length > 0 && (
              <div className="flex gap-1.5 flex-wrap justify-center mb-3">
                {[...selected].sort((a, b) => a - b).map((n, i) => (
                  <NumberBall key={n} n={n} size="sm" grad={theme.grad} index={i} onClick={() => toggle(n)} />
                ))}
              </div>
            )}
            <BallSelector maxNumber={cfg?.max_number || 56} pick={pick} selected={selected} onToggle={toggle} grad={theme.grad} intensity={intensity} />
            <HeatLegend />
          </>
        )}
      </GlassCard>

      {complete && (
        <GlassCard glow className="mb-4 animate-slide-up">
          {scoring && !res ? <Spinner /> : res && (
            <>
              <div className="flex items-center justify-between mb-3">
                <SectionTitle title="Evaluación IA" />
                <div className="text-right">
                  <p className="text-2xl font-extrabold tnum text-gradient">{pct}%</p>
                  <p className="text-[10px] text-white/40">score</p>
                </div>
              </div>
              <div className="h-2.5 rounded-full bg-white/10 overflow-hidden mb-4">
                <div className="h-full bg-gradient-to-r from-violet-500 to-cyan-400" style={{ width: `${pct}%` }} />
              </div>
              <div className="grid grid-cols-3 gap-2 mb-4 text-center">
                {positional ? (
                  <>
                    <Mini label="Suma" value={res.features.sum} />
                    <Mini label="Par/Impar" value={`${res.features.even}/${res.features.odd}`} />
                    <Mini label="Distintos" value={res.features.distinct} />
                    <Mini label="Repetidos" value={res.features.repeats} />
                    <Mini label="Máx" value={res.features.max_digit} />
                    <Mini label="Mín" value={res.features.min_digit} />
                  </>
                ) : (
                  <>
                    <Mini label="Suma" value={res.features.sum} />
                    <Mini label="Par/Impar" value={`${res.features.even}/${res.features.odd}`} />
                    <Mini label="Primos" value={res.features.primes} />
                    <Mini label="Rango" value={res.features.range} />
                    <Mini label="Consec." value={res.features.consecutive} />
                    <Mini label="Popular." value={`${Math.round(res.features.popularity * 100)}%`} />
                  </>
                )}
              </div>
              <p className="text-xs text-white/50 mb-2">💡 Sugerencias</p>
              <ul className="space-y-1.5 mb-4">
                {res.tips.map((t, i) => (
                  <li key={i} className="text-[13px] text-white/75 bg-white/[0.05] rounded-xl px-3 py-2">{t}</li>
                ))}
              </ul>
              <div className="flex gap-2">
                <GlassButton full onClick={save}>Guardar jugada</GlassButton>
                <GlassButton variant="ghost" onClick={() => sharePrediction({ numbers: playNumbers, gameType: game, score: res.score })}>↗</GlassButton>
              </div>
            </>
          )}
        </GlassCard>
      )}
      <Disclaimer />
    </>
  );
}

function Mini({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white/[0.05] rounded-xl py-2">
      <p className="text-sm font-bold tnum">{value}</p>
      <p className="text-[9px] text-white/40">{label}</p>
    </div>
  );
}
