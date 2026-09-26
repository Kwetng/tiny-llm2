"""Diagrams for the Jev + tiny LLM credit guide (flow, decision rules, calibration)."""
import json, sys
import cairosvg
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = {"gray": ("#F1EFE8", "#5F5E5A", "#444441", "#5F5E5A"), "purple": ("#EEEDFE", "#534AB7", "#3C3489", "#534AB7"),
     "teal": ("#E1F5EE", "#0F6E56", "#085041", "#0F6E56"), "coral": ("#FAECE7", "#993C1D", "#712B13", "#993C1D"),
     "amber": ("#FAEEDA", "#854F0B", "#633806", "#854F0B"), "green": ("#EAF3DE", "#3B6D11", "#27500A", "#3B6D11"),
     "red": ("#FCEBEB", "#A32D2D", "#791F1F", "#A32D2D")}
A, FONT = "#888780", "DejaVu Sans"

def head(h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="680" height="{h}" viewBox="0 0 680 {h}">'
            f'<rect width="680" height="{h}" fill="#FFFFFF"/><defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" '
            f'markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="{A}" '
            'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>')

def box(x, y, w, h, title, sub, col):
    f, s, tc, sc = C[col]
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{f}" stroke="{s}" stroke-width="0.8"/>'
    cx = x + w / 2
    if sub:
        out += f'<text x="{cx}" y="{y+h/2-10}" text-anchor="middle" dominant-baseline="central" font-family="{FONT}" font-size="14" font-weight="bold" fill="{tc}">{title}</text>'
        out += f'<text x="{cx}" y="{y+h/2+10}" text-anchor="middle" dominant-baseline="central" font-family="{FONT}" font-size="12" fill="{sc}">{sub}</text>'
    else:
        out += f'<text x="{cx}" y="{y+h/2}" text-anchor="middle" dominant-baseline="central" font-family="{FONT}" font-size="14" font-weight="bold" fill="{tc}">{title}</text>'
    return out

def ln(x1, y1, x2, y2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{A}" stroke-width="1.5" marker-end="url(#a)"/>'

def pth(d, arrow=True):
    m = ' marker-end="url(#a)"' if arrow else ""
    return f'<path d="{d}" fill="none" stroke="{A}" stroke-width="1.5"{m}/>'

def label(x, y, t):
    return f'<text x="{x}" y="{y}" text-anchor="middle" font-family="{FONT}" font-size="12" fill="#5F5E5A">{t}</text>'

def render(svg, name):
    cairosvg.svg2png(bytestring=svg.encode(), write_to=name, scale=3); print("wrote", name)

# 1. End-to-end flow ---------------------------------------------------------
s = head(600)
s += box(190, 30, 300, 56, "1. Borrower data (JSON)", "Ratios, trend, facility, analyst note", "gray")
s += ln(340, 88, 340, 118)
s += box(190, 122, 300, 56, "2. Jev: System One", "P(repay), main risk, risk grade", "purple")
s += pth("M340 180 L340 196", False)
s += box(40, 214, 280, 56, "3. Challenger scorecard", "Second opinion on PD", "gray")
s += box(360, 214, 280, 56, "4. Policy rules", "Leverage and interest cover limits", "gray")
s += pth("M340 196 L180 196 L180 210") + pth("M340 196 L500 196 L500 210")
s += pth("M180 272 L180 292 L340 292 L340 306") + pth("M500 272 L500 292 L340 292", False)
s += box(190, 310, 300, 56, "5. Decision engine", "PD bands + overrides", "teal")
s += ln(340, 368, 340, 398)
s += box(190, 402, 300, 56, "6. Tiny LLM: System Two", "Drafts narrative, no figures", "purple")
s += ln(340, 460, 340, 490)
s += box(190, 494, 300, 56, "7. Credit committee decides", "Memo + audit log", "coral")
s += "</svg>"
render(s, "guide_flow.png")

# 2. Decision rules ----------------------------------------------------------
s = head(560)
s += box(210, 30, 260, 56, "PD = 1 − P(repay)", "From Jev's can_repay answer", "purple")
s += pth("M340 88 L340 104 L120 104 L120 118") + pth("M340 88 L340 118") + pth("M340 104 L560 104 L560 118")
s += box(40, 122, 160, 56, "PD below 3%", "APPROVE", "green")
s += box(260, 122, 160, 56, "PD 3% to 10%", "REFER", "amber")
s += box(480, 122, 160, 56, "PD above 10%", "DECLINE", "red")
s += pth("M120 180 L120 210 L340 210 L340 226") + pth("M560 180 L560 210 L340 210", False) + pth("M340 180 L340 210", False)
s += box(170, 230, 340, 56, "Check 1: policy limit breached?", "Yes, and APPROVE: change to REFER", "teal")
s += ln(340, 288, 340, 318)
s += box(170, 322, 340, 56, "Check 2: models disagree?", "Gap over 10 points: change to REFER", "teal")
s += ln(340, 380, 340, 410)
s += box(170, 414, 340, 56, "Final recommendation", "APPROVE, REFER or DECLINE", "coral")
s += ln(340, 472, 340, 502)
s += box(210, 506, 260, 44, "Credit committee decides", "", "gray")
s += "</svg>"
render(s, "guide_rules.png")

# 3. Calibration chart -------------------------------------------------------
m = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "metrics.json"))
cal = m["calibration"]
labels = [c[0] for c in cal]; pred = [c[2] * 100 for c in cal]; real = [c[3] * 100 for c in cal]
fig, ax = plt.subplots(figsize=(7, 3.6), dpi=200)
xs = range(len(labels))
ax.bar([x - 0.2 for x in xs], pred, 0.38, label="Predicted PD (average)", color="#7F77DD")
ax.bar([x + 0.2 for x in xs], real, 0.38, label="Actually defaulted", color="#1D9E75")
for x, p, r in zip(xs, pred, real):
    ax.text(x - 0.2, p + 0.8, f"{p:.1f}%", ha="center", fontsize=7, color="#3C3489")
    ax.text(x + 0.2, r + 0.8, f"{r:.1f}%", ha="center", fontsize=7, color="#085041")
ax.set_xticks(list(xs)); ax.set_xticklabels([f"PD {l}" for l in labels], fontsize=8)
ax.set_ylabel("Default rate (%)", fontsize=8); ax.tick_params(axis="y", labelsize=8)
ax.spines[["top", "right"]].set_visible(False); ax.legend(fontsize=8, frameon=False)
ax.set_title("Calibration check: does a predicted PD match what really happened?", fontsize=9)
fig.tight_layout(); fig.savefig("guide_calibration.png"); print("wrote guide_calibration.png")
