"""
phantom_flow.py - an open re-implementation of the three modules of the "Phantom Flow" trading indicator.

Phantom Flow is a closed-source, paid TradingView indicator (Pine Script v6). Its published description lists:
  1. Phantom Shift      - trend direction from ATR bands around price; BUY / SELL when the direction flips
  2. Structure (SMC)    - swing structure: break of structure (BOS) and change of character (CHoCH)
  3. Phantom Oscillator - momentum relative to a moving average
  and a "Combo" signal when Shift and Oscillator agree.
The exact formulas are not public. This file implements each module with the standard textbook method,
so it is NOT the proprietary script and its signals will differ from it. Order blocks and fair value gaps
need intrabar highs and lows, which the public data here does not have, so they are left out.

Data: daily closes only (Coin Metrics community data). The true range is therefore |close - previous close|.

No look-ahead: every value at day t uses closes up to t only. A swing high or low needs PIVOT days on each
side, so it is only "known" PIVOT days after it happened (unlike TradingView drawings that appear on the
pivot bar itself and so repaint history). tests/test_phantom_flow.py checks this.

Parameters are common defaults, fixed before the backtest and not tuned on it:
  Shift: ATR 10, multiplier 3.0 | Structure: pivots of 5 days each side | Oscillator: (close - EMA 21) / ATR 14,
  smoothed with EMA 3.
"""
import numpy as np
import pandas as pd

DEFAULTS = {"atr_n": 10, "mult": 3.0, "pivot": 5, "ma_n": 21, "osc_atr_n": 14, "osc_smooth": 3}


def wilder_atr(close: pd.Series, n: int) -> pd.Series:
    tr = close.diff().abs()
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def phantom_shift(close: pd.Series, atr_n=10, mult=3.0):
    """SuperTrend-style trailing stop on closes. Returns (state +1/-1, active stop level)."""
    c = close.values; a = wilder_atr(close, atr_n).values
    n = len(c)
    up, dn = np.full(n, np.nan), np.full(n, np.nan)
    state, stop = np.zeros(n, dtype=int), np.full(n, np.nan)
    s = 1
    for t in range(n):
        if np.isnan(a[t]):
            continue
        bu, bd = c[t] - mult * a[t], c[t] + mult * a[t]
        if t > 0 and not np.isnan(up[t - 1]):
            up[t] = max(bu, up[t - 1]) if c[t - 1] > up[t - 1] else bu      # long stop only ratchets up
            dn[t] = min(bd, dn[t - 1]) if c[t - 1] < dn[t - 1] else bd      # short stop only ratchets down
            if s == -1 and c[t] > dn[t - 1]:
                s = 1
            elif s == 1 and c[t] < up[t - 1]:
                s = -1
        else:
            up[t], dn[t] = bu, bd
        state[t] = s
        stop[t] = up[t] if s == 1 else dn[t]
    return pd.Series(state, close.index), pd.Series(stop, close.index)


def structure(close: pd.Series, pivot=5):
    """Swing structure on closes. Returns (state +1/-1/0, event per day: 'BOS+', 'CHoCH+', 'BOS-', 'CHoCH-' or '')."""
    c = close.values; n = len(c)
    state, events = np.zeros(n, dtype=int), [""] * n
    last_hi = last_lo = np.nan
    hi_live = lo_live = False
    s = 0
    for t in range(n):
        p = t - pivot                                       # the pivot candidate confirmed today
        if p - pivot >= 0:
            win = c[p - pivot:t + 1]
            if c[p] == win.max():
                last_hi, hi_live = c[p], True
            if c[p] == win.min():
                last_lo, lo_live = c[p], True
        if hi_live and c[t] > last_hi:                      # close breaks the last swing high
            events[t] = "CHoCH+" if s == -1 else "BOS+"; s, hi_live = 1, False
        elif lo_live and c[t] < last_lo:                    # close breaks the last swing low
            events[t] = "CHoCH-" if s == 1 else "BOS-"; s, lo_live = -1, False
        state[t] = s
    return pd.Series(state, close.index), pd.Series(events, close.index)


def oscillator(close: pd.Series, ma_n=21, atr_n=14, smooth=3) -> pd.Series:
    """Momentum relative to a moving average, in ATRs: (close - EMA) / ATR, lightly smoothed."""
    raw = (close - close.ewm(span=ma_n, adjust=False, min_periods=ma_n).mean()) / wilder_atr(close, atr_n)
    return raw.ewm(span=smooth, adjust=False).mean()


def compute(close: pd.Series, **params) -> pd.DataFrame:
    """All modules plus the combined call, one row per day."""
    p = {**DEFAULTS, **params}
    shift, stop = phantom_shift(close, p["atr_n"], p["mult"])
    struct, ev = structure(close, p["pivot"])
    osc = oscillator(close, p["ma_n"], p["osc_atr_n"], p["osc_smooth"])
    osc_sign = np.sign(osc).fillna(0).astype(int)
    score = shift + struct + osc_sign                                          # -3 .. +3
    combo = np.where((shift == osc_sign) & (shift != 0), shift, 0)             # Phantom Flow's "Combo": Shift and Oscillator agree
    call = np.where((combo != 0) & (struct != -combo), combo, 0)               # ...and structure does not contradict
    return pd.DataFrame({"close": close, "shift": shift, "stop": stop, "structure": struct, "event": ev,
                         "osc": osc, "score": score, "combo": combo, "call": call}, index=close.index)


def p_up(score: int) -> float:
    """Display-only mapping of the -3..+3 confluence score to the panel's 0-1 'P(up)' scale (not a probability)."""
    return 0.5 + score / 8
