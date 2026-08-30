"""Quantum challenger (PennyLane) — the v6 circuit, actually trained.

The reference package builds a nice circuit (RY embedding → Rot layers → CNOT
chain) but then scores with the randomly initialised weights and never fits
them. A random circuit is a fixed random feature map: whatever it outputs is
not a prediction, so reporting its numbers as a challenger's performance would
be misleading. Here the same circuit is trained by gradient descent, and it is
still judged by the only metric that means anything — top-k hits against the
exact random baseline — while promotion stays blocked behind the full protocol.

Availability is reported honestly: with PennyLane absent, no metrics are
invented.
"""
from __future__ import annotations

import numpy as np

from .evaluation import summarize, theoretical_random_mean_hits


class QNNChallenger:
    name = "qnn"

    def __init__(self, n_qubits: int = 8, layers: int = 2, seed: int = 42):
        self.n_qubits = n_qubits
        self.layers = layers
        self.seed = seed

    # ---------------- availability ----------------
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

    # ---------------- circuit ----------------
    def build(self):
        """The v6 circuit: angle embedding, Rot layers, CNOT entangling chain."""
        import pennylane as qml

        dev = qml.device("default.qubit", wires=self.n_qubits)

        @qml.qnode(dev)
        def circuit(x, w):
            for i in range(self.n_qubits):
                qml.RY(np.pi * qml.math.tanh(x[i]), wires=i)
            for layer in range(self.layers):
                for i in range(self.n_qubits):
                    qml.Rot(w[layer, i, 0], w[layer, i, 1], w[layer, i, 2], wires=i)
                for i in range(self.n_qubits - 1):
                    qml.CNOT(wires=[i, i + 1])
            return [qml.expval(qml.PauliZ(i)) for i in range(self.n_qubits)]

        return circuit

    def init_weights(self):
        rng = np.random.default_rng(self.seed)
        return rng.normal(0, 0.05, size=(self.layers, self.n_qubits, 3))

    # ---------------- features ----------------
    def _zone_features(self, draws, max_number: int, min_number: int, pick: int):
        """Compress each draw into `n_qubits` zone shares — the circuit's input."""
        span = max_number - min_number + 1
        width = span / self.n_qubits
        x = np.zeros((len(draws), self.n_qubits), dtype=float)
        for i, d in enumerate(draws):
            for n in d:
                if min_number <= n <= max_number:
                    z = min(int((n - min_number) // width), self.n_qubits - 1)
                    x[i, z] += 1.0
        return x / max(pick, 1)

    # ---------------- training ----------------
    def run(self, draws, max_number: int, pick: int = 6, min_number: int = 1,
            steps: int = 25, train_rows: int = 60) -> dict:
        if not self.available():
            return {
                "status": "unavailable", "model": self.name, "framework": None,
                "role": "challenger", "promotion": "blocked_until_protocol_pass",
                "reason": "PennyLane no está instalado en este entorno.",
            }
        import pennylane as qml
        from pennylane import numpy as pnp

        span = max_number - min_number + 1
        zones = self._zone_features(draws, max_number, min_number, pick)
        # predict the NEXT draw's zone profile from the current one
        X, Y = zones[:-1], zones[1:]
        split = int(len(X) * 0.8)           # chronological, never shuffled
        Xtr, Xv, Ytr, Yv = X[:split], X[split:], Y[:split], Y[split:]
        if len(Xtr) < 50 or len(Xv) < 10:
            return {"status": "insufficient_data", "model": self.name,
                    "samples": int(len(X)),
                    "role": "challenger", "promotion": "blocked_until_protocol_pass"}

        circuit = self.build()
        weights = pnp.array(self.init_weights(), requires_grad=True)
        opt = qml.AdamOptimizer(0.05)
        rows = min(train_rows, len(Xtr))
        Xt = pnp.array(Xtr[:rows], requires_grad=False)
        Yt = pnp.array(Ytr[:rows], requires_grad=False)

        def cost(w):
            preds = pnp.stack([pnp.stack(circuit(Xt[i], w)) for i in range(rows)])
            return pnp.mean((preds - Yt) ** 2)

        history = []
        for step in range(steps):
            weights, loss = opt.step_and_cost(cost, weights)
            if step % 5 == 0:
                history.append({"step": step, "loss": float(loss)})

        # expand the 8 zone outputs back to per-number scores so the challenger
        # is judged with exactly the same metric as every other arm
        width = span / self.n_qubits
        val_scores = []
        for i in range(len(Xv)):
            z = np.asarray(circuit(pnp.array(Xv[i], requires_grad=False), weights), dtype=float)
            per_number = np.array([z[min(int(j // width), self.n_qubits - 1)]
                                   for j in range(span)], dtype=float)
            val_scores.append(per_number)
        actual_next = draws[split + 1:len(X) + 1]
        metrics = summarize(np.array(val_scores), actual_next, max_number, pick, min_number)

        return {
            "status": "trained",
            "model": self.name,
            "framework": self.framework(),
            "n_qubits": self.n_qubits,
            "layers": self.layers,
            "steps": steps,
            "train_rows": rows,
            "validation_samples": int(len(Xv)),
            "loss_history": history,
            "final_loss": history[-1]["loss"] if history else None,
            **metrics,
            "random_mean_hits": round(theoretical_random_mean_hits(max_number, pick), 4),
            "looks_like_base_rate": bool(metrics["flat_predictions"] or metrics["close_to_base_rate"]),
            "role": "challenger",
            "promotion": "blocked_until_protocol_pass",
            "note": ("Circuito entrenado de verdad (el paquete de referencia puntúa con "
                     "pesos aleatorios sin ajustar). Aun entrenado, debe pasar el protocolo "
                     "completo: ninguna métrica de entrenamiento promueve un modelo."),
        }
