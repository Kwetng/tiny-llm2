"""pf_effect.py - did adding Phantom Flow really improve the panel chair, or was it luck?

Reads outputs/panel_results.json and writes outputs/phantom_flow_effect.json:
  - Sharpe of the chair with and without Phantom Flow, over the whole test and excluding 2020
  - a block bootstrap (8-week blocks, 4,000 resamples) of the Sharpe difference, giving a 95% interval
    and the share of resamples where the new chair did no better
  - calendar years in which the new chair beat the old one

    python code/pf_effect.py      # run after panel_backtest.py; make_dashboard.py reads the result
"""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
R = json.load(open(ROOT / "outputs" / "panel_results.json"))
n = R["weeks"]
NEW, OLD = "Panel chair (consensus)", "Chair without Phantom Flow"


def rets(k):
    e = np.array(R["perf"][k]["equity"])
    return e / np.concatenate([[1], e[:-1]]) - 1


def sharpe(r):
    return float(r.mean() / r.std(ddof=1) * np.sqrt(52))


a, b = rets(NEW), rets(OLD)
dates = np.array(R["dates"][:n])
ex20 = np.array([d >= "2021" for d in dates])
rng = np.random.default_rng(1)
diffs = []
for _ in range(4000):
    idx = np.concatenate([np.arange(s, s + 8) % n for s in rng.integers(0, n, n // 8 + 1)])[:n]
    diffs.append(sharpe(a[idx]) - sharpe(b[idx]))
diffs = np.array(diffs)
years = R["perf"][NEW]["yearly"]
out = {"sharpe_new": sharpe(a), "sharpe_old": sharpe(b), "diff": sharpe(a) - sharpe(b),
       "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
       "p_no_better": float((diffs <= 0).mean()),
       "ex2020": {"new": sharpe(a[ex20]), "old": sharpe(b[ex20]), "buy_hold": sharpe(rets("Buy & hold")[ex20])},
       "years_better": [y for y in years if years[y] > R["perf"][OLD]["yearly"][y]], "years": list(years),
       "weeks_different": int(sum(x != y for x, y in zip(R["action"][NEW][:n], R["old_chair"]["action"][:n])))}
json.dump(out, open(ROOT / "outputs" / "phantom_flow_effect.json", "w"), indent=1)
print(f"Chair Sharpe with Phantom Flow {out['sharpe_new']:.2f} vs without {out['sharpe_old']:.2f}: difference {out['diff']:+.2f}, "
      f"95% interval [{out['ci95'][0]:+.2f}, {out['ci95'][1]:+.2f}], no better in {out['p_no_better']:.0%} of resamples")
print(f"Excluding 2020: {out['ex2020']['new']:.2f} vs {out['ex2020']['old']:.2f} (buy & hold {out['ex2020']['buy_hold']:.2f}); "
      f"better in {len(out['years_better'])} of {len(years)} calendar years; {out['weeks_different']} weeks with a different call")
