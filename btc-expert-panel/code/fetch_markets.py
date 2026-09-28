"""
fetch_markets.py - builds the weekly prediction-market cache the panel reads.

Run this on a machine with internet access (the environment that built this repository
could not reach either API):

    python code/fetch_markets.py                       # Polymarket touch ladders
    python code/fetch_markets.py --source kalshi       # Kalshi terminal ranges
    python code/fetch_markets.py --k 0.15 --min-days 5

It writes ../data/prediction_market.json. Then re-run the panel:

    python code/panel_backtest.py --offline
    python code/make_dashboard.py

For every Sunday in the panel's history it:
  1. picks the nearest expiry that is still at least --min-days away,
  2. collects every BTC barrier contract on that expiry and its price on that Sunday,
  3. computes the lean (see prediction_market.py) and stores it.

Sundays where fewer than two strikes on a side bracket the target distance are LEFT OUT.
The panel abstains on those. Most of 2020-2024 will be absent: these markets did not exist
or had no liquidity, and that is a fact about the world, not a bug to paper over.
"""
import argparse, json, sys, time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prediction_market import (DEFAULT_K, KalshiSource, Ladder, PolymarketSource,  # noqa: E402
                               WeeklySignals, lean)

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
CACHE = DATA / "prediction_market.json"
RAW = DATA / "prediction_market_raw"            # per-contract price history, so a re-run resumes


def weekly_spot():
    """The same Sunday closes the panel uses, from the Coin Metrics file it already downloads."""
    f = DATA / "btc.csv"
    if not f.exists():
        sys.exit(f"{f} not found - run panel_backtest.py once first, it downloads the price data.")
    cm = pd.read_csv(f, parse_dates=["time"], low_memory=False).set_index("time").sort_index()
    p = cm["PriceUSD"].dropna()
    wk = p.reindex(pd.date_range(p.index.min(), p.index.max(), freq="W-SUN")).dropna()
    return wk


def fetch_polymarket(spot, k, min_days, min_volume):
    src = PolymarketSource()
    print("listing Polymarket BTC barrier markets ...")
    markets = src.list_btc_markets(min_volume=min_volume)
    print(f"  {len(markets)} markets parsed as a Bitcoin barrier with an expiry")
    if not markets:
        return {}, src.name
    RAW.mkdir(parents=True, exist_ok=True)
    series = {}
    for i, m in enumerate(markets, 1):
        cache = RAW / f"{m['yes_token']}.json"
        if cache.exists():
            hist = json.load(open(cache))
        else:
            try:
                hist = src.price_history(m["yes_token"])
            except Exception as e:                                        # noqa: BLE001
                print(f"  [{i}/{len(markets)}] {m['question'][:48]}: {e}")
                hist = []
            json.dump(hist, open(cache, "w"))
            time.sleep(0.2)                                              # be polite to a free API
        if hist:
            s = pd.Series({pd.Timestamp(t, unit="s", tz="UTC").tz_localize(None): p for t, p in hist})
            series[id(m)] = s.sort_index()
            m["_key"] = id(m)
        if i % 25 == 0:
            print(f"  [{i}/{len(markets)}] fetched")

    by_expiry = {}
    for m in markets:
        if "_key" in m:
            by_expiry.setdefault(m["expiry"], []).append(m)

    weekly = {}
    for date, s in spot.items():
        expiries = sorted(e for e in by_expiry if (pd.Timestamp(e) - date).days >= min_days)
        if not expiries:
            continue
        exp = expiries[0]
        up, down = {}, {}
        for m in by_expiry[exp]:
            ser = series[m["_key"]]
            past = ser.loc[:date]
            if past.empty or (date - past.index[-1]).days > 3:            # no fresh quote that week
                continue
            (up if m["direction"] == "up" else down)[m["strike"]] = float(past.iloc[-1])
        out = lean(Ladder(as_of=str(date.date()), expiry=exp, spot=float(s), up=up, down=down,
                          source="polymarket"), k=k)
        if out:
            weekly[str(date.date())] = {kk: (round(vv, 5) if isinstance(vv, float) else vv)
                                        for kk, vv in out.items()}
    return weekly, "polymarket"


