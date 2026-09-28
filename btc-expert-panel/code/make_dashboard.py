"""make_dashboard.py - builds dashboard/index.html (a self-contained page) from outputs/panel_results.json.

    python code/make_dashboard.py     # run from the btc-expert-panel folder
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = json.load(open(ROOT / "outputs" / "panel_results.json"))
n_done = R["weeks"]
R["action"]["Chair without Phantom Flow"] = R["old_chair"]["action"]
R["p"]["Chair without Phantom Flow"] = R["old_chair"]["p"]
R["action"]["Chair without the market"] = R["no_mkt_chair"]["action"]
R["p"]["Chair without the market"] = R["no_mkt_chair"]["p"]
R["action"]["Chair without JEPA + fundamentals"] = R["no_new_chair"]["action"]
R["p"]["Chair without JEPA + fundamentals"] = R["no_new_chair"]["p"]
data = {
    "experts": R["experts"], "dates": R["dates"], "price": [round(p, 2) for p in R["price"]],
    "p": {k: [round(v, 3) for v in vs] for k, vs in R["p"].items()},
    "action": R["action"], "regime": R["regime"], "surprise": [round(s, 2) for s in R["llm_surprise"]],
    "equity": {k: [round(v, 5) for v in m["equity"]] for k, m in R["perf"].items()},
    "yearly": {k: m["yearly"] for k, m in R["perf"].items()},
    "agreement": R["agreement"], "latest": R["latest"], "n_done": n_done, "benchmarks": R["benchmarks"],
    "phantom_flow": R["phantom_flow"], "pf_sensitivity": R["pf_sensitivity"],
    "pf_effect": json.load(open(ROOT / "outputs" / "phantom_flow_effect.json")),
    "market_eval": R["market_eval"], "jepa": R["jepa"], "fundamentals": R["fundamentals"],
    "chair_effect": json.load(open(ROOT / "outputs" / "chair_effect.json")),
    "meta": {k: R[k] for k in ("decision_model", "data_to", "live_week", "live_price", "test_start", "test_end", "cost_bp", "thresholds", "generated")},
}
html = (ROOT / "code" / "dashboard_template.html").read_text().replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
(ROOT / "dashboard").mkdir(exist_ok=True)
page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n</head>\n<body>\n'
        + html + '\n</body>\n</html>\n')
(ROOT / "dashboard" / "index.html").write_text(page)          # open this file in any browser
if len(__import__("sys").argv) > 1:                             # optional: bare fragment for hosting inside another page
    Path(__import__("sys").argv[1]).write_text(html)
print(f"wrote dashboard/index.html ({len(page) / 1024:.0f} KB)")
