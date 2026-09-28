"""
prediction_market.py - turns BTC prediction markets into one weekly signal for the panel.

WHY THIS IS A DIFFERENT KIND OF EXPERT
The other six experts are models. This one is not: it reads what thousands of people are
paying, right now, for contracts that pay out on Bitcoin's price. It is the market's own
opinion, which is the one view a panel of models cannot produce for itself.

TWO SOURCES, TWO DIFFERENT THINGS (both public, no key needed for market data)

  Polymarket  a ladder of TOUCH contracts, monthly:
                "Will Bitcoin reach $150,000 in March?"   -> up-barrier at 150,000
                "Will Bitcoin dip to $65,000 in March?"   -> down-barrier at 65,000
              Many strikes at once, so you get the shape of the market's expected range.

  Kalshi      TERMINAL price ranges at a fixed moment (floor_strike / cap_strike), daily
              and weekly. This is a genuine probability distribution for the closing price.

THREE TRAPS, AND WHAT THIS FILE DOES ABOUT THEM

  1. TOUCH IS NOT CLOSE. "Will Bitcoin reach $150k in March" asks whether the price ever
     touches that level, not where it ends up. For a driftless random walk the reflection
     principle gives P(touch b) = 2 x P(end above b), so reading the ladder as if it were a
     distribution of closing prices makes every number about twice too big.
     -> `touch_to_terminal()` halves it, and says so. The panel VOTE never uses that
        conversion: it uses `lean()`, where the factor cancels (see trap 3).

  2. HORIZON MISMATCH. The panel calls the next 7 days. Polymarket's contracts run to a
     fixed month end, so on 1 March the question covers 31 days and on 28 March, 3 days.
     -> The SIGN of the lean survives this; the SIZE does not. So the lean drives a
        LONG/FLAT/SHORT vote, and `benchmark` work that needs a real 7-day probability
        uses Kalshi's short-dated terminal contracts instead.

  3. A PRICE IS NOT A PURE FORECAST. It carries a risk premium and the cost of tying money
     up. Small over days, real over months, and it pushes both sides of the ladder the
     same way.
     -> The signal is a DIFFERENCE between two symmetric contracts, so a common bias in
        both legs cancels. That is the main reason the lean is the signal and the raw
        probability is not.

THE SIGNAL
    lean = P(touch spot x (1+k)) - P(touch spot x (1-k))        with k = 10% by default
Both legs are the same distance from spot, in the same market, on the same expiry. Positive
means the crowd pays more for the move up than for the equivalent move down.

NO INVENTED DATA. Every function here either has real quotes or returns None, and the panel
treats None as "abstain" (FLAT). The fetchers were written against the published API shapes
but could not be run from the environment that built this file - see README.
"""
import json, math, re, time, urllib.parse, urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

GAMMA = "https://gamma-api.polymarket.com/markets"
CLOB_HISTORY = "https://clob.polymarket.com/prices-history"
KALSHI = "https://external-api.kalshi.com/trade-api/v2/markets"
DEFAULT_K = 0.10                 # compare a +10% move with a -10% move
MIN_STRIKES_PER_SIDE = 2         # fewer than this and we abstain rather than guess
VOTE_THRESHOLD = 0.06            # |lean| must clear this to vote LONG or SHORT


def _get(url, params=None, timeout=30, headers=None):
    """GET a public JSON endpoint over HTTPS. Raises on anything but 200."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params, doseq=True)
    if not url.startswith("https://"):
        raise ValueError("prediction market sources must be HTTPS")
    req = urllib.request.Request(url, headers=headers or {"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310 - HTTPS enforced above
        return json.load(r)


# ---------------------------------------------------------------------------------------
# 1. Reading a Polymarket question into a barrier
# ---------------------------------------------------------------------------------------
# "Will Bitcoin reach $150,000 in March?"  -> ("up",   150000.0)
# "Will Bitcoin dip to $65,000 in March?"  -> ("down",  65000.0)
# "Will Bitcoin hit $120k by Friday?"      -> ("up",   120000.0)
UP_WORDS = ("reach", "hit", "above", "exceed", "top")
DOWN_WORDS = ("dip", "fall", "drop", "below", "under")
_MONEY = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|m)?", re.I)


def parse_barrier(question: str) -> Optional[tuple]:
    """Return ('up'|'down', strike) for a BTC touch market, or None if it is not one."""
    if not question:
        return None
    q = question.lower()
    if "bitcoin" not in q and "btc" not in q:
        return None
    m = _MONEY.search(q)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    suffix = (m.group(2) or "").lower()
    value *= {"k": 1e3, "m": 1e6, "": 1.0}[suffix]
    # a bare "150" in a Bitcoin market means 150,000
    if suffix == "" and value < 1000:
        value *= 1e3
    before = q[: m.start()]
    if any(w in before for w in DOWN_WORDS):
        return "down", value
    if any(w in before for w in UP_WORDS):
        return "up", value
    return None


# ---------------------------------------------------------------------------------------
# 2. A ladder of barriers, and the lean it implies
# ---------------------------------------------------------------------------------------
@dataclass
class Ladder:
    """One expiry's worth of touch quotes, seen at one moment."""
    as_of: str                                   # YYYY-MM-DD
    expiry: str                                  # YYYY-MM-DD
    spot: float
    up: Dict[float, float] = field(default_factory=dict)      # strike -> P(touch), strike > spot
    down: Dict[float, float] = field(default_factory=dict)    # strike -> P(touch), strike < spot
    source: str = "polymarket"

    def days_to_expiry(self) -> float:
        d = (datetime.fromisoformat(self.expiry) - datetime.fromisoformat(self.as_of)).days
        return float(max(d, 0))


