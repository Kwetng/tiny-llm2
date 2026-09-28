"""
chair_effect.py - did each new seat actually improve the committee, or did it get lucky?

The panel has grown from five experts to nine. Every time a seat was added it was easy to point
at a bigger number and call it progress. This script refuses to do that. For each step it asks
the same three questions, in the same way, and writes the answers to
outputs/chair_effect.json for the dashboard and the guide.

  1. How much did the Sharpe ratio move?
  2. Could that be luck? A block bootstrap (8-week blocks, 4,000 resamples) puts a 95% interval
     around the difference and reports how often the newer chair did no better. Blocks rather
     than single weeks, because weekly returns are not independent.
  3. Does it survive dropping 2020? That year was extraordinary for Bitcoin and flatters every
     strategy that was long. A result that only exists because of 2020 is not a result.

The verdict wording is fixed in advance:
  interval entirely above zero  -> the seat improved the committee
  interval straddles zero       -> not proven, whatever the headline number says
  interval entirely below zero  -> the seat made the committee worse

    python code/chair_effect.py       # run after panel_backtest.py
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
COST = 0.001
BLOCK, N_BOOT = 8, 4000

# each step of the ladder: (label, key of the earlier chair, key of the later chair)
LADDER = [("Phantom Flow", "old_chair", "no_mkt_chair"),
          ("the market seat", "no_mkt_chair", "no_new_chair"),
          ("chart JEPA + fundamentals", "no_new_chair", "no_qh_chair"),
          ("quantum NN + regime HMM", "no_qh_chair", "chair")]


def sharpe(r):
    sd = r.std(ddof=1)
    return float(r.mean() / sd * np.sqrt(52)) if sd > 0 else 0.0


def main():
    R = json.load(open(ROOT / "outputs" / "panel_results.json"))
    n = R["weeks"]
    price = np.asarray(R["price"], dtype=float)
    simple = price[1:n + 1] / price[:n] - 1
    dates = R["dates"][:n]
    after_2020 = np.array([d >= "2021" for d in dates])

    def actions(key):
        if key == "chair":
            return np.asarray(R["action"]["Panel chair (consensus)"][:n])
        return np.asarray(R[key]["action"][:n])

    def returns(a):
        return a * simple - COST * np.abs(np.diff(np.concatenate([[0], a])))

    rng = np.random.default_rng(11)
    idxs = [np.concatenate([np.arange(s, s + BLOCK) % n for s in rng.integers(0, n, n // BLOCK + 1)])[:n]
            for _ in range(N_BOOT)]

    out = {"weeks": n, "blocks": BLOCK, "resamples": N_BOOT, "steps": []}
    for label, before, after in LADDER:
        a0, a1 = actions(before), actions(after)
        r0, r1 = returns(a0), returns(a1)
        diff = sharpe(r1) - sharpe(r0)
        boot = np.array([sharpe(r1[i]) - sharpe(r0[i]) for i in idxs])
        lo, hi = np.percentile(boot, [2.5, 97.5])
        changed = int((a0 != a1).sum())
        verdict = ("improved the committee" if lo > 0 else
                   "made the committee worse" if hi < 0 else
                   "not proven: the interval includes zero")
        step = {"seat": label, "sharpe_before": sharpe(r0), "sharpe_after": sharpe(r1), "diff": diff,
                "ci95": [float(lo), float(hi)], "p_no_better": float((boot <= 0).mean()),
                "weeks_changed": changed, "share_changed": changed / n,
                "ex2020_before": sharpe(r0[after_2020]), "ex2020_after": sharpe(r1[after_2020]),
                "survives_ex2020": bool(sharpe(r1[after_2020]) > sharpe(r0[after_2020])),
                "verdict": verdict}
        out["steps"].append(step)
        print(f"\n{label}")
        print(f"  Sharpe {step['sharpe_before']:.2f} -> {step['sharpe_after']:.2f}  ({diff:+.2f})")
        print(f"  95% interval [{lo:+.2f}, {hi:+.2f}], no better in {step['p_no_better']:.0%} of resamples")
        print(f"  excluding 2020: {step['ex2020_before']:.2f} -> {step['ex2020_after']:.2f}"
              f"  ({'survives' if step['survives_ex2020'] else 'does not survive'})")
        print(f"  changed the call in {changed} of {n} weeks -> {verdict}")

    json.dump(out, open(ROOT / "outputs" / "chair_effect.json", "w"), indent=1)
    print(f"\nWrote outputs/chair_effect.json")


if __name__ == "__main__":
    main()
