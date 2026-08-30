"""Ablation and stability protocol.

The reference package declares the ablations as a dataclass list and stops
there. Here each one is actually RUN: the model is retrained with that channel
switched off, so the report answers a concrete question — does the advantage
survive without recency? without frequency? with a shorter context?

An edge that only appears in one configuration, with one seed, or at one
lookback is not an edge; it is the best of many tries. That is what the
stability verdict measures.
"""
from __future__ import annotations

from dataclasses import dataclass

SEEDS = [7, 17, 42, 101, 2026]
LOOKBACKS = [8, 16, 32, 64, 96]


@dataclass(frozen=True)
class Ablation:
    name: str
    lookback: int
    use_recency: bool
    use_frequency: bool
    use_position: bool
    question: str = ""


DEFAULT_ABLATIONS = [
    Ablation("full", 32, True, True, True, "arquitectura completa"),
    Ablation("no_recency", 32, False, True, True, "¿depende de la recencia?"),
    Ablation("no_frequency", 32, True, False, True, "¿depende de la frecuencia?"),
    Ablation("no_position", 32, True, True, False, "¿depende de la posición?"),
    Ablation("binary_only", 32, False, False, False, "solo presencia binaria"),
    Ablation("short_context", 16, True, True, True, "contexto corto"),
    Ablation("long_context", 64, True, True, True, "contexto largo"),
]


def run_ablations(draws, max_number, kind, train_fn, pick=6, min_number=1,
                  epochs=20, seed=42, ablations=None) -> dict:
    """Train one model per ablation and compare their edges over random."""
    ablations = ablations or DEFAULT_ABLATIONS
    results = []
    for ab in ablations:
        r = train_fn(draws, max_number, kind, pick=pick, epochs=epochs,
                     lookback=ab.lookback, min_number=min_number, seed=seed,
                     use_recency=ab.use_recency, use_frequency=ab.use_frequency,
                     use_position=ab.use_position)
        results.append({
            "ablation": ab.name,
            "question": ab.question,
            "lookback": ab.lookback,
            "channels": {"recency": ab.use_recency, "frequency": ab.use_frequency,
                         "position": ab.use_position},
            "status": r.get("status"),
            "edge_vs_random": r.get("edge_vs_random"),
            "validation_mean_hits": r.get("validation_mean_hits"),
            "flat_predictions": r.get("flat_predictions"),
        })
    ok = [r for r in results if r.get("edge_vs_random") is not None]
    full = next((r for r in ok if r["ablation"] == "full"), None)
    reading = "Sin resultados comparables."
    if full and ok:
        better = [r for r in ok if r["ablation"] != "full"
                  and (r["edge_vs_random"] or 0) > (full["edge_vs_random"] or 0)]
        reading = (
            f"La configuración completa rinde {full['edge_vs_random']:+.4f} sobre el azar. "
            + (f"{len(better)} ablación(es) rinden MÁS que la completa, así que la ventaja "
               f"no proviene de las señales que se creían necesarias."
               if better else
               "Ninguna ablación la supera; la ventaja, si existe, usa todas las señales."))
    return {"ablations": results, "reading": reading,
            "n_run": len(results), "n_comparable": len(ok)}


def run_stability(draws, max_number, kind, train_fn, pick=6, min_number=1,
                  epochs=15, seeds=None, lookbacks=None) -> dict:
    """Multi-seed × lookback sweep, with a verdict about reproducibility."""
    seeds = seeds or SEEDS
    lookbacks = lookbacks or LOOKBACKS
    grid = []
    for s in seeds:
        for lb in lookbacks:
            r = train_fn(draws, max_number, kind, pick=pick, epochs=epochs,
                         lookback=lb, min_number=min_number, seed=s)
            grid.append({"seed": s, "lookback": lb,
                         "status": r.get("status"),
                         "edge_vs_random": r.get("edge_vs_random"),
                         "validation_mean_hits": r.get("validation_mean_hits")})
    edges = [g["edge_vs_random"] for g in grid if g.get("edge_vs_random") is not None]
    if not edges:
        return {"grid": grid, "runs": len(grid), "verdict": "sin_datos",
                "reading": "Ninguna configuración produjo métricas comparables."}
    positive = sum(1 for e in edges if e > 0)
    mean_edge = sum(edges) / len(edges)
    share = positive / len(edges)
    if share >= 0.8 and mean_edge > 0:
        verdict = "estable"
    elif share >= 0.5:
        verdict = "inestable"
    else:
        verdict = "no_reproducible"
    return {
        "grid": grid,
        "runs": len(grid),
        "seeds": seeds,
        "lookbacks": lookbacks,
        "positive_share": round(share, 4),
        "mean_edge": round(mean_edge, 4),
        "best": max(grid, key=lambda g: g.get("edge_vs_random") or -9),
        "worst": min(grid, key=lambda g: g.get("edge_vs_random") if g.get("edge_vs_random") is not None else 9),
        "verdict": verdict,
        "reading": (
            f"{positive} de {len(edges)} configuraciones quedan por encima del azar "
            f"(ventaja media {mean_edge:+.4f}). "
            + {"estable": "La ventaja se reproduce a través de semillas y lookbacks.",
               "inestable": "La ventaja aparece en algunas configuraciones y desaparece en "
                            "otras: es inestable y no debe promoverse.",
               "no_reproducible": "La mayoría de configuraciones NO superan al azar: lo que "
                                  "se vea en una sola es el mejor de muchos intentos."}[verdict]),
    }