def _interp_touch(rungs, k):
    """P(touch) at a relative distance k, interpolated from {strike: prob} against spot.

    Touch probability falls away roughly geometrically as the barrier moves further from
    spot, so we interpolate log(probability) against log(distance). We only interpolate
    BETWEEN two real quotes: past the end of the ladder we return None and abstain, because
    extrapolating a probability is inventing one.
    """
    pts = sorted((d, p) for d, p in rungs if 0 < p < 1 and d > 0)
    if len(pts) < MIN_STRIKES_PER_SIDE:
        return None
    # a strike sitting exactly on k must count on both sides: 1 - 0.80 is 0.19999999999999996,
    # so a bare <= / >= comparison would abstain over floating-point dust
    at = lambda d: math.isclose(d, k, rel_tol=1e-9)
    lo = [(d, p) for d, p in pts if d <= k or at(d)]
    hi = [(d, p) for d, p in pts if d >= k or at(d)]
    if not lo or not hi:
        return None                                    # k is outside the quoted range
    d0, p0 = lo[-1]
    d1, p1 = hi[0]
    if math.isclose(d0, d1):
        return float(p0)
    w = (math.log(k) - math.log(d0)) / (math.log(d1) - math.log(d0))
    return float(math.exp(math.log(p0) + w * (math.log(p1) - math.log(p0))))


def lean(ladder: Ladder, k: float = DEFAULT_K) -> Optional[dict]:
    """The signal: how much more the crowd pays for a +k% move than for a -k% move.

    Returns None when either side of the ladder does not bracket k, so the expert abstains.
    """
    s = ladder.spot
    up = _interp_touch([((x / s) - 1, p) for x, p in ladder.up.items() if x > s], k)
    down = _interp_touch([(1 - (x / s), p) for x, p in ladder.down.items() if x < s], k)
    if up is None or down is None:
        return None
    return {"lean": up - down, "p_touch_up": up, "p_touch_down": down, "k": k,
            "days_to_expiry": ladder.days_to_expiry(), "expiry": ladder.expiry, "spot": s,
            "n_up": len(ladder.up), "n_down": len(ladder.down), "source": ladder.source}


def touch_to_terminal(p_touch: float) -> float:
    """Rough conversion from 'ever touches' to 'ends up past it'.

    Reflection principle, driftless: P(max over the period >= b) = 2 x P(end >= b).
    So the terminal probability is about half the touch probability. Bitcoin is not
    driftless and this ignores that, which is exactly why it is used only for display and
    for the benchmark's fallback, never for the panel's vote.
    """
    return float(min(1.0, max(0.0, p_touch / 2)))


def p_up_from_lean(value: float) -> float:
    """Put the lean on the panel's 0-1 'chance it is higher in 7 days' scale.

    This is a presentation choice, not a probability: the lean's SIZE is not horizon
    adjusted (trap 2). Only its sign and the vote threshold carry weight.
    """
    return float(min(0.99, max(0.01, 0.5 + value / 2)))


def vote(value: Optional[float], threshold: float = VOTE_THRESHOLD) -> int:
    """LONG (1), SHORT (-1) or FLAT (0). No data means FLAT: abstaining, not guessing."""
    if value is None:
        return 0
    return 1 if value >= threshold else -1 if value <= -threshold else 0


