"""Per-game configuration.

Ranges are derived from the historical CSV data shipped with the project:
  - Melate / Revancha use balls 1..56
  - Melate Retro uses balls 1..39
  - Revanchita in the supplied dataset uses balls 1..56
  - Chispazo uses balls 1..29 (pick 5, like Melate but 5 numbers)
  - Tris is POSITIONAL: 5 digits 0..9, repeats allowed, the position matters

Combination games draw `pick` unique main numbers (order irrelevant). The
"additional" column (R7 / F7), when present in the source CSV, is stored
separately and not used for the prediction game.

Positional games (Tris) draw `pick` digits where ORDER and REPETITION matter:
"1,2,3,4,5" is a different result than "5,4,3,2,1". Matching is per-position.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GameConfig:
    key: str
    label: str
    max_number: int
    pick: int
    # CSV columns that hold the main numbers, in order
    main_columns: tuple
    additional_column: str | None
    # Default csv filename shipped under backend/data
    seed_file: str
    # "combination" (unique, order-independent) or "positional" (Tris: ordered,
    # repeats allowed, per-position matching). Defaults to combination so every
    # existing game keeps its exact behaviour.
    kind: str = "combination"
    # Smallest valid number. Combination games start at 1; Tris digits at 0.
    min_number: int = 1


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
    "chispazo": GameConfig(
        key="chispazo",
        label="Chispazo",
        max_number=29,
        pick=5,
        main_columns=("R1", "R2", "R3", "R4", "R5"),
        additional_column=None,
        seed_file="chispazo.csv",
    ),
    "tris": GameConfig(
        key="tris",
        label="Tris",
        max_number=9,
        min_number=0,
        pick=5,
        main_columns=("R1", "R2", "R3", "R4", "R5"),
        additional_column=None,
        seed_file="tris.csv",
        kind="positional",
    ),
}

GAME_KEYS = list(GAMES.keys())


def get_game(key: str) -> GameConfig:
    if key not in GAMES:
        raise ValueError(f"Unknown game type: {key}")
    return GAMES[key]


def is_positional(key: str) -> bool:
    return get_game(key).kind == "positional"


def validate_combination(game_key: str, numbers: list[int]) -> list[int]:
    """Validate a play against the game rules.

    Combination games: requires exactly `pick` UNIQUE numbers in [1, max];
    returns them sorted ascending.

    Positional games (Tris): requires exactly `pick` digits in
    [min_number, max_number]; REPEATS ARE ALLOWED and the ORDER IS PRESERVED
    (position matters), so the list is returned exactly as given.
    """
    cfg = get_game(game_key)
    if len(numbers) != cfg.pick:
        raise ValueError(f"{cfg.label} requiere exactamente {cfg.pick} números")

    if cfg.kind == "positional":
        for n in numbers:
            if n < cfg.min_number or n > cfg.max_number:
                raise ValueError(
                    f"Número {n} fuera de rango ({cfg.min_number}-{cfg.max_number}) para {cfg.label}"
                )
        return list(numbers)  # keep order + repeats — position matters

    if len(set(numbers)) != len(numbers):
        raise ValueError("No se permiten números repetidos")
    for n in numbers:
        if n < cfg.min_number or n > cfg.max_number:
            raise ValueError(
                f"Número {n} fuera de rango ({cfg.min_number}-{cfg.max_number}) para {cfg.label}"
            )
    return sorted(numbers)
