"""
fundamentals.py - the fundamental-analysis seat: what is Bitcoin actually worth?

Equities have earnings and cash flows. Bitcoin has none, so "fundamental analysis" here means
ON-CHAIN valuation: what the blockchain itself says about what holders paid, what miners earn,
how secure the network is, and how many people use it. Every input is a published, widely used
metric, and all of them come from the Coin Metrics file the panel already downloads.

THE FOUR MEASURES

  1. MVRV - is the price far above what holders actually paid?
     Realised value is every coin priced at the moment it last moved: the market's true cost
     basis. MVRV is market value divided by it, so MVRV of 3 means the average coin is sitting
     on a 200% gain. Historically high readings have marked cycle tops and readings below 1
     have marked bottoms. We take its logarithm, which is symmetric and scale-free.

  2. PUELL MULTIPLE - are miners unusually rich or unusually squeezed?
     Today's newly issued coins in dollars, divided by its own 365-day average. Very high means
     miners are being paid far more than normal and tend to sell into it; very low has marked
     capitulation and, historically, good entry points.

  3. HASH RIBBON - is the network's security growing or shrinking?
     The 30-day average hash rate over the 60-day average. Below 1 means miners are switching
     machines off, which has historically clustered around lows; a recovery back above 1 has
     been a bullish sign.

  4. METCALFE RESIDUAL - is the price ahead of adoption?
     Metcalfe's law says a network is worth roughly the square of its users. Regressing
     log(market cap) on log(active addresses) gives a fair value from usage alone; the residual
     is how far price sits above or below it. The regression is fitted on TRAINING DATA ONLY.

HOW THEY BECOME ONE VOTE
Each measure is turned into a TRAILING Z-SCORE: how unusual today's reading is against its own
previous four years. That matters more than it sounds. An earlier version of this file
standardised against the training window instead, and because Bitcoin's market cap grew roughly
a thousandfold it produced readings like "13 standard deviations cheap" that were arithmetic
artefacts rather than signals. A trailing window uses only past data, so it still looks forward
at nothing, but it stays on a sensible scale for ever.

Each z-score is then sign-flipped so positive always means "cheap or improving". Their average
is the composite score, and a logistic regression - fitted on training weeks only, with balanced
classes so it learns the signal rather than the fact that Bitcoin rose in most weeks - turns
that score into P(up next week).

THE HONEST CAVEAT, AND IT IS THE IMPORTANT ONE
Fundamentals are SLOW. These measures say "Bitcoin is expensive relative to its cost basis",
which is a statement about the next few months, not the next seven days. As a weekly signal
this seat is therefore expected to be weak and to change its mind rarely. That is not a flaw to
be tuned away: its value to a panel is that its mistakes are uncorrelated with the momentum
models, so it disagrees with them at useful moments. Its turnover and its agreement with the
other seats are both reported.
"""
import math

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression

METRICS = ["mvrv", "puell", "hash_ribbon", "metcalfe"]
# +1 where a HIGH reading is bullish, -1 where a high reading means expensive or late-cycle
DIRECTION = {"mvrv": -1, "puell": -1, "hash_ribbon": +1, "metcalfe": -1}
PLAIN = {"mvrv": "price vs what holders paid", "puell": "miner revenue vs normal",
         "hash_ribbon": "network security trend", "metcalfe": "price vs adoption"}
VOTE_Z = 0.50        # act only when valuation is this far from its own four-year norm
TRAIL, MIN_TRAIL = 208, 104          # four years of weeks to judge "unusual" against, two minimum


def trailing_z(s: pd.Series) -> pd.Series:
    """How unusual today's reading is against its own past four years. Causal: today is
    included, the future never is, so a value never changes once it has been computed."""
    mu = s.rolling(TRAIL, min_periods=MIN_TRAIL).mean()
    sd = s.rolling(TRAIL, min_periods=MIN_TRAIL).std().replace(0, np.nan)
    return (s - mu) / sd


