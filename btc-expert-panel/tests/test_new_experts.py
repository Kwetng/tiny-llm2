"""Tests for the two newest seats: the chart JEPA and the on-chain fundamentals.

    pytest -q btc-expert-panel/tests

The tests that matter most are the causality ones. Both seats compute rolling quantities, and a
rolling window that accidentally reaches forwards is the easiest way to invent a backtest result
that cannot be repeated live.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))
import chart_jepa as cj  # noqa: E402
import fundamentals as fu  # noqa: E402


def walk(n=400, seed=0, start=100.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2016-01-03", periods=n, freq="W-SUN")
    return pd.Series(start * np.exp(np.cumsum(rng.normal(0.002, 0.06, n))), index=idx)


# ------------------------------------------------------------------ chart JEPA
def test_chart_is_a_picture_of_the_right_shape():
    img = cj.render_chart(walk(cj.WINDOW).values)
    assert img.shape == (cj.ROWS, cj.WINDOW)
    assert img.min() >= 0.0 and img.max() == pytest.approx(1.0)
    assert (img > 0).any(axis=0).all()          # every week is drawn: no blank columns


def test_the_picture_shows_shape_not_price_level():
    """The same pattern at $300 and at $60,000 must render identically - that is the point."""
    p = walk(cj.WINDOW).values
    assert np.array_equal(cj.render_chart(p), cj.render_chart(p * 200))
    assert np.array_equal(cj.render_chart(p), cj.render_chart(p * 0.004))


def test_a_flat_chart_does_not_divide_by_zero():
    img = cj.render_chart(np.full(cj.WINDOW, 42.0))
    assert np.isfinite(img).all() and img.max() == pytest.approx(1.0)


def test_patches_tile_the_picture_exactly():
    img = cj.render_chart(walk(cj.WINDOW).values)
    patches = cj.to_patches(img)
    assert patches.shape == (cj.N_PATCH, cj.ROWS * cj.PATCH)
    assert cj.N_CONTEXT < cj.N_PATCH                      # something must be left to predict


def test_charts_never_use_future_prices():
    """The chart drawn for a date must not change when later weeks are appended."""
    p = walk(200)
    full, dates_full = cj.build_charts(p, p.index)
    cut = p.index[150]
    part, dates_part = cj.build_charts(p.loc[:cut], p.loc[:cut].index)
    assert dates_part[-1] == cut
    assert np.array_equal(part[-1], full[dates_full.index(cut)])


def test_training_does_not_collapse_and_scores_are_probabilities():
    p = walk(300, seed=3)
    charts, dates = cj.build_charts(p, p.index)
    y = (p.shift(-1) > p).astype(int).reindex(dates).values[: len(charts)]
    ok = ~pd.isna(y)
    model = cj.ChartJEPA(seed=1, steps=200).fit(charts[ok], y[ok].astype(int))
    assert model.collapse_score() > 0.1, "embeddings collapsed to a single point"
    probs = [model.p_up(c) for c in charts[:20]]
    assert all(0.0 < x < 1.0 for x in probs)
    assert np.std(probs) > 0, "the probe returns a constant, so the seat carries no information"


def test_same_seed_gives_the_same_model():
    p = walk(220, seed=5)
    charts, dates = cj.build_charts(p, p.index)
    y = (p.shift(-1) > p).astype(int).reindex(dates).values[: len(charts)]
    ok = ~pd.isna(y)
    a = cj.ChartJEPA(seed=7, steps=120).fit(charts[ok], y[ok].astype(int)).p_up(charts[0])
    b = cj.ChartJEPA(seed=7, steps=120).fit(charts[ok], y[ok].astype(int)).p_up(charts[0])
    assert a == pytest.approx(b)


# ------------------------------------------------------------------ fundamentals
def fake_chain(n=1500, seed=0):
    """A daily frame with the columns the Coin Metrics file provides."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="D")
    price = 5000 * np.exp(np.cumsum(rng.normal(0.001, 0.03, n)))
    supply = np.linspace(17e6, 19.5e6, n)
    return pd.DataFrame({"PriceUSD": price, "CapMrktCurUSD": price * supply,
                         "CapMVRVCur": np.exp(rng.normal(0.3, 0.25, n)).cumsum() / np.arange(1, n + 1) + 1,
                         "IssTotUSD": price * 900 * rng.uniform(0.9, 1.1, n),
                         "HashRate": np.exp(np.cumsum(rng.normal(0.002, 0.02, n))) * 1e8,
                         "AdrActCnt": 700_000 * np.exp(rng.normal(0, 0.1, n))}, index=idx)


def test_trailing_z_is_causal():
    """A z-score must never change once computed: later data cannot reach backwards."""
    s = pd.Series(walk(600, seed=2).values)
    full = fu.trailing_z(s)
    cut = 400
    part = fu.trailing_z(s.iloc[:cut])
    assert part.iloc[-1] == pytest.approx(full.iloc[cut - 1], nan_ok=True)


def test_trailing_z_waits_for_enough_history():
    z = fu.trailing_z(pd.Series(np.arange(300, dtype=float)))
    assert z.iloc[: fu.MIN_TRAIL - 1].isna().all()
    assert z.iloc[fu.MIN_TRAIL:].notna().all()


def test_metrics_are_scale_free():
    """Doubling every dollar amount must not move MVRV or the Puell multiple."""
    day = fake_chain()
    a = fu.daily_metrics(day)
    scaled = day.copy()
    for c in ("PriceUSD", "CapMrktCurUSD", "IssTotUSD"):
        scaled[c] *= 1000
    b = fu.daily_metrics(scaled)
    pd.testing.assert_series_equal(a["mvrv"], b["mvrv"])
    pd.testing.assert_series_equal(a["puell"], b["puell"], atol=1e-12)


def test_bullish_and_bearish_signs():
    """Positive must always mean 'cheap or improving', whichever way the raw metric points."""
    assert fu.DIRECTION["mvrv"] == -1 and fu.DIRECTION["puell"] == -1      # high = expensive
    assert fu.DIRECTION["hash_ribbon"] == +1                               # high = healthy
    assert fu.DIRECTION["metcalfe"] == -1                                  # high = ahead of adoption


def test_model_fits_and_only_votes_at_extremes():
    day = fake_chain(2200, seed=4)
    weekly = pd.date_range(day.index[30], day.index[-1], freq="W-SUN")
    f = fu.daily_metrics(day).reindex(weekly)
    price = day["PriceUSD"].reindex(weekly)
    y = (price.shift(-1) > price).astype(int).values
    train = (weekly < weekly[int(len(weekly) * 0.6)]).astype(bool)
    m = fu.FundamentalModel().fit(f, train, y)
    assert 0.0 < m.p_up(f) < 1.0
    parts = m.parts(f)
    assert list(parts.columns) == fu.METRICS
    assert set(m.explain(f.tail(1))) == set(fu.METRICS)


def test_vote_only_beyond_the_threshold():
    t = fu.VOTE_Z
    assert fu.vote(t) == 1 and fu.vote(-t) == -1
    assert fu.vote(t * 0.9) == 0 and fu.vote(0.0) == 0
    assert fu.vote(None) == 0 and fu.vote(float("nan")) == 0    # no reading is never a bet


def test_a_missing_metric_does_not_sink_the_composite():
    """Three readings and one gap must still produce a score, not a NaN."""
    m = fu.FundamentalModel()
    m._parts = pd.DataFrame({"mvrv": [1.0], "puell": [np.nan], "hash_ribbon": [-1.0], "metcalfe": [0.0]})
    assert m.composite(m._parts).iloc[0] == pytest.approx(0.0)
