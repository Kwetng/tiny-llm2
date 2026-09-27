"""Tests for the Phantom Flow re-implementation. No data download needed.

    pytest -q btc-expert-panel/tests
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))
import phantom_flow as pf  # noqa: E402


def series(values, start="2024-01-01"):
    return pd.Series(np.asarray(values, float), index=pd.date_range(start, periods=len(values), freq="D"))


def random_walk(n=600, seed=0):
    rng = np.random.default_rng(seed)
    return series(20000 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, n))))


def test_no_look_ahead():
    """The value on day t must be the same whether or not later days exist."""
    c = random_walk()
    full = pf.compute(c)
    for cut in (120, 250, 399, 599):
        part = pf.compute(c.iloc[:cut + 1]).iloc[-1]
        row = full.iloc[cut]
        for k in ("shift", "stop", "structure", "osc", "score", "call"):
            assert np.isclose(part[k], row[k], equal_nan=True), (cut, k)
        assert part["event"] == row["event"]


def test_shift_follows_a_clear_trend():
    up = series(np.linspace(100, 200, 120))
    down = series(np.linspace(200, 100, 120))
    assert pf.compute(up)["shift"].iloc[-1] == 1
    assert pf.compute(down)["shift"].iloc[-1] == -1


def test_stop_ratchets_in_an_uptrend():
    c = series(100 * np.exp(np.cumsum(np.full(150, 0.01) + np.random.default_rng(1).normal(0, 0.004, 150))))
    out = pf.compute(c)
    up = out[out["shift"] == 1]["stop"].dropna()
    same_leg = up.index[1:][np.diff(up.index.values).astype("timedelta64[D]").astype(int) == 1]
    assert (up.loc[same_leg].values >= up.shift(1).loc[same_leg].values - 1e-9).all()


def test_structure_events_and_change_of_character():
    # rise, pull back, break higher (BOS up), then collapse below the last swing low (CHoCH down)
    path = list(np.linspace(100, 130, 30)) + list(np.linspace(130, 115, 15)) + list(np.linspace(115, 150, 30)) + list(np.linspace(150, 90, 40))
    out = pf.compute(series(path))
    ev = [e for e in out["event"] if e]
    assert "BOS+" in ev or "CHoCH+" in ev
    assert ev[-1] in ("CHoCH-", "BOS-")
    assert out["structure"].iloc[-1] == -1


def test_call_needs_shift_and_oscillator_to_agree():
    out = pf.compute(random_walk(seed=3))
    osc_sign = np.sign(out["osc"]).fillna(0)
    acting = out["call"] != 0
    assert (out.loc[acting, "call"] == out.loc[acting, "shift"]).all()
    assert (out.loc[acting, "call"] == osc_sign[acting]).all()
    assert (out.loc[acting, "structure"] != -out.loc[acting, "call"]).all()


def test_score_scale():
    assert pf.p_up(3) == 0.875 and pf.p_up(-3) == 0.125 and pf.p_up(0) == 0.5
