"""Tests for the two newest seats: the quantum NN and the regime HMM.

    pytest -q btc-expert-panel/tests

The tests that matter most:
  - the quantum simulator reproduces a textbook Bell state exactly (this is what "real quantum
    mechanics, simulated" is supposed to mean - if the linear algebra were wrong, this is where
    it would show)
  - the parameter-shift rule (what real hardware would have to use) agrees with autograd
  - the HMM's filtered probabilities are IDENTICAL whether computed on the full series or a
    truncated one - the single test that rules out the classic look-ahead bug in this file
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))
import quantum_nn as qn  # noqa: E402
import hmm_regime as hr  # noqa: E402


# ------------------------------------------------------------------ quantum simulator
def test_zero_state_is_normalised_and_all_z_plus_one():
    sim = qn.StateVector(4)
    s = sim.zeros(2)
    assert torch.allclose((s ** 2).sum(1), torch.ones(2))
    assert torch.allclose(sim.expect_z(s), torch.ones(2, 4))


def test_ry_pi_flips_a_qubit_to_all_z_minus_one():
    sim = qn.StateVector(3)
    s = sim.zeros(1)
    for q in range(3):
        s = sim.ry(s, q, torch.tensor(np.pi))
    assert torch.allclose(sim.expect_z(s), -torch.ones(1, 3), atol=1e-5)
    assert torch.allclose((s ** 2).sum(1), torch.ones(1))          # still a valid probability distribution


def test_single_cnot_makes_a_bell_state():
    """RY(pi/2) on qubit 0 then CNOT(0->1): the textbook Bell state (|00>+|11>)/sqrt(2)."""
    sim = qn.StateVector(2)
    s = sim.zeros(1)
    s = sim.ry(s, 0, torch.tensor(np.pi / 2))
    s = s[:, sim.cnot_perm[0]]                                    # CNOT(0->1) alone, not the full ring
    expected = torch.tensor([[1 / np.sqrt(2), 0.0, 0.0, 1 / np.sqrt(2)]], dtype=s.dtype)
    assert torch.allclose(s, expected, atol=1e-5)
    z = sim.expect_z(s)
    assert torch.allclose(z, torch.zeros(1, 2), atol=1e-5)         # a Bell state is maximally uncertain per-qubit


def test_batched_and_per_sample_angles_agree_with_looped_single_samples():
    sim = qn.StateVector(3)
    thetas = torch.tensor([0.3, 1.1, 2.7])
    batched = sim.ry(sim.zeros(3), 1, thetas)
    for i in range(3):
        single = sim.ry(sim.zeros(1), 1, thetas[i])
        assert torch.allclose(batched[i], single[0], atol=1e-6)


def test_parameter_shift_matches_autograd():
    """The gradient rule real hardware must use should agree with differentiating the simulator."""
    net = qn.QuantumNet(seed=3)
    x = torch.rand(6, qn.N_QUBITS) * np.pi
    for layer, qubit in [(0, 0), (1, 3), (2, 5)]:
        ps = net.parameter_shift_gradient(x, layer, qubit, readout_index=0).sum()
        z = net.circuit(x)[:, 0].sum()
        auto = torch.autograd.grad(z, net.weights, retain_graph=False)[0][layer, qubit]
        assert abs(float(ps) - float(auto)) < 1e-4


def test_encoding_stays_in_0_pi_and_is_monotone_in_rank():
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, (200, len(qn.FEATURES)))
    e = qn.QuantumExpert().fit(X, (X[:, 0] > 0).astype(int))
    enc = e._encode(X).numpy()
    assert (enc >= 0).all() and (enc <= np.pi + 1e-6).all()
    order = np.argsort(X[:, 0])
    assert np.all(np.diff(enc[order, 0]) >= -1e-9)                 # rank-encoding cannot un-sort


def test_quantum_expert_reproducible_with_same_seed():
    rng = np.random.default_rng(1)
    X = rng.normal(0, 1, (150, len(qn.FEATURES)))
    y = (X[:, 0] > 0).astype(int)
    a = qn.QuantumExpert(seed=9, steps=50).fit(X, y).p_up(X[0])
    b = qn.QuantumExpert(seed=9, steps=50).fit(X, y).p_up(X[0])
    assert a == pytest.approx(b)


def test_quantum_expert_has_25_parameters():
    e = qn.QuantumExpert(steps=1).fit(np.zeros((10, len(qn.FEATURES))), np.array([0, 1] * 5))
    assert e.stats["params"] == 18 + 7                             # 3 layers x 6 qubits + (6 weights + 1 bias)


# ------------------------------------------------------------------ HMM regime
def two_regime_series(n=500, seed=0):
    rng = np.random.default_rng(seed)
    state = np.zeros(n, int)
    for t in range(1, n):
        state[t] = state[t - 1] if rng.random() < 0.95 else 1 - state[t - 1]
    ret = np.where(state == 0, rng.normal(-0.03, 0.09, n), rng.normal(0.02, 0.03, n))
    vol = pd.Series(ret).rolling(4, min_periods=1).std().fillna(0).values
    return np.column_stack([ret, vol]), state


def test_hmm_recovers_planted_regimes():
    obs, state = two_regime_series()
    m = hr.RegimeHMM(n_states=2, seed=0).fit(obs[:350])
    recovered = m.filter(obs).argmax(1)
    agree = max((recovered == state).mean(), (recovered == 1 - state).mean())
    assert agree > 0.8


def test_worse_state_is_always_index_zero():
    obs, _ = two_regime_series(seed=2)
    m = hr.RegimeHMM(n_states=2, seed=0).fit(obs)
    assert m.mu[0, 0] <= m.mu[1, 0]


def test_filtering_is_causal_truncation_gives_the_same_last_row():
    """THE test this file exists for: filtering less data must never change past answers."""
    obs, _ = two_regime_series(seed=3)
    m = hr.RegimeHMM(n_states=2, seed=0).fit(obs[:350])
    full = m.filter(obs)
    part = m.filter(obs[:400])
    assert np.allclose(full[399], part[399], atol=1e-10)
    assert np.allclose(full[200], m.filter(obs[:201])[200], atol=1e-10)


def test_p_up_next_is_a_valid_probability_and_varies():
    obs, _ = two_regime_series(seed=4)
    m = hr.RegimeHMM(n_states=2, seed=0).fit(obs[:350])
    filtered = m.filter(obs)
    ps = np.array([m.p_up_next(r) for r in filtered])
    assert ((ps >= 0) & (ps <= 1)).all()
    assert ps.std() > 0


def test_describe_matches_the_argmax_state():
    obs, _ = two_regime_series(seed=5)
    m = hr.RegimeHMM(n_states=2, seed=0).fit(obs)
    filtered = m.filter(obs)
    d = m.describe(filtered[-1])
    assert d["state"] == int(np.argmax(filtered[-1]))
    assert d["label"] in m.labels()


def test_three_states_get_three_distinct_volatility_words():
    """A median split can leave two of three states calling themselves 'volatile': ranking must not."""
    obs, _ = two_regime_series(seed=7)
    # three states with clearly different volatilities: low, medium, high
    obs3 = np.vstack([obs[:150], obs[150:300] * 1.6, obs[300:450] * 0.4])
    m = hr.RegimeHMM(n_states=3, seed=0).fit(obs3)
    words = [lab.split(" and ")[0] for lab in m.labels()]
    assert "calm" in words and "volatile" in words
    vols = np.sqrt(m.var[:, 0])
    assert words[int(np.argmin(vols))] == "calm"
    assert words[int(np.argmax(vols))] == "volatile"


def test_transition_rows_sum_to_one():
    obs, _ = two_regime_series(seed=6)
    m = hr.RegimeHMM(n_states=3, seed=0).fit(obs)
    assert np.allclose(m.A.sum(axis=1), 1.0, atol=1e-8)
    assert np.allclose(m.pi.sum(), 1.0, atol=1e-8)


def test_observations_builder_uses_ret_1w_and_vol_4w():
    wk = pd.DataFrame({"ret_1w": [0.01, -0.02, 0.03], "vol_4w": [0.1, 0.2, 0.15], "other": [9, 9, 9]})
    obs = hr.observations(wk)
    assert obs.shape == (3, 2)
    assert np.allclose(obs[:, 0], wk["ret_1w"].values)
    assert np.allclose(obs[:, 1], wk["vol_4w"].values)
