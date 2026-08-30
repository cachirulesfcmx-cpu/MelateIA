"""Quantum challenger adapter (PennyLane).

Reports availability honestly and never fabricates metrics when the framework
is missing. When PennyLane IS installed, it trains a small variational circuit
over a compressed representation of the recent draws.
"""
from __future__ import annotations


class QNNChallenger:
    name = "qnn"

    def available(self) -> bool:
        try:
            import pennylane  # noqa: F401
            return True
        except Exception:
            return False

    def framework(self) -> str | None:
        try:
            import pennylane
            return pennylane.__version__
        except Exception:
            return None

    def run(self, draws: list[list[int]], max_number: int, pick: int = 6,
            n_qubits: int = 6, steps: int = 40, seed: int = 42) -> dict:
        if not self.available():
            return {
                "status": "unavailable",
                "model": self.name,
                "framework": None,
                "role": "challenger",
                "promotion": "blocked_until_protocol_pass",
                "reason": "PennyLane no está instalado en este entorno.",
            }
        import numpy as np
        import pennylane as qml
        from pennylane import numpy as pnp

        rng = np.random.default_rng(seed)
        # compress each draw into n_qubits features: the share of numbers falling
        # in each equal-width zone of the range
        zones = np.zeros((len(draws), n_qubits), dtype=float)
        width = max_number / n_qubits
        for i, d in enumerate(draws):
            for n in d:
                if 1 <= n <= max_number:
                    zones[i, min(int((n - 1) // width), n_qubits - 1)] += 1
        zones /= max(pick, 1)

        X = zones[:-1]
        y = zones[1:, 0]                    # predict the first zone's share
        split = int(len(X) * 0.8)
        Xtr, Xv, ytr, yv = X[:split], X[split:], y[:split], y[split:]

        dev = qml.device("default.qubit", wires=n_qubits)

        @qml.qnode(dev)
        def circuit(weights, x):
            qml.AngleEmbedding(x, wires=range(n_qubits))
            qml.BasicEntanglerLayers(weights, wires=range(n_qubits))
            return qml.expval(qml.PauliZ(0))

        shape = qml.BasicEntanglerLayers.shape(n_layers=2, n_wires=n_qubits)
        weights = pnp.array(rng.normal(0, 0.1, shape), requires_grad=True)
        opt = qml.AdamOptimizer(0.05)

        def cost(w):
            preds = pnp.stack([circuit(w, x) for x in Xtr[:120]])
            return pnp.mean((preds - pnp.array(ytr[:120])) ** 2)

        for _ in range(steps):
            weights = opt.step(cost, weights)

        preds = np.array([float(circuit(weights, x)) for x in Xv])
        mse = float(np.mean((preds - yv) ** 2))
        baseline_mse = float(np.mean((np.full_like(yv, ytr.mean()) - yv) ** 2))
        return {
            "status": "trained",
            "model": self.name,
            "framework": self.framework(),
            "n_qubits": n_qubits,
            "steps": steps,
            "validation_mse": round(mse, 6),
            "constant_baseline_mse": round(baseline_mse, 6),
            "beats_constant_baseline": bool(mse < baseline_mse),
            "role": "challenger",
            "promotion": "blocked_until_protocol_pass",
            "note": ("Batir a una predicción constante en una tarea auxiliar no es "
                     "evidencia predictiva sobre el sorteo. Debe pasar el protocolo."),
        }