def _interp_at(above, x):
    """P(close >= x), linearly interpolated between the two nearest quoted floors."""
    pts = sorted(above.items())
    lo = [(f, p) for f, p in pts if f <= x]
    hi = [(f, p) for f, p in pts if f >= x]
    if not lo or not hi:
        return None
    f0, p0 = lo[-1]
    f1, p1 = hi[0]
    if f1 == f0:
        return float(p0)
    return float(p0 + (x - f0) / (f1 - f0) * (p1 - p0))


def fetch_kalshi(spot, k, min_days):
    """Kalshi quotes terminal ranges, so the 'ladder' is built from cumulative range prices.

    P(close above X) is the sum of the probabilities of every range entirely above X. That
    is a real distribution of the closing price, which is what the benchmark test wants.
    """
    src = KalshiSource()
    print("listing Kalshi BTC markets ...")
    rows = src.list_btc_markets()
    print(f"  {len(rows)} markets")
    if not rows:
        return {}, src.name
    df = pd.DataFrame(rows).dropna(subset=["close_time"])
    df["close"] = pd.to_datetime(df.close_time, errors="coerce", utc=True).dt.tz_localize(None)
    df["p"] = pd.to_numeric(df.last_price, errors="coerce")
    df = df.dropna(subset=["close", "p"])
    weekly = {}
    for date, s in spot.items():
        day = df[(df["close"] > date + pd.Timedelta(days=min_days)) &
                 (df["close"] <= date + pd.Timedelta(days=10))]
        if day.empty:
            continue
        exp = day["close"].min()
        day = day[day["close"] == exp]
        above = {float(r.floor): float(day[day.floor >= r.floor].p.sum())
                 for r in day.itertuples() if pd.notna(r.floor)}
        up = {x: p for x, p in above.items() if x > s}
        down = {x: 1 - p for x, p in above.items() if x < s}
        # a genuine P(close above today's price) - the number the benchmark test compares against
        p_up_terminal = _interp_at(above, float(s))
        out = lean(Ladder(as_of=str(date.date()), expiry=str(exp.date()), spot=float(s),
                          up=up, down=down, source="kalshi"), k=k)
        if out:
            out["terminal"] = True                       # already a closing-price probability
            if p_up_terminal is not None:
                out["p_up_terminal"] = round(p_up_terminal, 5)
            weekly[str(date.date())] = {kk: (round(vv, 5) if isinstance(vv, float) else vv)
                                        for kk, vv in out.items()}
    return weekly, "kalshi"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["polymarket", "kalshi"], default="polymarket")
    ap.add_argument("--k", type=float, default=DEFAULT_K, help="how far from spot to compare, e.g. 0.10")
    ap.add_argument("--min-days", type=int, default=5, help="skip an expiry closer than this")
    ap.add_argument("--min-volume", type=float, default=50_000, help="Polymarket: ignore illiquid markets")
    ap.add_argument("--out", default=str(CACHE))
    args = ap.parse_args()

    spot = weekly_spot()
    print(f"{len(spot)} Sundays, {spot.index.min().date()} to {spot.index.max().date()}")
    if args.source == "polymarket":
        weekly, source = fetch_polymarket(spot, args.k, args.min_days, args.min_volume)
    else:
        weekly, source = fetch_kalshi(spot, args.k, args.min_days)

    WeeklySignals(args.out).save(weekly, source, args.k)
    if weekly:
        d = sorted(weekly)
        longs = sum(v["lean"] > 0 for v in weekly.values())
        print(f"\n{len(weekly)} of {len(spot)} Sundays covered ({d[0]} to {d[-1]}), "
              f"{longs} leaning up. Saved to {args.out}")
        print("Now re-run: python code/panel_backtest.py --offline && python code/make_dashboard.py")
    else:
        print("\nNo week produced a usable ladder. The panel will abstain on every week, and the "
              "backtest results will be unchanged. Check --k, --min-days and --min-volume.")


if __name__ == "__main__":
    main()
