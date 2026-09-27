"""
build_guide.py - puts the latest comparison results into the guide and rebuilds the Word version.

    python compare_credit.py --a jev --b laya --extra-test 3600
    python build_guide.py                 # needs node + the docx package (npm i docx)

It replaces everything between the RESULTS markers in docs/laya-vs-jev-guide.md with
outputs/comparison_report.md, then runs tools/build_docx.js. Without a real run it leaves the
"results pending" text in place: plumbing-test numbers are never put in the guide.
"""
import json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs" / "laya-vs-jev-guide.md"
REPORT, METRICS = ROOT / "outputs" / "comparison_report.md", ROOT / "outputs" / "metrics.json"
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"

md = GUIDE.read_text()
if REPORT.exists() and METRICS.exists() and not json.loads(METRICS.read_text())["meta"]["plumbing_test"]:
    rep = REPORT.read_text().split("\n", 1)[1]                                   # drop the report's own title
    rep = rep.split("## Calibration by PD bucket")[0]                             # detail stays in outputs/
    rep = rep.replace("## ", "## Results: ")
    figs = [("calibration.png", "Calibration: predicted PD against realised default rate, raw and recalibrated"),
            ("roc.png", "Ranking: defaulters caught against good borrowers flagged"),
            ("pd_agreement.png", "Agreement: each borrower's PD from the two models"),
            ("latency.png", "Speed: time per borrower")]
    rep += "\n" + "\n\n".join(f"![{cap}](../outputs/{f})" for f, cap in figs) + "\n"
    md = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda m: f"{START}\n\n{rep}\n\n{END}", md, flags=re.S)
    GUIDE.write_text(md)
    print("guide updated with results from", REPORT)
else:
    print("no real comparison run found (or only a plumbing test): guide keeps 'results pending'")

tool = ROOT.parent / "tools" / "build_docx.js"
env = {**os.environ, "DOC_HEADER": "Laya vs Jev: credit decisions"}
subprocess.run(["node", str(tool), GUIDE.name, "Laya_vs_Jev_Credit_Guide.docx"], cwd=GUIDE.parent, env=env, check=True)
print("wrote docs/Laya_vs_Jev_Credit_Guide.docx")
