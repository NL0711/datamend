"""Figures for the seminar report and presentation.

fig_client_map.png  : the real 8-client map saved in ml-service/qc/assets/client_map.json (not a mock-up).
fig_federated.png   : diagram of the federated training round used in ml-service/qc/federated.py.
fig_pipeline.png    : diagram of the four score components and the fusion layer (docs/qc-system-spec.md, sections 6-7).
Run:  python docs/seminar/make_figures.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"
OUT.mkdir(exist_ok=True)
CMAP_JSON = HERE.parents[1] / "ml-service" / "qc" / "assets" / "client_map.json"

BLUE, TEAL, AMBER, GREY, RED, DARK = "#1f4e79", "#2a9d8f", "#e9a23b", "#8d99ae", "#c0392b", "#222222"


def client_map():
    d = json.load(open(CMAP_JSON))
    grid = np.array([[int(c) for c in row] for row in d["rows"]])
    lat = 6.5 + 0.25 * np.arange(grid.shape[0])
    lon = 66.5 + 0.25 * np.arange(grid.shape[1])
    fig, ax = plt.subplots(figsize=(6.2, 6.4), dpi=200)
    colors = ["#ffffff", "#4c78a8", "#f58518", "#e45756", "#72b7b2", "#54a24b", "#b279a2", "#9d755d", "#eeca3b"]
    from matplotlib.colors import ListedColormap
    ax.pcolormesh(lon, lat, np.ma.masked_equal(grid, 0), cmap=ListedColormap(colors[1:9]), vmin=0.5, vmax=8.5)
    for c in range(1, 9):
        ys, xs = np.nonzero(grid == c)
        ax.text(lon[int(xs.mean())], lat[int(ys.mean())], str(c), ha="center", va="center", fontsize=13, fontweight="bold",
                color="white" if c not in (8,) else DARK)
    for c in (3, 6):
        ys, xs = np.nonzero(grid == c)
        ax.contour(lon, lat, (grid == c).astype(float), levels=[0.5], colors=[DARK], linewidths=1.6, linestyles="--")
    ax.set_xlabel("Longitude (degrees E)"); ax.set_ylabel("Latitude (degrees N)")
    ax.set_title("Eight federated clients over India\n(groups of whole IMD sub-divisions; dashed = held-out clients 3 and 6)", fontsize=10)
    ax.set_aspect("equal")
    fig.tight_layout(); fig.savefig(OUT / "fig_client_map.png"); plt.close(fig)


def box(ax, xy, w, h, text, fc, ec=DARK, fs=9, tc="white", bold=False):
    ax.add_patch(FancyBboxPatch(xy, w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=fc, ec=ec, lw=1.2))
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center", fontsize=fs, color=tc, fontweight="bold" if bold else "normal")


def arrow(ax, a, b, color=DARK, style="-|>", ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=12, lw=1.3, color=color, linestyle=ls, connectionstyle=f"arc3,rad={rad}"))


def federated():
    fig, ax = plt.subplots(figsize=(8.4, 4.6), dpi=200)
    ax.set_xlim(0, 10); ax.set_ylim(0, 5.6); ax.axis("off")
    box(ax, (3.6, 4.1), 2.8, 1.0, "Server\naverages the shared body\n(weighted by cells)", BLUE, fs=9.5, bold=True)
    xs = [0.2, 1.85, 3.5, 5.15, 6.8, 8.45]
    for i, x in enumerate(xs):
        box(ax, (x, 1.35), 1.35, 1.45, f"Client {[1,2,4,5,7,8][i]}\nlocal data only\nlocal head\nlocal scaling", TEAL, fs=7.8)
        arrow(ax, (x + 0.67, 2.85), (5.0, 4.05), color=GREY, rad=0.12 if x < 4.5 else -0.12)
    ax.text(5.0, 3.35, "1. each client trains one local epoch, sends body weights", ha="center", fontsize=8.5, color=DARK)
    ax.text(5.0, 3.05, "2. server averages the body and sends it back (the head stays local)", ha="center", fontsize=8.5, color=DARK)
    box(ax, (1.2, 0.1), 3.0, 0.75, "Held-out client 3 (north-east)\nunseen: gets body + mean of heads", AMBER, fs=8, tc=DARK)
    box(ax, (5.8, 0.1), 3.0, 0.75, "Held-out client 6 (west-central)\nunseen: gets body + mean of heads", AMBER, fs=8, tc=DARK)
    ax.set_title("One federated round (FedPers variant) - simulated sequentially on one machine, no privacy claim", fontsize=9.5)
    fig.tight_layout(); fig.savefig(OUT / "fig_federated.png"); plt.close(fig)


def pipeline():
    fig, ax = plt.subplots(figsize=(8.4, 4.0), dpi=200)
    ax.set_xlim(0, 10); ax.set_ylim(0, 5); ax.axis("off")
    box(ax, (0.1, 1.9), 1.5, 1.2, "Daily rainfall\nfield (one\ncell-day)", GREY, fs=9)
    comps = [("Spatial (trained)\nsame-day neighbours,\nhidden disc removed", BLUE), ("Temporal (trained)\nown previous 30 days,\none-direction GRU", BLUE),
             ("Slow (untrained)\n30/90-day totals vs\nclimatology", TEAL), ("Rules (untrained)\nphysical and\nstep checks", TEAL)]
    for i, (t, c) in enumerate(comps):
        y = 4.0 - i * 1.15
        box(ax, (2.4, y - 0.4), 2.9, 0.95, t, c, fs=8)
        arrow(ax, (1.6, 2.5), (2.4, y + 0.07), color=GREY)
        arrow(ax, (5.3, y + 0.07), (6.2, 2.5), color=GREY)
    box(ax, (6.2, 1.85), 1.7, 1.3, "Fusion\nlogistic regression\non four scores", AMBER, fs=8.5, tc=DARK, bold=True)
    arrow(ax, (7.9, 2.5), (8.5, 2.5))
    box(ax, (8.5, 1.9), 1.4, 1.2, "Final flag\nReview flag\n(fixed false-\nalarm budgets)", RED, fs=7.8)
    ax.set_title("Four evidence components fused into one score (DataMend rainfall QC)", fontsize=9.5)
    fig.tight_layout(); fig.savefig(OUT / "fig_pipeline.png"); plt.close(fig)


if __name__ == "__main__":
    client_map(); federated(); pipeline()
    print("wrote", sorted(p.name for p in OUT.iterdir()))
