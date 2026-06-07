/** Render a prediction as a shareable PNG (Liquid Glass style) and share/download it. */

const GAME_LABELS: Record<string, string> = {
  melate: "Melate",
  revancha: "Revancha",
  melate_retro: "Melate Retro",
  revanchita: "Revanchita",
};
const GAME_COLORS: Record<string, [string, string]> = {
  melate: ["#34d399", "#0d9488"],
  revancha: ["#d946ef", "#7c3aed"],
  melate_retro: ["#fbbf24", "#f97316"],
  revanchita: ["#38bdf8", "#2563eb"],
};

export async function sharePrediction(opts: {
  numbers: number[];
  gameType: string;
  strategy?: string;
  score?: number;
}) {
  const { numbers, gameType, strategy, score } = opts;
  const W = 1080, H = 1080;
  const canvas = document.createElement("canvas");
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d")!;

  // background
  const bg = ctx.createLinearGradient(0, 0, W, H);
  bg.addColorStop(0, "#0a0a16"); bg.addColorStop(1, "#06060a");
  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
  // ambient blobs
  const blob = (x: number, y: number, r: number, c: string) => {
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, c); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  };
  blob(180, 160, 420, "rgba(124,58,237,0.55)");
  blob(920, 980, 460, "rgba(6,182,212,0.45)");

  // header
  ctx.textAlign = "center";
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 64px -apple-system, Segoe UI, Roboto, sans-serif";
  ctx.fillText("🎰 MelateAI Pro", W / 2, 150);
  ctx.fillStyle = "rgba(255,255,255,0.55)";
  ctx.font = "500 36px -apple-system, Segoe UI, Roboto, sans-serif";
  ctx.fillText(GAME_LABELS[gameType] || gameType, W / 2, 215);

  // balls
  const [c1, c2] = GAME_COLORS[gameType] || ["#7c3aed", "#06b6d4"];
  const sorted = [...numbers].sort((a, b) => a - b);
  const n = sorted.length;
  const r = 84, gap = 36;
  const totalW = n * (r * 2) + (n - 1) * gap;
  let x = (W - totalW) / 2 + r;
  const y = H / 2;
  sorted.forEach((num) => {
    const g = ctx.createLinearGradient(x - r, y - r, x + r, y + r);
    g.addColorStop(0, c1); g.addColorStop(1, c2);
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    // gloss
    ctx.fillStyle = "rgba(255,255,255,0.25)";
    ctx.beginPath(); ctx.ellipse(x, y - r * 0.4, r * 0.6, r * 0.32, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 78px -apple-system, Segoe UI, Roboto, sans-serif";
    ctx.textBaseline = "middle";
    ctx.fillText(String(num), x, y + 4);
    ctx.textBaseline = "alphabetic";
    x += r * 2 + gap;
  });

  // strategy + score chip
  if (strategy) {
    ctx.fillStyle = "rgba(255,255,255,0.7)";
    ctx.font = "600 40px -apple-system, Segoe UI, Roboto, sans-serif";
    const conf = score != null ? ` · ${Math.round(score * 100)}% confianza` : "";
    ctx.fillText(`Estrategia: ${strategy}${conf}`, W / 2, y + 220);
  }

  // disclaimer
  ctx.fillStyle = "rgba(255,255,255,0.4)";
  ctx.font = "400 30px -apple-system, Segoe UI, Roboto, sans-serif";
  ctx.fillText("Combinación optimizada estadísticamente · el azar manda", W / 2, H - 150);
  ctx.fillStyle = "rgba(255,255,255,0.55)";
  ctx.font = "600 34px -apple-system, Segoe UI, Roboto, sans-serif";
  ctx.fillText("melastia.com", W / 2, H - 90);

  const blobData: Blob = await new Promise((res) => canvas.toBlob((b) => res(b!), "image/png"));
  const file = new File([blobData], "melateai-prediccion.png", { type: "image/png" });

  // Prefer native share with file (iOS), else download
  const navAny = navigator as any;
  if (navAny.canShare && navAny.canShare({ files: [file] })) {
    try {
      await navAny.share({ files: [file], title: "MelateAI Pro", text: "Mi combinación optimizada" });
      return;
    } catch {
      /* user cancelled -> fall through to download */
    }
  }
  const url = URL.createObjectURL(blobData);
  const a = document.createElement("a");
  a.href = url; a.download = "melateai-prediccion.png"; a.click();
  URL.revokeObjectURL(url);
}
