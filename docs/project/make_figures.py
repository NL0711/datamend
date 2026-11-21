"""Figures for the major project report. Numbers are copied from the committed/downloaded STNet result files
(probe_stnet_s42.json and ceiling_stnet.md, SYNTHETIC faults, validation years 2013-2017, seed 42)."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(OUT, exist_ok=True)
NAVY, TEAL, GREY, AMBER = "#1F3A5F", "#2A7F8E", "#5B6770", "#C98A1B"
plt.rcParams.update({"font.family": "serif", "font.size": 9})


def box(ax, x, y, w, h, text, fc="#E8EEF5", ec=NAVY, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fc, ec=ec, lw=1.1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=6.3, fontweight="bold" if bold else "normal", wrap=True)


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=10, lw=1.1, color=GREY))


# ---- Figure 1: system architecture -------------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(7.2, 4.1))
ax.set_xlim(0, 12); ax.set_ylim(0, 7); ax.axis("off")
ax.text(0.1, 6.75, "Part A: validation platform", fontsize=9.5, fontweight="bold", color=NAVY)
box(ax, 0.1, 5.4, 2.0, 1.0, "Rainfall input\nCSV / JSON upload\nlive gauge feed", fc="#F3F6F9")
box(ax, 2.6, 5.4, 2.2, 1.0, "Input contract\nreject file or\nflag row")
box(ax, 5.3, 5.4, 2.4, 1.0, "Check catalogue\n8 reading + 4 daily\nchecks, explicit 'not run'")
box(ax, 8.2, 5.4, 1.7, 1.0, "Verdict + score\n+ evidence")
box(ax, 10.2, 5.4, 1.7, 1.0, "Run report\nJSON / CSV")
for a, b in [(2.1, 2.6), (4.8, 5.3), (7.7, 8.2), (9.9, 10.2)]:
    arrow(ax, a, 5.9, b, 5.9)
box(ax, 5.3, 3.9, 2.4, 0.9, "Score-provider seam\n(trained score, optional)", fc="#FBF1DC", ec=AMBER)
arrow(ax, 6.5, 4.8, 6.5, 5.4)
box(ax, 8.2, 3.9, 3.7, 0.9, "Explainer interface:\nrule-based baseline | AI narrator", fc="#F3F6F9")
arrow(ax, 9.0, 5.4, 9.5, 4.8)
ax.text(0.1, 3.05, "Part B: model system (ml-service/qc), RF25 0.25-degree grid", fontsize=9.5, fontweight="bold", color=TEAL)
box(ax, 0.1, 1.5, 2.2, 1.1, "RF25 daily grid\ntime-based splits\n8 regional clients", fc="#F3F6F9", ec=TEAL)
box(ax, 2.8, 1.5, 2.2, 1.1, "Synthetic fault\nbenchmark (6 kinds)\n+ protected extremes", ec=TEAL, fc="#E4F2F4")
box(ax, 5.5, 1.5, 2.3, 1.1, "STNet\nCNN + ConvGRU\nfault / clean / disc", ec=TEAL, fc="#E4F2F4", bold=True)
box(ax, 8.3, 1.5, 1.8, 1.1, "Fusion with\nrules + budget\n(1 / 1,000)", ec=TEAL, fc="#E4F2F4")
box(ax, 10.5, 1.5, 1.4, 1.1, "Regional\nIMD report", ec=TEAL, fc="#E4F2F4")
for a, b in [(2.3, 2.8), (5.0, 5.5), (7.8, 8.3), (10.1, 10.5)]:
    arrow(ax, a, 2.05, b, 2.05)
arrow(ax, 9.2, 2.6, 6.9, 3.9)
ax.text(6.0, 0.7, "Evidence is stored with every flag; the narrator never changes a verdict, score or evidence.", ha="center", fontsize=8, style="italic", color=GREY)
fig.savefig(os.path.join(OUT, "fig_architecture.png"), dpi=200, bbox_inches="tight")
plt.close(fig)

# ---- Figure 2: separability by fault kind (probe AUC, next-year test) ----------------------------------------------
kinds = ["Spike", "Phantom\nrain", "Stuck", "Drift", "Scale", "Zeroed"]
auc = [0.9988, 0.9874, 0.9750, 0.8948, 0.9381, 0.8885]
order = [0, 1, 2, 4, 3, 5]
kinds = [kinds[i] for i in order]; auc = [auc[i] for i in order]
fig, ax = plt.subplots(figsize=(5.6, 2.9))
bars = ax.bar(kinds, auc, color=TEAL, width=0.62)
ax.set_ylim(0.8, 1.01); ax.set_ylabel("AUC (fit 2013, test 2014)")
for b, v in zip(bars, auc):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.004, f"{v:.3f}", ha="center", fontsize=8)
ax.spines[["top", "right"]].set_visible(False)
ax.set_title("Linear-probe separability of STNet features (synthetic faults)", fontsize=9)
fig.savefig(os.path.join(OUT, "fig_probe_auc.png"), dpi=200, bbox_inches="tight")
plt.close(fig)

# ---- Figure 3: recall against size of the fault (ceiling check) ----------------------------------------------------
labels = ["<0.1", "0.1-1", "1-5", "5-20", "20-100", ">100"]
rec = [0.427, 0.567, 0.687, 0.794, 0.885, 0.896]
fig, ax = plt.subplots(figsize=(5.6, 2.9))
ax.plot(labels, rec, marker="o", color=NAVY, lw=1.8)
for x, v in zip(labels, rec):
    ax.text(x, v + 0.025, f"{v:.2f}", ha="center", fontsize=8)
ax.set_ylim(0.3, 1.0); ax.set_xlabel("change in rainfall caused by the fault (mm)"); ax.set_ylabel("recall at 1 per 1,000")
ax.spines[["top", "right"]].set_visible(False)
ax.set_title("Detection recall grows with fault size (STNet fault head)", fontsize=9)
fig.savefig(os.path.join(OUT, "fig_recall_vs_size.png"), dpi=200, bbox_inches="tight")
plt.close(fig)
print("figures written to", OUT)
