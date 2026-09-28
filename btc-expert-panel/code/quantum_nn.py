"""
quantum_nn.py - the quantum seat: a variational quantum circuit that calls Bitcoin's next week.

WHAT IS AND IS NOT CLAIMED HERE
This is a real quantum circuit: real qubits in superposition, real entanglement, real measurement
expectation values. The linear algebra below is exactly what would execute on hardware. It is
SIMULATED on an ordinary CPU, because six qubits is a 64-dimensional state vector and a laptop
does that exactly and instantly.

What is NOT claimed: any quantum advantage. On six qubits a classical computer reproduces the
circuit perfectly, so nothing here is faster or more powerful than classical maths - it is a
particular, rather unusual model class, and it earns its seat by being unusual rather than by
being quantum. Published claims of quantum advantage on financial time series do not survive
honest out-of-sample testing, and this file makes no such claim.

THE CIRCUIT

  |0>  -- RY(x1) -- RY(w) --*---------------- ... -- <Z>
  |0>  -- RY(x2) -- RY(w) --X--*------------- ... -- <Z>
  |0>  -- RY(x3) -- RY(w) -----X--*---------- ... -- <Z>
   ...                              (ring of CNOTs)

  1. ANGLE ENCODING. Six market features are mapped to [0, pi] and written into six qubits as
     RY rotations. A feature of 0 leaves the qubit as |0>; a feature of pi flips it to |1>;
     anything between leaves it in superposition.
  2. ENTANGLEMENT. A ring of CNOT gates correlates the qubits, so the circuit can represent
     interactions between features that no single qubit holds on its own.
  3. DATA RE-UPLOADING. The features are written in again before each variational layer. A
     circuit that sees its input once is limited to a shallow function of it; re-uploading
     (Perez-Salinas et al., 2020) makes it a much richer one, and costs nothing.
  4. READOUT. The expectation <Z> is measured on each qubit, giving six numbers in [-1, 1],
     and a single classical linear layer turns those into P(up next week). The readout being
     classical is normal for a hybrid model and is stated rather than glossed over.

ONLY RY AND CNOT, WHICH KEEPS EVERY AMPLITUDE REAL
RY rotations and CNOTs have real matrices, so the state vector never needs complex numbers.
That is not a shortcut: it is Qiskit's `RealAmplitudes` ansatz, one of the standard
hardware-efficient circuits. It makes the simulator simpler, faster and easy to check against
textbook results (see tests/test_quantum_hmm.py, which verifies a Bell state).

WHY IT SUITS A SMALL DATASET
The whole model has 25 parameters: 18 rotation angles and a 7-parameter readout. Against roughly
680 weeks of history that is a far better ratio than any other learned seat on this panel, and it
is the honest reason to expect it to behave sensibly rather than memorise.

GRADIENTS
Training here differentiates through the simulator, which is what everyone does in simulation.
On real hardware you cannot do that, and you would use the parameter-shift rule instead:
d<Z>/dw = [<Z>(w + pi/2) - <Z>(w - pi/2)] / 2. `parameter_shift_gradient()` implements it so the
two can be compared, and a test checks they agree.
"""
import numpy as np
import torch
import torch.nn as nn

N_QUBITS = 6
N_LAYERS = 3
# the six inputs written into the six qubits, chosen to be as unalike as possible
FEATURES = ["mom_4w", "mom_12w", "vol_4w", "mvrv", "dd_52w", "vix"]


class StateVector:
    """A minimal exact simulator for RY and CNOT on a register of real amplitudes.

    The state is a (batch, 2**n) tensor. Qubit 0 is the most significant bit, so basis state
    index k has qubit q set when (k >> (n - 1 - q)) & 1.
    """

    def __init__(self, n_qubits=N_QUBITS):
        self.n = n_qubits
        self.dim = 2 ** n_qubits
        k = torch.arange(self.dim)
        # +1 where qubit q reads |0>, -1 where it reads |1>: the diagonal of the Z observable
        self.z_sign = torch.stack([torch.where((k >> (self.n - 1 - q)) & 1 == 0, 1.0, -1.0)
                                   for q in range(self.n)])
        self.cnot_perm = [self._cnot_permutation(c, (c + 1) % self.n) for c in range(self.n)]

    def _cnot_permutation(self, control, target):
        k = torch.arange(self.dim)
        ctrl_is_one = (k >> (self.n - 1 - control)) & 1 == 1
        flipped = k ^ (1 << (self.n - 1 - target))
        return torch.where(ctrl_is_one, flipped, k)

    def zeros(self, batch):
        """|000000>, the state every circuit starts in."""
        s = torch.zeros(batch, self.dim)
        s[:, 0] = 1.0
        return s

    def ry(self, state, qubit, theta):
        """RY(theta) on one qubit. theta is a scalar, or one angle per sample in the batch."""
        left, right = 2 ** qubit, 2 ** (self.n - 1 - qubit)
        s = state.reshape(-1, left, 2, right)
        half = theta / 2
        c, sn = torch.cos(half), torch.sin(half)
        if c.ndim:                                    # per-sample angles need a batch axis
            c, sn = c.reshape(-1, 1, 1), sn.reshape(-1, 1, 1)
        a, b = s[:, :, 0, :], s[:, :, 1, :]
        return torch.stack([c * a - sn * b, sn * a + c * b], dim=2).reshape(-1, self.dim)

    def cnot_ring(self, state):
        """A CNOT from every qubit to its neighbour, closing the ring: this is the entangler."""
        for c in range(self.n):
            state = state[:, self.cnot_perm[c]]
        return state

    def expect_z(self, state):
        """<Z> on every qubit: (batch, n_qubits), each in [-1, 1]."""
        probs = state ** 2
        return probs @ self.z_sign.T


