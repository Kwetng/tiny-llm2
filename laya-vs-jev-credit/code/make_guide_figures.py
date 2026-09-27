"""Draws the explanatory figure for the guide (no results in it)."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BLUE, ORANGE, INK, MUTED, LINE, BG = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#c9c8c3", "#fcfcfb"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "img")
os.makedirs(OUT, exist_ok=True)

fig, ax = plt.subplots(figsize=(10, 4.6)); fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
ax.set_xlim(0, 101); ax.set_ylim(0, 46); ax.axis("off")


def box(x, y, w, h, title, sub, edge=LINE, fill="#ffffff"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fill, ec=edge, lw=1.6))
    ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center", fontsize=10, color=INK, weight="bold")
    ax.text(x + w / 2, y + h * 0.30, sub, ha="center", va="center", fontsize=7.8, color=MUTED, linespacing=1.3)


def arrow(x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.3))


box(1, 17, 17, 12, "Same borrower", "400 hold-out borrowers:\nratios, trends, note\n(JSON)")
box(1, 2, 17, 11, "Same questions", "can_repay (noul)\nmain_risk (choice)\nrisk_grade (score)")
box(24, 27, 20, 13, "Jev", "TypeSafe AI · closed\ncloud API · data leaves\nthe bank", edge=BLUE)
box(24, 6, 20, 13, "Laya", "Convai · Apache-2.0\nruns on our machine\ndata stays in-house", edge=ORANGE)
box(50, 17, 15, 12, "Normalise", "one answer format\n(Laya grades are\n0-based)")
box(68.5, 17, 13, 12, "Recalibrate", "2 numbers fitted\non 600 labelled\nborrowers")
box(85, 17, 15, 12, "Compare", "ranking, calibration,\ndecisions, agreement,\nspeed, data location")
box(50, 0.5, 35, 11, "Same policy engine + challenger", "PD < 3% approve · 3-10% refer · > 10% decline\npolicy limits · refer if models disagree by > 10 pts")
for yy in (23, 7.5):
    arrow(18.8, yy, 23.2, 33.5); arrow(18.8, yy, 23.2, 12.5)
arrow(44.8, 33.5, 49.2, 25); arrow(44.8, 12.5, 49.2, 21)
arrow(65.8, 23, 67.8, 23); arrow(82.3, 23, 84.3, 23)
arrow(75, 16.2, 72, 12.3)
ax.text(50, 44.5, "Only the model changes: everything else is byte-identical", ha="center", fontsize=11, color=INK)
fig.savefig(os.path.join(OUT, "harness.png"), dpi=170, bbox_inches="tight", facecolor=BG)
print("wrote docs/img/harness.png")