# ---------------------------------------------------------------------------------------
# 3. Sources
# ---------------------------------------------------------------------------------------
class PolymarketSource:
    """Builds touch ladders from Polymarket's public Gamma + CLOB endpoints.

    Gamma lists the markets and their CLOB token ids; CLOB /prices-history gives each
    token's price over time. A 'Yes' price is the market-implied probability.
    """
    name = "polymarket"

    def list_btc_markets(self, closed=True, min_volume=50_000, page=500, max_pages=20):
        out, offset = [], 0
        for _ in range(max_pages):
            batch = _get(GAMMA, {"limit": page, "offset": offset, "closed": str(closed).lower(),
                                 "volume_num_min": min_volume})
            if not batch:
                break
            for m in batch:
                bar = parse_barrier(m.get("question") or "")
                if not bar or not m.get("endDate"):
                    continue
                try:                                     # Gamma returns these as JSON strings
                    tokens = json.loads(m.get("clobTokenIds") or "[]")
                    outcomes = [o.lower() for o in json.loads(m.get("outcomes") or "[]")]
                except (TypeError, ValueError):
                    continue
                if "yes" not in outcomes or len(tokens) != len(outcomes):
                    continue
                out.append({"question": m["question"], "direction": bar[0], "strike": bar[1],
                            "expiry": m["endDate"][:10], "volume": float(m.get("volume") or 0),
                            "yes_token": tokens[outcomes.index("yes")]})
            offset += page
        return out

    def price_history(self, token_id, start_ts=None, end_ts=None, fidelity=60):
        params = {"market": token_id, "fidelity": fidelity}
        if start_ts:
            params["startTs"] = int(start_ts)
        if end_ts:
            params["endTs"] = int(end_ts)
        hist = _get(CLOB_HISTORY, params).get("history", [])
        return [(int(h["t"]), float(h["p"])) for h in hist]


class KalshiSource:
    """Kalshi's BTC contracts quote TERMINAL price ranges (floor_strike / cap_strike) at a
    fixed moment, daily and weekly. That is a real distribution of the closing price, which
    is what the benchmark test needs. Listing markets needs no key."""
    name = "kalshi"

    def list_btc_markets(self, series_ticker="KXBTCD", status="settled", limit=1000):
        out, cursor = [], None
        while True:
            params = {"series_ticker": series_ticker, "status": status, "limit": limit}
            if cursor:
                params["cursor"] = cursor
            page = _get(KALSHI, params)
            for m in page.get("markets", []):
                out.append({"ticker": m.get("ticker"), "floor": m.get("floor_strike"),
                            "cap": m.get("cap_strike"), "strike_type": m.get("strike_type"),
                            "close_time": m.get("close_time"), "result": m.get("result"),
                            "last_price": m.get("last_price_dollars"),
                            "yes_bid": m.get("yes_bid_dollars"), "yes_ask": m.get("yes_ask_dollars")})
            cursor = page.get("cursor")
            if not cursor or not page.get("markets"):
                return out


# ---------------------------------------------------------------------------------------
# 4. The weekly cache the panel reads
# ---------------------------------------------------------------------------------------
SCHEMA = """data/prediction_market.json
{
 "source": "polymarket",
 "fetched": "2026-09-28",
 "k": 0.10,
 "weekly": {
   "2026-05-17": {"lean": 0.12, "p_touch_up": 0.31, "p_touch_down": 0.19, "k": 0.1,
                  "days_to_expiry": 15, "expiry": "2026-06-01", "spot": 77497.7,
                  "n_up": 4, "n_down": 3, "source": "polymarket"}
 }
}
Weeks that are absent, and weeks whose ladder did not bracket k, are ABSENT from "weekly".
The panel abstains on those, which is most of 2020-2024: these markets did not exist then."""


class WeeklySignals:
    """Loads the cache. Missing weeks return None and the expert votes FLAT."""

    def __init__(self, path):
        self.path = Path(path)
        self.meta, self.weekly = {}, {}
        if self.path.exists():
            blob = json.load(open(self.path))
            self.weekly = blob.get("weekly", {})
            self.meta = {k: v for k, v in blob.items() if k != "weekly"}

    def __len__(self):
        return len(self.weekly)

    @property
    def available(self):
        return bool(self.weekly)

    def get(self, date) -> Optional[dict]:
        return self.weekly.get(str(date)[:10])

    def lean_on(self, date) -> Optional[float]:
        rec = self.get(date)
        return None if rec is None else float(rec["lean"])

    def covered_dates(self):
        return sorted(self.weekly)

    def save(self, weekly, source, k=DEFAULT_K):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        json.dump({"source": source, "fetched": time.strftime("%Y-%m-%d"), "k": k,
                   "weekly": weekly}, open(self.path, "w"), indent=1)
        self.weekly, self.meta = weekly, {"source": source, "k": k}
        return self