def daily_metrics(day: pd.DataFrame) -> pd.DataFrame:
    """Build the four raw measures from the Coin Metrics daily file.

    Needs: PriceUSD, CapMrktCurUSD, CapMVRVCur, IssTotUSD, HashRate, AdrActCnt.
    Nothing here looks forward: every value uses that day and earlier only.
    """
    f = pd.DataFrame(index=day.index)
    f["mvrv"] = np.log(day["CapMVRVCur"])                       # log is symmetric and scale-free
    f["puell"] = np.log(day["IssTotUSD"] / day["IssTotUSD"].rolling(365, min_periods=200).mean())
    f["hash_ribbon"] = (day["HashRate"].rolling(30, min_periods=20).mean()
                        / day["HashRate"].rolling(60, min_periods=40).mean())
    f["log_mcap"] = np.log(day["CapMrktCurUSD"])
    f["log_addr"] = np.log(day["AdrActCnt"].rolling(7, min_periods=4).mean())
    return f


class FundamentalModel:
    """Fitted on one expanding training window, then used unchanged for the following year."""

    def __init__(self):
        self.mu = self.sd = None
        self.metcalfe = None
        self.probe = None
        self.stats = {}

    def score_all(self, f: pd.DataFrame) -> pd.DataFrame:
        """Every measure as a signed trailing z-score, for the WHOLE series at once.

        Computed on the full history because each value depends only on its own past; slicing
        it afterwards is what keeps train and test separate.
        """
        fair = self.metcalfe.predict(f[["log_addr"]].fillna(f["log_addr"].median()).values)
        raw = pd.DataFrame({"mvrv": f["mvrv"], "puell": f["puell"], "hash_ribbon": f["hash_ribbon"],
                            "metcalfe": f["log_mcap"].values - fair}, index=f.index)
        return pd.DataFrame({k: trailing_z(raw[k]) * DIRECTION[k] for k in METRICS}, index=f.index)

    def fit(self, f_all: pd.DataFrame, train_mask, y_next: np.ndarray):
        """The Metcalfe regression and the probe see training weeks only."""
        ok = f_all[train_mask][["log_mcap", "log_addr"]].dropna()
        self.metcalfe = LinearRegression().fit(ok[["log_addr"]].values, ok["log_mcap"].values)
        self._parts = self.score_all(f_all)
        comp = self._parts.mean(axis=1, skipna=True)
        m = np.asarray(train_mask) & comp.notna().values & ~pd.isna(y_next)
        self.probe = LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced").fit(
            comp.values[m].reshape(-1, 1), np.asarray(y_next)[m])
        self.stats = {"metcalfe_slope": float(self.metcalfe.coef_[0]),
                      "metcalfe_r2": float(self.metcalfe.score(ok[["log_addr"]].values, ok["log_mcap"].values)),
                      "probe_coef": float(self.probe.coef_[0, 0]), "n_weeks": int(m.sum())}
        return self

    def parts(self, f: pd.DataFrame) -> pd.DataFrame:
        return self._parts.reindex(f.index)

    def composite(self, f: pd.DataFrame) -> pd.Series:
        return self.parts(f).mean(axis=1, skipna=True)

    def p_up(self, f_row: pd.DataFrame) -> float:
        c = self.composite(f_row)
        if c.isna().all() or pd.isna(c.iloc[-1]):
            return 0.5                                   # not enough history yet: no opinion
        return float(self.probe.predict_proba([[float(c.iloc[-1])]])[0, 1])

    def explain(self, f_row: pd.DataFrame) -> dict:
        """The four standardised readings, for the case file and the dashboard."""
        p = self.parts(f_row).iloc[-1]
        return {k: (None if pd.isna(p[k]) else round(float(p[k]), 2)) for k in METRICS}


def vote(composite_z, threshold: float = VOTE_Z) -> int:
    """LONG when unusually cheap, SHORT when unusually expensive, otherwise FLAT.

    The vote is taken on the valuation score itself rather than on the logistic's P(up),
    because that is how valuation is actually used: you act at extremes, not on a marginal
    tilt. The threshold was fixed at +-0.5 by matching the other seats' activity (about half
    the weeks), before any return was measured. Out of sample it says "expensive" far more
    often than "cheap", which is the familiar weakness of valuation timing in a bull market.
    """
    if composite_z is None or (isinstance(composite_z, float) and math.isnan(composite_z)):
        return 0
    return 1 if composite_z >= threshold else -1 if composite_z <= -threshold else 0
