"""Per-game configuration.

Ranges are derived from the historical CSV data shipped with the project:
  - Melate / Revancha use balls 1..56
  - Melate Retro uses balls 1..39
  - Revanchita in the supplied dataset uses balls 1..56

Every game draws 6 unique main numbers. The "additional" column (R7 / F7),
when present in the source CSV, is stored separately and not used for the
6-number prediction game.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GameConfig:
    key: str
    label: str
    max_number: int
    pick: int
    # CSV columns that hold the 6 main numbers, in order
    main_columns: tuple
    additional_column: str | None
    # Default csv filename shipped under backend/data
    seed_file: str


GAMES: dict[str, GameConfig] = {
    "melate": GameConfig(
        key="melate",
        label="Melate",
        max_number=56,
        pick=6,
        main_columns=("R1", "R2", "R3", "R4", "R5", "R6"),
        additional_column="R7",
        seed_file="melate.csv",
    ),
    "revancha": GameConfig(
        key="revancha",
        label="Revancha",
        max_number=56,
        pick=6,
        main_columns=("R1", "R2", "R3", "R4", "R5", "R6"),
        additional_column=None,
        seed_file="revancha.csv",
    ),
    "melate_retro": GameConfig(
        key="melate_retro",
        label="Melate Retro",
        max_number=39,
        pick=6,
        main_columns=("F1", "F2", "F3", "F4", "F5", "F6"),
        additional_column="F7",
        seed_file="melate_retro.csv",
    ),
    "revanchita": GameConfig(
        key="revanchita",
        label="Revanchita",
        max_number=56,
        pick=6,
        main_columns=("F1", "F2", "F3", "F4", "F5", "F6"),
        additional_column=None,
        seed_file="revanchita.csv",
    ),
}

GAME_KEYS = list(GAMES.keys())


def get_game(key: str) -> GameConfig:
    if key not in GAMES:
        raise ValueError(f"Unknown game type: {key}")
    return GAMES[key]


def validate_combination(game_key: str, numbers: list[int]) -> list[int]:
    """Validate a combination against the game rules. Returns sorted numbers."""
    cfg = get_game(game_key)
    if len(numbers) != cfg.pick:
        raise ValueError(f"{cfg.label} requiere exactamente {cfg.pick} números")
    if len(set(numbers)) != len(numbers):
        raise ValueError("No se permiten números repetidos")
    for n in numbers:
        if n < 1 or n > cfg.max_number:
            raise ValueError(
                f"Número {n} fuera de rango (1-{cfg.max_number}) para {cfg.label}"
            )
    return sorted(numbers)
