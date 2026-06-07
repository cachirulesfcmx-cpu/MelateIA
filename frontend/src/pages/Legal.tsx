import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/AppLayout";
import { GlassCard } from "../components/ui";

export default function Legal() {
  const nav = useNavigate();
  return (
    <>
      <PageHeader
        title="Información"
        subtitle="Juego responsable y términos"
        right={<button onClick={() => nav("/perfil")} className="glass rounded-2xl px-3 py-2 text-xs font-semibold active:scale-95">← Perfil</button>}
      />
      <div className="space-y-4">
        <GlassCard className="border-amber-400/30">
          <h2 className="text-lg font-bold mb-2">🎲 Juego responsable</h2>
          <p className="text-sm text-white/70 leading-relaxed">
            Melate, Revancha, Melate Retro y Revanchita son <b className="text-white">juegos de azar</b>.
            Los resultados son <b className="text-white">aleatorios e independientes</b>: ningún sistema,
            estadística ni inteligencia artificial puede predecir ni garantizar premios. La esperanza
            matemática de la lotería es <b className="text-white">negativa</b>.
          </p>
          <ul className="text-sm text-white/60 list-disc pl-5 mt-3 space-y-1">
            <li>Juega solo con dinero que puedas permitirte perder.</li>
            <li>No persigas pérdidas ni juegues para resolver problemas económicos.</li>
            <li>Establece límites de tiempo y de gasto.</li>
            <li>Si el juego deja de ser entretenimiento, busca ayuda.</li>
          </ul>
        </GlassCard>

        <GlassCard>
          <h2 className="text-base font-bold mb-2">¿Qué hace MelateAI Pro?</h2>
          <p className="text-sm text-white/70 leading-relaxed">
            Es una herramienta <b className="text-white">educativa y de análisis estadístico</b>. Genera
            combinaciones <b className="text-white">optimizadas estadísticamente</b>, registra resultados
            reales, compara aciertos y mide su desempeño histórico contra el azar. <b className="text-white">No
            promete resultados</b> ni constituye asesoría financiera.
          </p>
        </GlassCard>

        <GlassCard>
          <h2 className="text-base font-bold mb-2">Términos y privacidad</h2>
          <p className="text-sm text-white/60 leading-relaxed">
            Al usar la app aceptas que las predicciones son orientativas y sin garantía. Guardamos tu
            cuenta (nombre, email), tus predicciones y los sorteos que registres, para ofrecer el
            servicio. No vendemos tus datos. Puedes solicitar la eliminación de tu cuenta al
            administrador.
          </p>
        </GlassCard>

        <p className="text-center text-[11px] text-white/30">MelateAI Pro · No afiliado a Pronósticos para la Asistencia Pública.</p>
      </div>
    </>
  );
}
