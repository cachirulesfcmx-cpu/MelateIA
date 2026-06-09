"""Earnings estimator endpoint."""
from fastapi import APIRouter, Depends, HTTPException

from ..schemas import EarningsEstimate
from ..auth import get_current_user
from ..models import User
from ..engine.game_config import GAME_KEYS, get_game
from ..engine.earnings import estimate

router = APIRouter(prefix="/api/earnings", tags=["earnings"])


@router.post("/estimate")
def earnings_estimate(payload: EarningsEstimate, user: User = Depends(get_current_user)):
    if payload.game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    cfg = get_game(payload.game_type)
    if cfg.kind == "positional":
        from ..engine.positional import pos_earnings
        return pos_earnings(cfg, payload.combinations, payload.cost_per_combination, payload.custom_prizes)
    return estimate(
        payload.game_type, payload.combinations, payload.cost_per_combination, payload.custom_prizes
    )
