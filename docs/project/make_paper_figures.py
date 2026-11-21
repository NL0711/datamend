"""Single-column (3.4 in) figures for the IEEE-format paper. Values are the same measured numbers as make_figures.py
(probe_stnet_s42.json, ceiling_stnet.md; SYNTHETIC faults, validation years 2013-2017, seed 42)."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = os.path.join(os.path.dirname(__file__), "figures")
NAVY, TEAL, GREY, AMBER = "#1F3A5F", "#2A7F8E", "#5B6770", "#C98A1B"
plt.rcParams.update({"font.family": "serif", "font.size": 7})


def box(ax, x, y, w, h, text, fc="#E8EEF5", ec=NAVY, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fc, ec=ec, lw=0.9))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=5.5, fontweight="bold" if bold else "normal")


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=7, lw=0.9, color=GREY))


fig, ax = plt.subplots(figsize=(3.45, 2.75))
ax.set_xlim(0, 10); ax.set_ylim(0, 8); ax.axis("off")
ax.text(0, 7.7, "Part A: validation platform", fontsize=7, fontweight="bold", color=NAVY)
box(ax, 0, 5.6, 2.9, 1.5, "Input contract\nreject file /\nflag row")
box(ax, 3.55, 5.6, 2.9, 1.5, "Check catalogue\n8 reading + 4 daily\n+ 'not run'")
box(ax, 7.1, 5.6, 2.9, 1.5, "Verdict, score,\nevidence")
arrow(ax, 2.9, 6.35, 3.55, 6.35); arrow(ax, 6.45, 6.35, 7.1, 6.35)
box(ax, 3.55, 3.4, 2.9, 1.4, "Score-provider\nseam (optional)", fc="#FBF1DC", ec=AMBER)
box(ax, 7.1, 3.4, 2.9, 1.4, "Run report +\nexplainer")
arrow(ax, 5.0, 4.8, 5.0, 5.6); arrow(ax, 8.55, 5.6, 8.55, 4.8)
ax.text(0, 2.75, "Part B: model system (RF25 grid)", fontsize=7, fontweight="bold", color=TEAL)
box(ax, 0, 0.5, 2.9, 1.7, "Time splits,\nsynthetic fault\nbenchmark", ec=TEAL, fc="#E4F2F4")
box(ax, 3.55, 0.5, 2.9, 1.7, "STNet\nCNN + ConvGRU\n3 heads", ec=TEAL, fc="#E4F2F4", bold=True)
box(ax, 7.1, 0.5, 2.9, 1.7, "Fusion with rules\nat a fixed\nbudget", ec=TEAL, fc="#E4F2F4")
arrow(ax, 2.9, 1.35, 3.55, 1.35); arrow(ax, 6.45, 1.35, 7.1, 1.35)
arrow(ax, 8.55, 2.2, 5.6, 3.4)
fig.savefig(os.path.join(OUT, "pp_architecture.png"), dpi=300, bbox_inches="tight")
plt.close(fig)

kinds = ["Spike", "Phantom", "Stuck", "Scale", "Drift", "Zeroed"]
auc = [0.9988, 0.9874, 0.9750, 0.9381, 0.8948, 0.8885]
fig, ax = plt.subplots(figsize=(3.45, 2.0))
b = ax.bar(kinds, auc, color=TEAL, width=0.6)
ax.set_ylim(0.8, 1.02); ax.set_ylabel("AUC")
for r, v in zip(b, auc):
    ax.text(r.get_x() + r.get_width() / 2, v + 0.004, f"{v:.3f}", ha="center", fontsize=6)
ax.spines[["top", "right"]].set_visible(False)
fig.savefig(os.path.join(OUT, "pp_probe_auc.png"), dpi=300, bbox_inches="tight")
plt.close(fig)

labels = ["<0.1", "0.1-1", "1-5", "5-20", "20-100", ">100"]
rec = [0.427, 0.567, 0.687, 0.794, 0.885, 0.896]
fig, ax = plt.subplots(figsize=(3.45, 2.0))
ax.plot(labels, rec, marker="o", ms=3.5, color=NAVY, lw=1.4)
for x, v in zip(labels, rec):
    ax.text(x, v + 0.03, f"{v:.2f}", ha="center", fontsize=6)
ax.set_ylim(0.3, 1.0); ax.set_xlabel("change in rainfall caused by the fault (mm)"); ax.set_ylabel("recall at 1 / 1,000")
ax.spines[["top", "right"]].set_visible(False)
fig.savefig(os.path.join(OUT, "pp_recall_vs_size.png"), dpi=300, bbox_inches="tight")
plt.close(fig)
print("paper figures written")
