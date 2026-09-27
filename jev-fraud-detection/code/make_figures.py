"""make_figures.py - diagrams and charts for the Jev + mini LLM fraud documentation.

Run from the jev-fraud-detection folder after fraud_jev_llm.py has written example_outputs/:
    python code/make_figures.py
"""
import json, os
import cairosvg
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

OUT = "diagrams"
os.makedirs(OUT, exist_ok=True)
M = json.load(open("example_outputs/metrics.json"))

C = {"gray": ("#F1EFE8", "#5F5E5A", "#444441", "#5F5E5A"), "purple": ("#EEEDFE", "#534AB7", "#3C3489", "#534AB7"),
     "teal": ("#E1F5EE", "#0F6E56", "#085041", "#0F6E56"), "coral": ("#FAECE7", "#993C1D", "#712B13", "#993C1D"),
     "green": ("#EAF3DE", "#3B6D11", "#27500A", "#3B6D11"), "amber": ("#FAEEDA", "#854F0B", "#633806", "#854F0B"),
     "red": ("#FCEBEB", "#A32D2D", "#791F1F", "#A32D2D")}
A, FONT = "#888780", "DejaVu Sans"

def head(h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="680" height="{h}" viewBox="0 0 680 {h}"><rect width="680" height="{h}" fill="#FFFFFF"/>'
            f'<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M2 1L8 5L2 9" fill="none" stroke="{A}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>')

def box(x, y, w, h, title, sub, col):
    f, s, tc, sc = C[col]; cx = x + w / 2
    o = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{f}" stroke="{s}" stroke-width="0.8"/>'
    if sub:
        o += f'<text x="{cx}" y="{y+h/2-10}" text-anchor="middle" dominant-baseline="central" font-family="{FONT}" font-size="14" font-weight="bold" fill="{tc}">{title}</text>'
        o += f'<text x="{cx}" y="{y+h/2+10}" text-anchor="middle" dominant-baseline="central" font-family="{FONT}" font-size="12" fill="{sc}">{sub}</text>'
    else:
        o += f'<text x="{cx}" y="{y+h/2}" text-anchor="middle" dominant-baseline="central" font-family="{FONT}" font-size="14" font-weight="bold" fill="{tc}">{title}</text>'
    return o

def path(d, arrow=True):
    return f'<path d="{d}" fill="none" stroke="{A}" stroke-width="1.5"{" marker-end=" + chr(34) + "url(#a)" + chr(34) if arrow else ""}/>'

def render(svg, name):
    cairosvg.svg2png(bytestring=svg.encode(), write_to=os.path.join(OUT, name), scale=3); print("wrote", name)

# 1. System flow -------------------------------------------------------------
s = head(560)
s += box(170, 30, 340, 56, "Transaction arrives", "Amount, description, device, payee", "gray")
s += path("M340 88 L340 104 L165 104 L165 118") + path("M340 104 L515 104 L515 118")
s += box(40, 122, 250, 56, "Jev: System One", "P(fraud) and fraud type", "purple")
s += box(390, 122, 250, 56, "Mini LLM", "Surprise of the description", "purple")
s += path("M515 180 L515 210")
s += box(390, 214, 250, 56, "Challenger model", "Trees on behaviour + surprise", "gray")
s += path("M165 180 L165 316 L250 316 L250 330") + path("M515 272 L515 316 L430 316 L430 330")
s += box(170, 334, 340, 56, "Decision engine", "Hard rules, risk bands, overrides", "teal")
s += path("M340 392 L340 422")
s += box(170, 426, 340, 56, "ALLOW / STEP-UP / HOLD / BLOCK", "Plus reason codes and audit log", "coral")
s += path("M340 484 L340 504")
s += box(170, 508, 340, 40, "Analyst or customer confirms", "", "gray")
s += "</svg>"
render(s, "fraud_flow.png")

# 2. Action ladder -----------------------------------------------------------
cut = M["thresholds"]
s = head(390)
s += box(190, 30, 300, 56, "Combined risk", "Average of Jev and challenger", "teal")
s += path("M340 88 L340 104 L100 104 L100 118") + path("M340 104 L260 104 L260 118", True) + path("M340 104 L420 104 L420 118") + path("M340 104 L580 104 L580 118")
s += box(30, 122, 140, 56, "ALLOW", f"below {cut['STEP-UP']:.0%}", "green")
s += box(190, 122, 140, 56, "STEP-UP", f"{cut['STEP-UP']:.0%} to {cut['HOLD']:.0%}", "amber")
s += box(350, 122, 140, 56, "HOLD", f"{cut['HOLD']:.0%} to {cut['BLOCK']:.0%}", "coral")
s += box(510, 122, 140, 56, "BLOCK", f"{cut['BLOCK']:.0%} and above", "red")
s += path("M100 180 L100 200 L340 200 L340 214") + path("M260 180 L260 200", False) + path("M420 180 L420 200", False) + path("M580 180 L580 200 L340 200", False)
s += box(130, 218, 420, 56, "Overrides can only raise the action", "Mule list, card testing, LLM surprise, one model very sure", "teal")
s += path("M340 276 L340 306")
s += box(40, 310, 290, 56, "Customer sees", "Confirm in app, or scam warning", "gray")
s += box(350, 310, 290, 56, "Analyst sees", "Case file with reason codes", "gray")
s += path("M340 276 L340 290 L185 290 L185 306") + path("M340 290 L495 290 L495 306")
s += "</svg>"
render(s, "fraud_actions.png")

# 3. Charts ------------------------------------------------------------------
BLUE, GREY, INK, INK2 = "#2a78d6", "#c9c7bf", "#0b0b0b", "#52514e"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": "#d6d4cc", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2})

def hbar(labels, values, fmt, title, name, highlight, xlabel):
    fig, ax = plt.subplots(figsize=(7, 0.45 * len(labels) + 1.0), dpi=220)
    ys = range(len(labels))[::-1]
    cols = [BLUE if i in highlight else GREY for i in range(len(labels))]
    ax.barh(list(ys), values, color=cols, height=0.62)
    for y_, v in zip(ys, values):
        ax.text(v + max(values) * 0.01, y_, fmt(v), va="center", fontsize=7.5, color=INK)
    ax.set_yticks(list(ys)); ax.set_yticklabels(labels, fontsize=8, color=INK)
    ax.set_xlabel(xlabel); ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="x", color="#eeede8", lw=0.6); ax.set_axisbelow(True)
    ax.set_xlim(0, max(values) * 1.15)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}" if max(values) > 10 else f"{v:.1f}")); ax.set_title(title, fontsize=9, color=INK, loc="left")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, name)); plt.close(fig); print("wrote", name)

biz = M["business"]
names = list(biz)
hbar([n.replace("Full design: ", "Full design:\n") for n in names], [biz[n]["total_cost_gbp"] for n in names],
     lambda v: f"£{v:,.0f}", "Total cost on 9,600 test transactions (fraud lost + customer friction)", "chart_cost.png",
     {len(names) - 1}, "£")
rk = M["ranking"]
rn = list(rk)
hbar(rn, [rk[n]["pr_auc"] for n in rn], lambda v: f"{v:.2f}", "PR-AUC: how well each score ranks fraud above genuine (1.0 = perfect)",
     "chart_prauc.png", {rn.index("Challenger + mini LLM surprise")}, "PR-AUC")
