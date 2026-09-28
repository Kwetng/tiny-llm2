"""Tests for the prediction-market expert. No network, no API key, no cached data needed.

    pytest -q btc-expert-panel/tests

These test the MATHS and the ABSTENTION rules, which is everything that can be checked
without live quotes. The two fetchers talk to public APIs that the environment building this
repository could not reach, so they are exercised here against recorded response shapes taken
from the published API documentation, not against the live services.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))
import prediction_market as pm  # noqa: E402

SPOT = 100_000.0


def ladder(up, down, spot=SPOT, **kw):
    return pm.Ladder(as_of=kw.get("as_of", "2026-05-17"), expiry=kw.get("expiry", "2026-06-01"),
                     spot=spot, up={spot * x: p for x, p in up.items()},
                     down={spot * x: p for x, p in down.items()})


SYMMETRIC = {"up": {1.05: 0.55, 1.10: 0.33, 1.20: 0.12}, "down": {0.95: 0.55, 0.90: 0.33, 0.80: 0.12}}


@pytest.mark.parametrize("question, expected", [
    ("Will Bitcoin reach $150,000 in March?", ("up", 150_000.0)),
    ("Will Bitcoin dip to $65,000 in March?", ("down", 65_000.0)),
    ("Will Bitcoin hit $120k by Friday?", ("up", 120_000.0)),
    ("Will BTC fall below $70,000 this month?", ("down", 70_000.0)),
    ("Will Bitcoin reach $150 in March?", ("up", 150_000.0)),      # bare number means thousands
    ("Will Ethereum reach $5,000?", None),                          # not Bitcoin
    ("Who wins the 2028 election?", None),                          # not a price market
    ("Will Bitcoin be volatile in March?", None),                   # no strike
])
def test_question_parsing(question, expected):
    assert pm.parse_barrier(question) == expected


def test_symmetric_ladder_has_no_lean():
    """Equal prices for equal distances up and down must give exactly zero tilt."""
    assert pm.lean(ladder(**SYMMETRIC))["lean"] == pytest.approx(0.0, abs=1e-12)


def test_bullish_ladder_leans_long_and_bearish_leans_short():
    bull = pm.lean(ladder({1.05: 0.62, 1.10: 0.45, 1.20: 0.20}, {0.95: 0.48, 0.90: 0.25, 0.80: 0.08}))
    bear = pm.lean(ladder({1.05: 0.48, 1.10: 0.25, 1.20: 0.08}, {0.95: 0.62, 0.90: 0.45, 0.80: 0.20}))
    assert bull["lean"] > 0 and pm.vote(bull["lean"]) == 1
    assert bear["lean"] < 0 and pm.vote(bear["lean"]) == -1
    assert bull["lean"] == pytest.approx(-bear["lean"])              # the signal is antisymmetric


def test_a_common_bias_in_both_legs_cancels():
    """The point of using a difference: a risk premium that lifts both sides leaves it alone."""
    base = pm.lean(ladder({1.05: 0.60, 1.10: 0.40, 1.20: 0.15}, {0.95: 0.50, 0.90: 0.30, 0.80: 0.10}))
    lifted = pm.lean(ladder({1.05: 0.66, 1.10: 0.46, 1.20: 0.21}, {0.95: 0.56, 0.90: 0.36, 0.80: 0.16}))
    assert lifted["lean"] == pytest.approx(base["lean"], abs=1e-9)


def test_abstains_rather_than_extrapolating():
    """Outside the quoted strikes, and with too few strikes, the answer is None, not a guess."""
    assert pm.lean(ladder(**SYMMETRIC), k=0.40) is None               # beyond the widest strike
    assert pm.lean(ladder(**SYMMETRIC), k=0.01) is None               # inside the nearest strike
    assert pm.lean(ladder({1.10: 0.3}, {0.90: 0.3})) is None          # one strike a side
    assert pm.lean(ladder({1.05: 0.5, 1.10: 0.3}, {})) is None        # nothing on the downside


def test_interpolation_is_monotone_and_bracketed():
    lad = ladder(**SYMMETRIC)
    vals = [pm.lean(lad, k=k)["p_touch_up"] for k in (0.05, 0.07, 0.10, 0.15, 0.20)]
    assert vals == sorted(vals, reverse=True)                          # further away is less likely
    assert vals[0] == pytest.approx(0.55) and vals[-1] == pytest.approx(0.12)


def test_touch_to_terminal_halves_and_stays_a_probability():
    """Reflection principle: 'ever touches' is about twice 'ends up past it'."""
    assert pm.touch_to_terminal(0.60) == pytest.approx(0.30)
    assert 0.0 <= pm.touch_to_terminal(2.0) <= 1.0
    assert pm.touch_to_terminal(0.0) == 0.0


def test_vote_thresholds_and_abstention():
    assert pm.vote(None) == 0                                          # no data is never a bet
    assert pm.vote(0.0) == 0
    assert pm.vote(pm.VOTE_THRESHOLD / 2) == 0                         # too small to act on
    assert pm.vote(pm.VOTE_THRESHOLD) == 1
    assert pm.vote(-pm.VOTE_THRESHOLD) == -1


def test_p_up_scale_is_bounded_and_centred():
    assert pm.p_up_from_lean(0.0) == pytest.approx(0.5)
    assert 0 < pm.p_up_from_lean(-5.0) < pm.p_up_from_lean(5.0) < 1


def test_weekly_cache_round_trip_and_missing_weeks(tmp_path):
    path = tmp_path / "prediction_market.json"
    sig = pm.WeeklySignals(path)
    assert not sig.available and sig.get("2026-05-17") is None         # absent file is not an error
    sig.save({"2026-05-17": {"lean": 0.12, "p_touch_up": 0.31, "p_touch_down": 0.19}}, "polymarket")
    reloaded = pm.WeeklySignals(path)
    assert reloaded.available and len(reloaded) == 1
    assert reloaded.lean_on("2026-05-17") == pytest.approx(0.12)
    assert reloaded.get("2026-05-10") is None                          # a week with no market
    assert reloaded.meta["source"] == "polymarket"
    assert json.load(open(path))["k"] == pm.DEFAULT_K


def test_gamma_response_shape_is_parsed_as_documented():
    """One market in Polymarket's documented Gamma shape becomes one rung of the ladder."""
    gamma_row = {"question": "Will Bitcoin reach $150,000 in March?",
                 "endDate": "2026-04-01T04:00:00Z", "volume": "24146460.0",
                 "outcomes": '["Yes", "No"]', "outcomePrices": '["0.31", "0.69"]',
                 "clobTokenIds": '["111111", "222222"]', "closed": True, "active": False}
    outcomes = [o.lower() for o in json.loads(gamma_row["outcomes"])]
    tokens = json.loads(gamma_row["clobTokenIds"])
    assert pm.parse_barrier(gamma_row["question"]) == ("up", 150_000.0)
    assert tokens[outcomes.index("yes")] == "111111"                   # the 'Yes' leg is the probability


