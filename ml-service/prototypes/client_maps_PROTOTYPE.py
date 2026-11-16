"""PROTOTYPE - throwaway. Question: what should a federated client be on the RF25 grid?

Draws three candidate client maps (8 clients each) with per-client statistics, to react to.
  python prototypes/client_maps_PROTOTYPE.py <data_dir> <out_png>
Statistics use training-range years only (2000-2016). Not production code; no tests.
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from scipy.ndimage import label
from sklearn.cluster import KMeans

sys.path.insert(0, ".")
from training.data import RainfallArchive

K = 8
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
YEARS = range(2000, 2017)
INK, MUTED, SURFACE = "#1a1a19", "#6b6a63", "#ffffff"

arch = RainfallArchive(sys.argv[1])
land = arch.land_mask
H, W = land.shape
rows, cols = np.nonzero(land)
lat, lon = arch.lat[rows], arch.lon[cols]

# per-cell statistics from train-range years
month_tot = np.zeros((12, H, W)); ann, wet, days, jjas = (np.zeros((H, W)) for _ in range(4))
wet_vals = []
for y in YEARS:
    c = arch.load(y)[:365]
    c0 = np.nan_to_num(c)
    m = (np.arange(365) // 30.42).astype(int).clip(0, 11)
    for k in range(12):
        month_tot[k] += c0[m == k].sum(0)
    ann += c0.sum(0); wet += (c0 > 0.1).sum(0); days += np.isfinite(c).sum(0)
    jjas += c0[151:273].sum(0)
    wet_vals.append(np.where(c > 0.1, c, np.nan))
n = len(YEARS)
ann_mean = ann / n
p99 = np.nanpercentile(np.concatenate(wet_vals), 99, axis=0)
frac = (month_tot / np.maximum(month_tot.sum(0), 1e-6))[:, rows, cols].T          # (cells, 12) seasonal shape
z = lambda a: (a - a.mean()) / a.std()


def relabel_west_to_east(lab):
    """Stable ids: order clients by centroid (north to south, then west to east) so colour follows place."""
    order = sorted(range(K), key=lambda k: (-round(lat[lab == k].mean() / 4), lon[lab == k].mean()))
    out = np.empty_like(lab)
    for new, old in enumerate(order):
        out[lab == old] = new
    return out


def tiles():
    lab = np.zeros(lat.size, int)
    bands = np.quantile(lat, [0.25, 0.5, 0.75])
    b = np.searchsorted(bands, lat)
    for i in range(4):
        sel = b == i
        lab[sel] = i * 2 + (lon[sel] > np.median(lon[sel]))
    return lab


def regimes():
    X = np.column_stack([frac * 6, z(np.log1p(ann_mean[rows, cols])) * 1.5, z(lat) * 0.7, z(lon) * 0.7])
    ok = ann_mean[rows, cols] > 1.0          # a few land cells carry no rain at all in these years; attach them by position
    km = KMeans(K, n_init=10, random_state=0).fit(X[ok])
    lab = np.empty(lat.size, int); lab[ok] = km.labels_
    for i in np.nonzero(~ok)[0]:
        lab[i] = lab[ok][np.argmin((lat[ok] - lat[i]) ** 2 + (lon[ok] - lon[i]) ** 2)]
    print("zero-rain land cells:", int((~ok).sum()))
    return lab


def blobs():
    return KMeans(K, n_init=10, random_state=0).fit_predict(np.column_stack([lat, lon]))


CANDS = [("A. Equal-count lat/lon tiles", tiles()), ("B. Rainfall-regime clusters", regimes()),
         ("C. Geographic blobs (lat/lon k-means)", blobs())]

fig, axes = plt.subplots(2, 3, figsize=(19, 11), gridspec_kw={"height_ratios": [1.7, 1]}, facecolor=SURFACE)
extent = [arch.lon.min(), arch.lon.max(), arch.lat.min(), arch.lat.max()]
print_rows = []
for j, (name, lab) in enumerate(CANDS):
    lab = relabel_west_to_east(lab)
    grid = np.full((H, W), np.nan); grid[rows, cols] = lab
    ax = axes[0, j]
    ax.imshow(grid, origin="lower", extent=extent, cmap=ListedColormap(PALETTE), vmin=-0.5, vmax=K - 0.5, interpolation="nearest")
    ax.set_title(name, color=INK, fontsize=14, loc="left", pad=10)
    ax.set_xlabel("longitude", color=MUTED); ax.set_ylabel("latitude", color=MUTED)
    ax.tick_params(colors=MUTED); [s.set_visible(False) for s in ax.spines.values()]
    table = []
    for k in range(K):
        sel = lab == k
        r, c = rows[sel], cols[sel]
        piece = np.zeros((H, W), bool); piece[r, c] = True
        ncomp = label(piece, structure=np.ones((3, 3)))[1]
        ax.text(lon[sel].mean(), lat[sel].mean(), str(k + 1), color=INK, fontsize=13, fontweight="bold", ha="center", va="center",
                bbox=dict(boxstyle="circle,pad=0.25", fc=SURFACE, ec=PALETTE[k], lw=2))
        row = [str(k + 1), int(sel.sum()), f"{ann_mean[r, c].mean():.0f}", f"{100 * (wet[r, c] / np.maximum(days[r, c], 1)).mean():.0f}%",
               f"{100 * (jjas[r, c].sum() / max(ann[r, c].sum(), 1e-6)):.0f}%", f"{np.nanmean(p99[r, c]):.0f}", ncomp]
        table.append(row)
        print_rows.append([name[:1]] + row)
    t = axes[1, j]; t.axis("off")
    tb = t.table(cellText=table, colLabels=["client", "cells", "mm / yr", "wet days", "Jun-Sep", "p99 mm", "pieces"],
                 loc="upper center", cellLoc="right")
    tb.auto_set_font_size(False); tb.set_fontsize(10.5); tb.scale(1, 1.55)
    for (ri, ci), cell in tb.get_celld().items():
        cell.set_edgecolor("#e4e3de"); cell.get_text().set_color(INK if ri else MUTED)
        if ri and ci == 0:
            cell.set_facecolor(PALETTE[ri - 1]); cell.get_text().set_color(SURFACE); cell.get_text().set_fontweight("bold")
    cells = np.array([r[1] for r in table]); annual = np.array([float(r[2]) for r in table])
    foot = chr(10).join([f"cells per client: {cells.min()}-{cells.max()}", f"annual rain across clients: {annual.min():.0f}-{annual.max():.0f} mm",
                      f"clients in more than one piece: {sum(r[6] > 1 for r in table)} of {K}"])
    t.text(0.5, -0.12, foot, transform=t.transAxes, ha="center", va="top", color=MUTED, fontsize=10.5)
fig.suptitle("PROTOTYPE: candidate federated clients on the RF25 grid (8 clients, statistics from 2000-2016)", color=INK, fontsize=15, x=0.02, ha="left")
plt.tight_layout(rect=(0, 0, 1, 0.97))
plt.savefig(sys.argv[2], dpi=110, facecolor=SURFACE)
for r in print_rows:
    print(*r, sep="\t")
