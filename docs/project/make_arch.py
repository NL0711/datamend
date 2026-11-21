"""Architecture diagram of DataMend (inputs, Part A validation platform, Part B model system).
One wide figure used in the report, the slides and the LaTeX paper (figure*). Output: figures/fig_architecture.png and .pdf"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
NAVY, TEAL, AMBER, INK, GREY = "#1F3A5F", "#1F7A8C", "#B7791F", "#1B2733", "#5B6770"
FILL = {"in": "#F1F4F8", "a": "#E3ECF7", "b": "#DDF0F2", "seam": "#FBEFD5", "side": "#FFFFFF"}
EDGE = {"in": GREY, "a": NAVY, "b": TEAL, "seam": AMBER, "side": NAVY}
plt.rcParams.update({"font.family": "serif"})

W, H = 22.0, 13.6
fig, ax = plt.subplots(figsize=(9.0, 5.55))
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")


def lane(y0, y1, tab, title, color, left=False):
    ax.add_patch(FancyBboxPatch((0.15, y0), W - 0.3, y1 - y0, boxstyle="round,pad=0,rounding_size=0.35", fc="#FAFBFC", ec="#D5DBE3", lw=0.8))
    ax.add_patch(FancyBboxPatch((0.15, y0), 1.15, y1 - y0, boxstyle="round,pad=0,rounding_size=0.35", fc=color, ec=color, lw=0))
    ax.text(0.72, (y0 + y1) / 2, tab, rotation=90, ha="center", va="center", fontsize=8, fontweight="bold", color="white")
    if left:
        ax.text(1.75, y1 - 0.42, title, ha="left", va="center", fontsize=7, fontweight="bold", color=color)
    else:
        ax.text(W - 0.55, y1 - 0.42, title, ha="right", va="center", fontsize=7, fontweight="bold", color=color)


def box(x, y, w, h, title, sub, kind):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.3", fc=FILL[kind], ec=EDGE[kind], lw=1.1))
    ax.text(x + w / 2, y + h - 0.38, title, ha="center", va="top", fontsize=7.8, fontweight="bold", color=INK)
    for i, s in enumerate(sub):
        ax.text(x + w / 2, y + h - 1.05 - i * 0.62, s, ha="center", va="top", fontsize=6.4, color="#37424F")


def arrow(x1, y1, x2, y2, color=GREY, lw=1.2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=9, lw=lw, color=color, shrinkA=0, shrinkB=0))


def line(xs, ys, color=GREY, lw=1.2):
    ax.plot(xs, ys, color=color, lw=lw, solid_capstyle="butt")


# lanes
lane(10.35, 13.4, "IN", "DATA SOURCES", GREY)
lane(4.35, 10.05, "A", "PART A: VALIDATION PLATFORM (FastAPI + React)", NAVY)
lane(0.2, 4.05, "B", "PART B: MODEL SYSTEM (ml-service, IMD RF25 grid)", TEAL, left=True)

X = [1.9, 7.1, 12.3, 17.5]
WA = 4.3
WL = 4.0

# inputs
IY, IH = 10.6, 2.0
box(X[0], IY, WA, IH, "File upload", ["CSV / JSON", "optional station metadata"], "in")
box(X[1], IY, WA, IH, "Live gauge feed", ["Weather Union", "580 gauges"], "in")
box(X[2], IY, WA, IH, "Gridded rainfall", ["IMD RF25", "0.25 degree, daily"], "in")

# part A, row 1
YA, HA = 6.9, 2.3
box(X[0], YA, WA, HA, "Input contract", ["profile, units, time zone", "reject file / flag row"], "a")
box(X[1], YA, WA, HA, "Check catalogue", ["8 reading + 4 daily checks", "explicit ‘not run’"], "a")
box(X[2], YA, WA, HA, "Verdict + evidence", ["verdict for every reading", "rule score, severity"], "a")
box(X[3], YA, WL, HA, "Run store", ["SQLite, JSON and", "CSV export"], "a")
for i in range(3):
    arrow(X[i] + WA, YA + HA / 2, X[i + 1], YA + HA / 2)
# inputs -> contract (elbow bus)
cx = X[0] + WA / 2
arrow(cx, IY, cx, YA + HA)
line([X[1] + WA / 2, X[1] + WA / 2, cx], [IY, 10.2, 10.2])
line([X[2] + WA / 2, X[2] + WA / 2], [IY, 10.2])
line([cx, X[2] + WA / 2], [10.2, 10.2])
ax.plot([cx], [10.2], marker="o", ms=3, color=GREY)

# part A, row 2
YB, HB = 4.65, 1.7
box(X[1], YB, WA, HB, "Score-provider seam", ["optional trained score"], "seam")
box(X[2], YB, WA, HB, "Explainer", ["baseline | AI narrator"], "side")
box(X[3], YB, WL, HB, "Dashboard", ["review loop, exports"], "side")
arrow(X[1] + WA / 2, YB + HB, X[1] + WA / 2, YA, color=AMBER)
arrow(X[2] + WA / 2, YA, X[2] + WA / 2, YB + HB, color=NAVY)
arrow(X[3] + WL / 2, YA, X[3] + WL / 2, YB + HB, color=NAVY)

# part B
YC, HC = 0.5, 2.3
box(X[0], YC, WA, HC, "RF25 + benchmark", ["time splits, 8 regions", "6 synthetic fault kinds"], "b")
box(X[1], YC, WA, HC, "STNet", ["CNN + ConvGRU", "fault / clean / disc heads"], "b")
box(X[2], YC, WA, HC, "Fusion + budget", ["with rules, 1 false alarm", "per 1,000 clean cell-days"], "b")
box(X[3], YC, WL, HC, "Regional report", ["IMD sub-divisions"], "b")
for i in range(3):
    arrow(X[i] + (WA), YC + HC / 2, X[i + 1], YC + HC / 2, color=TEAL)
# calibrated score -> seam (elbow)
sx = X[1] + WA / 2
fx = X[2] + WA / 2
line([fx, fx, sx], [YC + HC, 4.2, 4.2], color=AMBER)
arrow(sx, 4.2, sx, YB, color=AMBER)
ax.text(fx + 0.3, 3.45, "calibrated score", ha="left", va="center", fontsize=6.2, style="italic", color=AMBER)

fig.savefig(os.path.join(OUT, "fig_architecture.png"), dpi=300, bbox_inches="tight", pad_inches=0.04)
fig.savefig(os.path.join(OUT, "fig_architecture.pdf"), bbox_inches="tight", pad_inches=0.04)
print("saved")