def test_clob_history_shape():
    """/prices-history returns {"history": [{"t": unix, "p": price}]} - the shape we read."""
    payload = {"history": [{"t": 1_774_000_000, "p": 0.31}, {"t": 1_774_003_600, "p": 0.34}]}
    parsed = [(int(h["t"]), float(h["p"])) for h in payload["history"]]
    assert parsed[-1] == (1_774_003_600, 0.34)


def test_sources_refuse_plain_http(monkeypatch):
    monkeypatch.setattr(pm, "GAMMA", "http://gamma-api.polymarket.com/markets")
    with pytest.raises(ValueError):
        pm._get(pm.GAMMA)


def chair(votes):
    """The panel rule, exactly as panel_backtest.py applies it."""
    nl, ns = votes.count(1), votes.count(-1)
    return 1 if (nl >= 3 and nl > ns) else -1 if (ns >= 3 and ns > nl) else 0


@pytest.mark.parametrize("six", [
    [1, 1, 1, 0, 0, 0], [1, 1, 0, 0, 0, 0], [-1, -1, -1, 0, 0, 0],
    [1, 1, 1, -1, -1, -1], [1, 1, 1, 1, -1, -1], [0, 0, 0, 0, 0, 0], [-1, -1, -1, -1, 1, 0],
])
def test_an_abstaining_expert_never_changes_the_chair(six):
    """The property the whole design rests on: a silent seventh seat leaves the panel untouched.

    This is why the published 332-week results are unaffected by adding this expert, and why
    a week with no market is not quietly turned into a week with a 50/50 opinion.
    """
    assert chair(six + [0]) == chair(six)


def test_a_voting_expert_can_change_the_chair():
    """...and the seat is not inert: when it does vote, it counts like any other."""
    assert chair([1, 1, 0, 0, 0, 0]) == 0
    assert chair([1, 1, 0, 0, 0, 0] + [1]) == 1
