"""Map of the eight evaluation regions (groups of whole IMD sub-divisions), from the saved region map
ml-service/qc/assets/client_map.json (the real map, not a mock-up). Output: figures/fig_region_map.png"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"
SRC = HERE.parents[1] / "ml-service" / "qc" / "assets" / "client_map.json"
DARK = "#222222"

d = json.load(open(SRC))
grid = np.array([[int(c) for c in row] for row in d["rows"]])
lat = 6.5 + 0.25 * np.arange(grid.shape[0])
lon = 66.5 + 0.25 * np.arange(grid.shape[1])
fig, ax = plt.subplots(figsize=(6.2, 6.4), dpi=200)
colors = ["#4c78a8", "#f58518", "#e45756", "#72b7b2", "#54a24b", "#b279a2", "#9d755d", "#eeca3b"]
ax.pcolormesh(lon, lat, np.ma.masked_equal(grid, 0), cmap=ListedColormap(colors), vmin=0.5, vmax=8.5)
for c in range(1, 9):
    ys, xs = np.nonzero(grid == c)
    ax.text(lon[int(xs.mean())], lat[int(ys.mean())], str(c), ha="center", va="center", fontsize=13, fontweight="bold",
            color="white" if c != 8 else DARK)
for c in (3, 6):
    ax.contour(lon, lat, (grid == c).astype(float), levels=[0.5], colors=[DARK], linewidths=1.6, linestyles="--")
ax.set_xlabel("Longitude (degrees E)")
ax.set_ylabel("Latitude (degrees N)")
ax.set_title("Eight evaluation regions over India\n(groups of whole IMD sub-divisions; dashed = held-out regions 3 and 6)", fontsize=10)
ax.set_aspect("equal")
fig.tight_layout()
fig.savefig(OUT / "fig_region_map.png")
print("saved")
