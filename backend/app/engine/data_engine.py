"""Data engine: load, clean and validate draw data from CSV or the database.

Uses only the Python standard library so it runs in lightweight/serverless
environments. (pandas/numpy/scikit-learn are optional and only power the
advanced ML model when installed — see ``models_ml``.)
"""
from __future__ import annotations

import csv
import io

from .game_config import get_game, GameConfig
from .features import GameStats


def _coerce_int(v) -> int | None:
    try:
        if v is None:
            return None
        s = str(v).strip()
        if s == "" or s.lower() == "nan":
            return None
        return int(float(s))
    except (ValueError, TypeError):
        return None


def parse_csv(content: bytes | str, game_type: str) -> list[dict]:
    """Parse a CSV (matching the shipped schema) into clean draw rows.

    Returns a list of dicts: {draw_number, draw_date, numbers[6], additional}.
    Rows that fail validation are skipped.
    """
    cfg = get_game(game_type)
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None:
        raise ValueError("CSV vacío o ilegible")

    # normalise headers to upper-case for lookup
    header_map = {str(h).strip().upper(): h for h in reader.fieldnames}
    main_cols = list(cfg.main_columns)
    missing = [c for c in main_cols if c not in header_map]
    if missing:
        raise ValueError(
            f"CSV inválido para {cfg.label}: faltan columnas {missing}. "
            f"Se requieren {main_cols}."
        )

    def col(row, name):
        key = header_map.get(name)
        return row.get(key) if key else None

    positional = cfg.kind == "positional"
    rows = []
    for r in reader:
        nums = [_coerce_int(col(r, c)) for c in main_cols]
        if any(n is None for n in nums):
            continue
        if len(nums) != cfg.pick:
            continue
        if any(n < cfg.min_number or n > cfg.max_number for n in nums):
            continue
        if not positional and len(set(nums)) != cfg.pick:
            # combination games require unique numbers
            continue
        draw_number = _coerce_int(col(r, "CONCURSO"))
        date_val = col(r, "FECHA")
        draw_date = str(date_val).strip() if date_val not in (None, "") else None
        additional = None
        if cfg.additional_column:
            additional = _coerce_int(col(r, cfg.additional_column))
        rows.append({
            "draw_number": draw_number,
            "draw_date": draw_date,
            # positional: preserve order + repeats; combination: sort
            "numbers": list(nums) if positional else sorted(nums),
            "additional": additional,
        })
    return rows


def numbers_to_str(numbers: list[int], ordered: bool = False) -> str:
    """Serialize numbers for storage.

    Combination games sort (order-independent). Positional games pass
    ``ordered=True`` to preserve the exact sequence (Tris position matters).
    """
    seq = list(numbers) if ordered else sorted(numbers)
    return ",".join(str(n) for n in seq)


def str_to_numbers(s: str) -> list[int]:
    return [int(x) for x in s.split(",") if x.strip()]


def parse_number_text(text: str) -> list[int]:
    """Parse '12 18 23 34 45 51' or '12,18,23,34,45,51'."""
    cleaned = text.replace(",", " ").replace(";", " ").replace("-", " ")
    parts = [p for p in cleaned.split() if p.strip()]
    return [int(p) for p in parts]


def build_stats_from_draws(draw_rows: list[dict], cfg: GameConfig) -> GameStats:
    """draw_rows ordered however; we sort oldest->newest by draw_number."""
    ordered = sorted(draw_rows, key=lambda d: d["draw_number"] or 0)
    sequences = [d["numbers"] for d in ordered]
    return GameStats(max_number=cfg.max_number, draws=sequences, pick=cfg.pick)
