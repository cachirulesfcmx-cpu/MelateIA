"""Draw endpoints: list, add (text/balls), CSV upload, statistics."""
from collections import Counter
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Draw, User, CsvUpload
from ..schemas import DrawCreate, DrawTextCreate, DrawCreateResult, DrawOut
from ..auth import get_current_user, get_current_admin
from ..engine.game_config import get_game, validate_combination, GAME_KEYS, GAMES
from ..engine.data_engine import parse_csv, parse_number_text, numbers_to_str, str_to_numbers
from ..engine.features import GameStats, is_prime
from ..services import evaluate_new_draw, load_draw_rows

router = APIRouter(prefix="/api/draws", tags=["draws"])


def _draw_out(d: Draw) -> dict:
    return {
        "id": d.id,
        "game_type": d.game_type,
        "draw_number": d.draw_number,
        "draw_date": d.draw_date,
        "numbers": str_to_numbers(d.numbers),
        "additional": d.additional,
        "source": d.source,
        "created_at": d.created_at,
    }


@router.get("/games")
def list_games():
    return [
        {"key": k, "label": g.label, "max_number": g.max_number, "pick": g.pick}
        for k, g in GAMES.items()
    ]


@router.get("")
def list_draws(
    game_type: str | None = None,
    number: int | None = Query(default=None),
    date: str | None = None,
    draw_number: int | None = None,
    limit: int = Query(default=100, le=2000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Draw)
    if game_type:
        q = q.filter(Draw.game_type == game_type)
    if date:
        q = q.filter(Draw.draw_date == date)
    if draw_number:
        q = q.filter(Draw.draw_number == draw_number)
    q = q.order_by(Draw.draw_number.desc())
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    out = [_draw_out(d) for d in rows]
    if number is not None:
        out = [d for d in out if number in d["numbers"] or d["additional"] == number]
    return {"total": total, "draws": out}


def _next_draw_number(db: Session, game_type: str) -> int:
    last = (
        db.query(Draw)
        .filter(Draw.game_type == game_type)
        .order_by(Draw.draw_number.desc())
        .first()
    )
    return (last.draw_number + 1) if last else 1


def _create_draw(db, user, game_type, numbers, draw_number, draw_date, additional, source):
    try:
        numbers = validate_combination(game_type, numbers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if draw_number is None:
        draw_number = _next_draw_number(db, game_type)
    exists = (
        db.query(Draw)
        .filter(Draw.game_type == game_type, Draw.draw_number == draw_number)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail=f"El concurso {draw_number} ya existe para {game_type}")
    draw = Draw(
        game_type=game_type,
        draw_number=draw_number,
        draw_date=draw_date,
        numbers=numbers_to_str(numbers),
        additional=additional,
        source=source,
        created_by=user.id,
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    ev = evaluate_new_draw(db, draw)
    db.refresh(draw)
    return draw, ev


def _draw_result(draw, ev: dict) -> dict:
    return {
        "draw": _draw_out(draw),
        "evaluated_predictions": ev.get("evaluated", 0),
        "users_affected": ev.get("users_affected", 0),
        "new_hits": ev.get("new_hits", []),
        "retrained": ev.get("retrained"),
    }


@router.post("", response_model=DrawCreateResult)
def create_draw(payload: DrawCreate, db: Session = Depends(get_db), user: User = Depends(get_current_admin)):
    if payload.game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    draw, ev = _create_draw(
        db, user, payload.game_type, payload.numbers,
        payload.draw_number, payload.draw_date, payload.additional, "manual",
    )
    return _draw_result(draw, ev)


@router.post("/text", response_model=DrawCreateResult)
def create_draw_text(payload: DrawTextCreate, db: Session = Depends(get_db), user: User = Depends(get_current_admin)):
    if payload.game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    try:
        numbers = parse_number_text(payload.text)
    except ValueError:
        raise HTTPException(status_code=400, detail="No se pudieron interpretar los números")
    draw, ev = _create_draw(
        db, user, payload.game_type, numbers,
        payload.draw_number, payload.draw_date, None, "manual",
    )
    return _draw_result(draw, ev)


@router.post("/upload-csv")
async def upload_csv(
    game_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    content = await file.read()
    try:
        rows = parse_csv(content, game_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing_numbers = {
        d.draw_number for d in db.query(Draw.draw_number).filter(Draw.game_type == game_type).all()
    }
    imported = 0
    for r in rows:
        if r["draw_number"] in existing_numbers:
            continue
        db.add(Draw(
            game_type=game_type,
            draw_number=r["draw_number"],
            draw_date=r["draw_date"],
            numbers=numbers_to_str(r["numbers"]),
            additional=r["additional"],
            source="csv",
            created_by=user.id,
        ))
        existing_numbers.add(r["draw_number"])
        imported += 1
    db.add(CsvUpload(user_id=user.id, filename=file.filename, game_type=game_type, rows_imported=imported))
    db.commit()
    return {"imported": imported, "total_rows": len(rows), "game_type": game_type}


@router.get("/stats")
def draw_stats(game_type: str, window: int = 50, db: Session = Depends(get_db)):
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    cfg = get_game(game_type)
    rows = load_draw_rows(db, game_type)
    if not rows:
        return {"game_type": game_type, "total_draws": 0, "message": "Sin datos cargados"}
    sequences = [r["numbers"] for r in rows]
    stats = GameStats(max_number=cfg.max_number, draws=sequences, pick=cfg.pick)

    sums, ranges, odds, primes_list, consec_list = [], [], [], [], []
    repeats_list = []
    prev = None
    for s in sequences:
        sd = sorted(s)
        sums.append(sum(sd))
        ranges.append(sd[-1] - sd[0])
        odds.append(sum(1 for x in sd if x % 2))
        primes_list.append(sum(1 for x in sd if is_prime(x)))
        consec_list.append(sum(1 for i in range(len(sd) - 1) if sd[i + 1] - sd[i] == 1))
        if prev is not None:
            repeats_list.append(len(set(sd) & set(prev)))
        prev = sd

    def avg(x):
        return round(sum(x) / len(x), 2) if x else 0

    freq_sorted = sorted(stats.frequency.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "game_type": game_type,
        "label": cfg.label,
        "max_number": cfg.max_number,
        "total_draws": len(sequences),
        "frequency": stats.frequency,
        "most_frequent": [{"number": n, "count": c} for n, c in freq_sorted[:10]],
        "least_frequent": [{"number": n, "count": c} for n, c in freq_sorted[-10:]],
        "hot": stats.hot_numbers(window, 10),
        "cold": stats.cold_numbers(window, 10),
        "overdue": [{"number": n, "gap": stats.gaps[n]} for n in stats.overdue_numbers(10)],
        "gaps": stats.gaps,
        "averages": {
            "sum": avg(sums),
            "range": avg(ranges),
            "odd": avg(odds),
            "even": round(cfg.pick - avg(odds), 2),
            "primes": avg(primes_list),
            "consecutive": avg(consec_list),
            "repeats_vs_previous": avg(repeats_list),
        },
        "sum_min": min(sums), "sum_max": max(sums),
    }


def _parse_date(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(s)[:10], fmt).date()
        except ValueError:
            continue
    return None


@router.get("/number-tracker")
def number_tracker(game_type: str, window: int = 50, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Per-number hot/cold ranking + appearance timer (gap in draws, last date,
    days since last appearance)."""
    if game_type not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="Tipo de sorteo inválido")
    cfg = get_game(game_type)
    rows = load_draw_rows(db, game_type)  # oldest -> newest
    if not rows:
        return {"game_type": game_type, "total_draws": 0, "numbers": []}

    total = len(rows)
    last_idx = {n: None for n in range(1, cfg.max_number + 1)}
    last_date = {n: None for n in range(1, cfg.max_number + 1)}
    freq = {n: 0 for n in range(1, cfg.max_number + 1)}
    recent = {n: 0 for n in range(1, cfg.max_number + 1)}
    recent_start = max(0, total - window)
    for idx, r in enumerate(rows):
        d = _parse_date(r["draw_date"])
        for n in r["numbers"]:
            if 1 <= n <= cfg.max_number:
                freq[n] += 1
                last_idx[n] = idx
                if d:
                    last_date[n] = d
                if idx >= recent_start:
                    recent[n] += 1

    today = date.today()
    max_freq = max(freq.values()) or 1
    numbers = []
    for n in range(1, cfg.max_number + 1):
        gap = (total - 1 - last_idx[n]) if last_idx[n] is not None else total
        ld = last_date[n]
        days = max(0, (today - ld).days) if ld else None
        numbers.append({
            "number": n,
            "frequency": freq[n],
            "recent": recent[n],
            "gap": gap,                       # draws since last appearance
            "last_date": ld.isoformat() if ld else None,
            "days_since": days,               # "cronómetro": días desde su última aparición
            "heat": round(recent[n] / max(1, window), 3),
            "temp": "hot" if recent[n] >= (window * cfg.pick / cfg.max_number) else "cold",
        })

    hot = sorted(numbers, key=lambda x: (x["recent"], x["frequency"]), reverse=True)[:12]
    cold = sorted(numbers, key=lambda x: (x["recent"], -x["gap"]))[:12]
    overdue = sorted(numbers, key=lambda x: x["gap"], reverse=True)[:12]
    return {
        "game_type": game_type,
        "label": cfg.label,
        "max_number": cfg.max_number,
        "total_draws": total,
        "window": window,
        "hot": hot,
        "cold": cold,
        "overdue": overdue,
        "numbers": numbers,
    }
