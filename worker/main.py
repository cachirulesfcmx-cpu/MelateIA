"""MelateAI Training Worker — CLI.

Trains the heavy sequence challengers OUTSIDE the HTTP service, which is the
whole point: PyTorch cannot be fitted inside a web request, and the web dyno
should not carry a multi-hundred-megabyte dependency for it.

    python -m worker.main --game melate --model lstm
    python -m worker.main --game melate --model transformer
    python -m worker.main --game chispazo --model qnn
    python -m worker.main --game melate --model lstm --submit    # send to the app

`--submit` posts the result to the app as a Challenger with promotion blocked;
it never writes a Champion. Reads the same CSV history the app is seeded with.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

# game -> (max_number, pick, min_number, csv file, main columns)
GAMES = {
    "melate":       (56, 6, 1, "melate.csv", [f"R{i}" for i in range(1, 7)]),
    "revancha":     (56, 6, 1, "revancha.csv", [f"R{i}" for i in range(1, 7)]),
    "melate_retro": (39, 6, 1, "melate_retro.csv", [f"F{i}" for i in range(1, 7)]),
    "revanchita":   (56, 6, 1, "revanchita.csv", [f"F{i}" for i in range(1, 7)]),
    "chispazo":     (29, 5, 1, "chispazo.csv", [f"R{i}" for i in range(1, 6)]),
}


def _data_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent
    return [
        Path(os.environ.get("MELATE_DATA_DIR", "")) if os.environ.get("MELATE_DATA_DIR") else None,
        here.parent / "backend" / "data",
        Path("/app/data"),
        here.parent / "data",
    ]


def load_history(game: str) -> list[list[int]]:
    import csv as _csv

    max_number, pick, min_number, filename, cols = GAMES[game]
    path = next((d / filename for d in _data_dirs() if d and (d / filename).exists()), None)
    if path is None:
        raise FileNotFoundError(
            f"No encontré {filename}. Usa MELATE_DATA_DIR para indicar la carpeta de datos.")
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in _csv.DictReader(fh):
            try:
                nums = sorted(int(r[c]) for c in cols)
            except (KeyError, TypeError, ValueError):
                continue
            if len(set(nums)) != pick or not all(min_number <= n <= max_number for n in nums):
                continue
            try:
                order = int(r.get("CONCURSO") or 0)
            except ValueError:
                order = 0
            rows.append((order, nums))
    rows.sort(key=lambda x: x[0])
    return [n for _, n in rows]


def submit(result: dict, base_url: str, token: str) -> dict:
    """Publish the run to the app as a Challenger (promotion stays blocked)."""
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/research/worker-result",
        data=json.dumps(result).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def main() -> int:
    ap = argparse.ArgumentParser(description="MelateAI training worker")
    ap.add_argument("--game", choices=sorted(GAMES), required=True)
    ap.add_argument("--model", choices=["lstm", "transformer", "qnn"], required=True)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--lookback", type=int, default=32)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--qnn-steps", type=int, default=25)
    ap.add_argument("--qnn-rows", type=int, default=60)
    ap.add_argument("--ablations", action="store_true",
                    help="ejecutar el protocolo de ablaciones (7 configuraciones)")
    ap.add_argument("--stability", action="store_true",
                    help="barrido de estabilidad: 5 semillas x 5 lookbacks")
    ap.add_argument("--submit", action="store_true",
                    help="publicar el resultado en la app como Challenger")
    ap.add_argument("--api", default=os.environ.get("MELATE_API_URL", ""))
    ap.add_argument("--token", default=os.environ.get("MELATE_API_TOKEN", ""))
    args = ap.parse_args()

    max_number, pick, min_number, _, _ = GAMES[args.game]
    history = load_history(args.game)

    if args.model == "qnn":
        from .qnn import QNNChallenger
        result = QNNChallenger(seed=args.seed).run(
            history, max_number, pick, min_number=min_number,
            steps=args.qnn_steps, train_rows=args.qnn_rows)
    else:
        try:
            from .train import train_model
        except ImportError as exc:
            result = {"status": "unavailable", "model": args.model, "framework": None,
                      "role": "challenger", "promotion": "blocked_until_protocol_pass",
                      "reason": f"PyTorch no está instalado: {exc}"}
        else:
            result = train_model(history, max_number, args.model, pick=pick,
                                 epochs=args.epochs, lookback=args.lookback,
                                 min_number=min_number, seed=args.seed)

    # v6 — ablations and stability sweep, run on the same history
    if args.model != "qnn" and (args.ablations or args.stability):
        try:
            from .ablations import run_ablations, run_stability
            from .train import train_model as _tm
        except ImportError as exc:
            result["ablations_error"] = str(exc)
        else:
            if args.ablations:
                result["ablation_protocol"] = run_ablations(
                    history, max_number, args.model, _tm, pick=pick,
                    min_number=min_number, epochs=max(8, args.epochs // 2),
                    seed=args.seed)
            if args.stability:
                result["stability"] = run_stability(
                    history, max_number, args.model, _tm, pick=pick,
                    min_number=min_number, epochs=max(6, args.epochs // 3))

    result["game"] = args.game
    result["draws"] = len(history)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.submit:
        if not args.api or not args.token:
            print("\n--submit requiere --api y --token (o MELATE_API_URL / MELATE_API_TOKEN).",
                  file=sys.stderr)
            return 2
        print("\n" + json.dumps(submit(result, args.api, args.token), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
