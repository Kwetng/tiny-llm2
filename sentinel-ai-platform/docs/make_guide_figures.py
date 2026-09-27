"""Figures for the Sentinel Word guide (request pipeline and path to production).

    python docs/make_guide_figures.py     # writes docs/img/*.png
"""
from pathlib import Path
import cairosvg

OUT = Path(__file__).resolve().parent / "img"
OUT.mkdir(exist_ok=True)
C = {"gray": ("#F1EFE8", "#5F5E5A", "#444441", "#5F5E5A"), "purple": ("#EEEDFE", "#534AB7", "#3C3489", "#534AB7"),
     "teal": ("#E1F5EE", "#0F6E56", "#085041", "#0F6E56"), "coral": ("#FAECE7", "#993C1D", "#712B13", "#993C1D"),
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
        o += f'<text x="{cx}" y="{y + h / 2 - 9}" text-anchor="middle" dominant-baseline="central" font-family="{FONT}" font-size="14" font-weight="bold" fill="{tc}">{title}</text>'
        o += f'<text x="{cx}" y="{y + h / 2 + 10}" text-anchor="middle" dominant-baseline="central" font-family="{FONT}" font-size="12" fill="{sc}">{sub}</text>'
    else:
        o += f'<text x="{cx}" y="{y + h / 2}" text-anchor="middle" dominant-baseline="central" font-family="{FONT}" font-size="14" font-weight="bold" fill="{tc}">{title}</text>'
    return o


def path(d, arrow=True):
    m = ' marker-end="url(#a)"' if arrow else ""
    return f'<path d="{d}" fill="none" stroke="{A}" stroke-width="1.5"{m}/>'


def label(x, y, t):
    return f'<text x="{x}" y="{y}" text-anchor="start" font-family="{FONT}" font-size="12" fill="#5F5E5A">{t}</text>'


# 1. request pipeline ---------------------------------------------------------
steps = [("1. Who is asking?", "Token checked, rate limit applied", "gray"),
         ("2. Is it an attack?", "Guard blocks prompt injection", "red"),
         ("3. Remove personal data", "Card numbers, emails, accounts", "teal"),
         ("4. Search what you may see", "Access rules applied first", "teal"),
         ("5. Quarantine poisoned text", "Hidden instructions removed", "red"),
         ("6. Ask a model", "Azure OpenAI, Gemini or local", "purple"),
         ("7. Check the citations", "No valid source, no answer", "teal"),
         ("8. Record everything", "Tamper-evident audit log", "gray")]
s = head(40 + len(steps) * 72 + 10)
for i, (t, sub, col) in enumerate(steps):
    y = 30 + i * 72
    s += box(170, y, 340, 54, t, sub, col)
    if i < len(steps) - 1:
        s += path(f"M340 {y + 56} L340 {y + 70}")
s += path("M510 115 L560 115 L560 135", True) + box(530, 139, 120, 36, "Refused", "", "red").replace('font-size="14"', 'font-size="12"')
s += "</svg>"
cairosvg.svg2png(bytestring=s.encode(), write_to=str(OUT / "pipeline.png"), scale=3)

# 2. path to production -------------------------------------------------------
stages = [("Intake", "Register, risk tier, owner", "gray"), ("Design", "Reuse shared services", "gray"),
          ("Build", "Experts add test questions", "purple"), ("Gate", "12 thresholds in CI", "teal"),
          ("Validate", "Model Risk reviews evidence", "teal"), ("Pilot", "Small group, alerts on", "purple"),
          ("Scale", "Monthly monitoring", "coral")]
s = head(40 + len(stages) * 64)
for i, (t, sub, col) in enumerate(stages):
    y = 24 + i * 64
    s += box(190, y, 300, 48, t, sub, col)
    if i < len(stages) - 1:
        s += path(f"M340 {y + 50} L340 {y + 62}")
s += "</svg>"
cairosvg.svg2png(bytestring=s.encode(), write_to=str(OUT / "path_to_production.png"), scale=3)
print("wrote", *[p.name for p in OUT.glob("*.png")])
