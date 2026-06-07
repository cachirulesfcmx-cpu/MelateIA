"""AI assistant powered by Claude (Anthropic).

Disabled gracefully when ANTHROPIC_API_KEY is not set. Uses only the stdlib
(urllib) so it adds no serverless dependencies.
"""
import json
import urllib.request
import urllib.error

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User, Draw
from ..auth import get_current_user
from ..security import enforce_rate_limit
from ..engine.game_config import GAMES
from ..engine.data_engine import str_to_numbers
from ..services import build_stats

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

SYSTEM = (
    "Eres el asistente de MelateAI Pro, una app móvil de análisis estadístico y "
    "predicción optimizada de los sorteos mexicanos Melate, Revancha, Melate Retro y "
    "Revanchita. Ayudas al usuario a interpretar estadísticas (números calientes/fríos, "
    "atrasos/gaps, frecuencias, sumas, pares/impares, primos), entender las estrategias "
    "(conservadora, balanceada, agresiva, genética, anti-popular, calientes, fríos, "
    "híbrida y adaptativa), el backtesting, el estimador de ganancias y el aprendizaje por "
    "refuerzo del sistema. Reglas: responde SIEMPRE en español, claro y conciso; usa los "
    "datos de contexto si se proveen; y deja claro de forma honesta que la lotería es un "
    "juego de AZAR, que ninguna IA puede garantizar premios y que se debe jugar con "
    "responsabilidad. No inventes números 'ganadores garantizados'."
)


class Msg(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Msg] = []
    game_type: str | None = None


@router.get("/status")
def status(user: User = Depends(get_current_user)):
    return {"enabled": bool(settings.anthropic_api_key), "model": settings.anthropic_model}


def _context(db: Session, game_type: str | None) -> str:
    if not game_type or game_type not in GAMES:
        return ""
    try:
        stats, cfg = build_stats(db, game_type)
        if not stats.draws:
            return ""
        last = db.query(Draw).filter(Draw.game_type == game_type).order_by(Draw.draw_number.desc()).first()
        hot = stats.hot_numbers(50, 8)
        cold = stats.cold_numbers(50, 8)
        overdue = stats.overdue_numbers(8)
        parts = [f"Contexto {cfg.label} ({len(stats.draws)} sorteos):"]
        if last:
            parts.append(f"último sorteo #{last.draw_number}: {str_to_numbers(last.numbers)}")
        parts.append(f"calientes(50): {hot}")
        parts.append(f"fríos(50): {cold}")
        parts.append(f"más atrasados: {overdue}")
        return " ".join(parts)
    except Exception:
        return ""


@router.post("/chat")
def chat(payload: ChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not settings.anthropic_api_key:
        return {"enabled": False, "reply": "El asistente IA aún no está configurado (falta ANTHROPIC_API_KEY)."}
    enforce_rate_limit(db, f"assistant:{user.id}", limit=40, window_seconds=3600)

    system = SYSTEM
    ctx = _context(db, payload.game_type)
    if ctx:
        system += "\n\nDatos en vivo para fundamentar tu respuesta: " + ctx

    messages = [{"role": m.role, "content": m.content} for m in payload.history[-8:] if m.role in ("user", "assistant")]
    messages.append({"role": "user", "content": payload.message})

    body = json.dumps({
        "model": settings.anthropic_model,
        "max_tokens": 700,
        "system": system,
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "User-Agent": "MelateAI-Pro/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        reply = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return {"enabled": True, "reply": reply or "(sin respuesta)"}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:200]
        except Exception:
            pass
        return {"enabled": True, "reply": f"No pude consultar al asistente ahora (error {e.code}). Intenta más tarde.", "error": detail}
    except Exception:
        return {"enabled": True, "reply": "No pude consultar al asistente ahora. Intenta más tarde."}