class QuantumNet(nn.Module):
    """Data re-uploading variational circuit with a classical linear readout."""

    def __init__(self, n_qubits=N_QUBITS, n_layers=N_LAYERS, seed=0):
        super().__init__()
        torch.manual_seed(seed)
        self.sim = StateVector(n_qubits)
        self.n, self.layers = n_qubits, n_layers
        self.weights = nn.Parameter(torch.rand(n_layers, n_qubits) * 2 * np.pi)
        self.readout = nn.Linear(n_qubits, 1)

    def circuit(self, x):
        """x: (batch, n_qubits) angles in [0, pi]. Returns <Z> per qubit."""
        state = self.sim.zeros(x.shape[0])
        for layer in range(self.layers):
            for q in range(self.n):                        # re-upload the data every layer
                state = self.sim.ry(state, q, x[:, q])
            for q in range(self.n):                        # the trainable rotations
                state = self.sim.ry(state, q, self.weights[layer, q])
            state = self.sim.cnot_ring(state)
        return self.sim.expect_z(state)

    def forward(self, x):
        return self.readout(self.circuit(x)).squeeze(-1)

    def p_up(self, x):
        with torch.no_grad():
            return torch.sigmoid(self.forward(x)).numpy()

    @torch.no_grad()
    def parameter_shift_gradient(self, x, layer, qubit, readout_index=0):
        """d<Z_i>/dw for one weight, the way real hardware must do it.

        A quantum computer cannot be differentiated through, so the gradient is recovered by
        running the circuit twice with the parameter moved a quarter turn each way.
        """
        original = self.weights[layer, qubit].clone()
        self.weights[layer, qubit] = original + np.pi / 2
        plus = self.circuit(x)[:, readout_index]
        self.weights[layer, qubit] = original - np.pi / 2
        minus = self.circuit(x)[:, readout_index]
        self.weights[layer, qubit] = original
        return (plus - minus) / 2


class QuantumExpert:
    """Fitted on one expanding training window, then used unchanged for the following year."""

    def __init__(self, seed=0, steps=400, lr=0.06):
        self.seed, self.steps, self.lr = seed, steps, lr
        self.net = None
        self.edges = None
        self.stats = {}

    def _encode(self, X):
        """Map each feature onto [0, pi] by its rank against the training distribution.

        Ranks rather than a z-score: an angle is periodic, so an outlier pushed past pi wraps
        around and silently becomes its own opposite. Ranks cannot wrap.
        """
        out = np.empty_like(X, dtype=float)
        for j in range(X.shape[1]):
            out[:, j] = np.searchsorted(self.edges[j], X[:, j]) / len(self.edges[j]) * np.pi
        return torch.tensor(out, dtype=torch.float32)

    def fit(self, X_train, y_train):
        self.edges = [np.sort(X_train[:, j]) for j in range(X_train.shape[1])]
        x = self._encode(X_train)
        y = torch.tensor(y_train, dtype=torch.float32)
        torch.manual_seed(self.seed)
        self.net = QuantumNet(seed=self.seed)
        opt = torch.optim.Adam(self.net.parameters(), lr=self.lr)
        pos = float(y.mean())
        weight = torch.where(y > 0.5, 1 / max(pos, 1e-6), 1 / max(1 - pos, 1e-6))  # balance the classes
        loss = torch.tensor(float("nan"))
        for _ in range(self.steps):
            loss = nn.functional.binary_cross_entropy_with_logits(self.net(x), y, weight=weight)
            opt.zero_grad()
            loss.backward()
            opt.step()
        with torch.no_grad():
            z = self.net.circuit(x)
        self.stats = {"loss": float(loss.detach()), "n_weeks": int(len(y)),
                      "params": sum(p.numel() for p in self.net.parameters()),
                      "qubits": self.net.n, "layers": self.net.layers,
                      "entanglement": float(z.std(dim=0).mean())}
        return self

    def p_up(self, x_row):
        return float(self.net.p_up(self._encode(np.atleast_2d(x_row)))[0])

    def measurements(self, x_row):
        """The six <Z> readings, for the dashboard: what each qubit actually measured."""
        with torch.no_grad():
            return self.net.circuit(self._encode(np.atleast_2d(x_row)))[0].tolist()
