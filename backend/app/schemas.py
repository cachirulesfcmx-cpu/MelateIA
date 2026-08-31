"""Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ---------- Auth ----------
class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_admin: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class ForgotPassword(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str
    new_password: str = Field(min_length=6, max_length=128)


class AdminSetPassword(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class AdminCreateUser(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    is_admin: bool = False


class AdminUpdateUser(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    is_admin: Optional[bool] = None


class ProfileStats(BaseModel):
    user: UserOut
    total_predictions: int
    total_draws_added: int
    best_hits: int


# ---------- Draws ----------
class DrawCreate(BaseModel):
    game_type: str
    numbers: list[int]
    draw_number: Optional[int] = None
    draw_date: Optional[str] = None
    additional: Optional[int] = None


class DrawTextCreate(BaseModel):
    game_type: str
    text: str
    draw_number: Optional[int] = None
    draw_date: Optional[str] = None


class DrawOut(BaseModel):
    id: int
    game_type: str
    draw_number: int
    draw_date: Optional[str]
    numbers: list[int]
    additional: Optional[int]
    source: str
    created_at: datetime


class DrawCreateResult(BaseModel):
    draw: DrawOut
    evaluated_predictions: int
    users_affected: int = 0
    new_hits: list[dict]
    retrained: Optional[dict] = None


class GroupedDrawEntry(BaseModel):
    """One game's result inside a grouped (same-event) submission.

    `numbers` may be omitted/empty to skip that game; `text` is an alternative
    free-form input ("12 18 23 ..."). `additional` is the bonus (Melate R7).
    """
    numbers: Optional[list[int]] = None
    text: Optional[str] = None
    additional: Optional[int] = None


class GroupedDrawCreate(BaseModel):
    """Melate + Revancha + Revanchita are the SAME physical draw (same concurso
    and date). Submit all three at once."""
    draw_number: Optional[int] = None
    draw_date: Optional[str] = None
    melate: Optional[GroupedDrawEntry] = None
    revancha: Optional[GroupedDrawEntry] = None
    revanchita: Optional[GroupedDrawEntry] = None


class GroupedDrawResult(BaseModel):
    draw_number: Optional[int] = None
    results: list[DrawCreateResult]
    errors: list[dict]


# ---------- Predictions ----------
class PredictionGenerate(BaseModel):
    game_type: str
    strategy: str = "balanceada"
    count: int = Field(default=5, ge=1, le=50)


class GeneratedCombo(BaseModel):
    numbers: list[int]
    score: float
    explanation: str
    strategy: str
    features: dict


class PredictionGenerateOut(BaseModel):
    routed_to: Optional[str] = None
    context: Optional[str] = None
    game_type: str
    strategy: str
    combos: list[GeneratedCombo]
    # What the research layer did to these combos and what it currently knows:
    # risk filter, diversification, live audit and the NO_EDGE/EDGE state.
    research: Optional[dict] = None


class PredictionSave(BaseModel):
    game_type: str
    strategy: str
    numbers: list[int]
    score: float = 0.0
    explanation: str = ""


class PredictionResultOut(BaseModel):
    hits: int
    matched_numbers: list[int]
    missed_numbers: list[int]
    draw_number: int
    draw_id: int
    evaluated_at: datetime


class PredictionOut(BaseModel):
    id: int
    game_type: str
    strategy: str
    numbers: list[int]
    score: float
    explanation: str
    status: str
    used: bool
    created_at: datetime
    results: list[PredictionResultOut] = []
    best_hits: int = 0


# ---------- Earnings ----------
class EarningsEstimate(BaseModel):
    game_type: str
    combinations: int = Field(ge=1)
    cost_per_combination: float = Field(ge=0)
    custom_prizes: Optional[dict] = None  # override {"2": amount, ...}


# ---------- Backtesting ----------
class BacktestRequest(BaseModel):
    game_type: str
    strategy: str = "balanceada"
    last_n: int = Field(default=50, ge=5, le=500)
    combos_per_draw: int = Field(default=5, ge=1, le=20)
    cost_per_combination: float = 21.0
