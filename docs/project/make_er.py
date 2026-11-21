"""Entity-relationship diagram of the DataMend run store, drawn from backend/app/validation/models.py (the real tables, keys and
foreign keys). Output: figures/diagram_er_corrected.png

Solid line = foreign key (ON DELETE CASCADE). Dashed line = logical link through row_ref, NOT a database constraint.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures", "diagram_er_corrected.png")
NAVY, TEAL, AMBER, PURPLE, GREY, INK = "#1F3A5F", "#1F7A8C", "#B7791F", "#6B4C9A", "#4A5563", "#16202B"
RH, HH = 0.27, 0.38

fig, ax = plt.subplots(figsize=(15.4, 9.3))
ax.set_xlim(0, 15.4); ax.set_ylim(0, 9.3); ax.axis("off")
plt.rcParams["font.family"] = "DejaVu Sans"

TABLES = {}


def table(key, x, top, w, title, rows, color):
    """rows: (badge, name, type); badge in PK, FK, '' ; a row with name starting '...' is a note."""
    h = HH + len(rows) * RH
    ax.add_patch(Rectangle((x, top - h), w, h, fc="white", ec=color, lw=1.6, zorder=2))
    ax.add_patch(Rectangle((x, top - HH), w, HH, fc=color, ec=color, zorder=3))
    ax.text(x + w / 2, top - HH / 2, title, ha="center", va="center", color="white", fontsize=10.5, fontweight="bold", zorder=4)
    ys = {}
    for i, (badge, name, typ) in enumerate(rows):
        yc = top - HH - (i + 0.5) * RH
        ys[name] = yc
        if name.startswith("..."):
            ax.text(x + 0.14, yc, name, ha="left", va="center", fontsize=8, style="italic", color=GREY, zorder=4)
            continue
        if badge:
            ax.text(x + 0.12, yc, badge, ha="left", va="center", fontsize=8, fontweight="bold",
                    color={"PK": AMBER, "FK": TEAL}[badge], zorder=4)
        ax.text(x + 0.52, yc, name, ha="left", va="center", fontsize=8.6, fontweight="bold", color=INK, zorder=4)
        ax.text(x + w - 0.12, yc, typ, ha="right", va="center", fontsize=8, color=GREY, zorder=4)
    TABLES[key] = dict(x=x, top=top, w=w, h=h, ys=ys)
    return TABLES[key]


def one(p, v, color):
    """Exactly-one marker (double bar) at start point p, direction v pointing away from the entity."""
    nx, ny = -v[1], v[0]
    for d in (0.16, 0.25):
        cx, cy = p[0] + v[0] * d, p[1] + v[1] * d
        ax.plot([cx - nx * 0.1, cx + nx * 0.1], [cy - ny * 0.1, cy + ny * 0.1], color=color, lw=1.5, zorder=5)


def many(p, u, color):
    """Zero-or-many marker (circle + crow's foot) at end point p, direction u pointing INTO the entity."""
    nx, ny = -u[1], u[0]
    base = (p[0] - u[0] * 0.24, p[1] - u[1] * 0.24)
    for s in (-0.09, 0.0, 0.09):
        ax.plot([base[0], p[0] + nx * s], [base[1], p[1] + ny * s], color=color, lw=1.5, zorder=5)
    c = (p[0] - u[0] * 0.35, p[1] - u[1] * 0.35)
    ax.add_patch(Circle(c, 0.065, fc="white", ec=color, lw=1.4, zorder=6))


def path(pts, color=GREY, dashed=False):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=color, lw=1.5, ls=(0, (5, 3)) if dashed else "-", zorder=1, solid_capstyle="butt")


def unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = (dx * dx + dy * dy) ** 0.5
    return (dx / n, dy / n)


def link(pts, color=GREY, dashed=False, bar=True):
    path(pts, color, dashed)
    if bar:   # the one-end sits on the parent table; the branches that leave the shared bus have no bar of their own
        one(pts[0], unit(pts[0], pts[1]), color)
    many(pts[-1], unit(pts[-2], pts[-1]), color)


# ---- tables (columns taken from models.py; "more columns" rows say how many are left out) ---------------------------------
R = table("runs", 0.35, 7.6, 3.5, "validation_runs", [
    ("PK", "id", "int"), ("", "created_at", "datetime"), ("", "profile", "reading | daily"), ("", "source", "upload | live"),
    ("", "input_sha256", "string"), ("", "settings", "json"), ("", "platform_version", "string"), ("", "git_commit", "string"),
    ("", "not_run", "json"), ("", "... 11 more columns", "")], NAVY)
S = table("results", 5.6, 8.6, 4.0, "validation_results", [
    ("PK", "id", "int"), ("FK", "run_id", "int"), ("", "row_ref", "string"), ("", "station_id", "string"), ("", "time_key", "string, null"),
    ("", "verdict", "string"), ("", "rule_score", "float"), ("", "severity", "string, null"),
    ("", "original_row", "json"), ("", "... 5 more columns", "")], NAVY)
H = table("hits", 11.2, 8.6, 3.8, "validation_check_hits", [
    ("PK", "id", "int"), ("FK", "run_id", "int"), ("FK", "result_id", "int"), ("", "check", "string"), ("", "layer", "string"),
    ("", "kind", "string"), ("", "weight", "float"), ("", "reason", "text"), ("", "evidence", "json")], TEAL)
E = table("expl", 5.6, 4.4, 4.0, "explanations", [
    ("PK", "id", "int"), ("FK", "run_id", "int"), ("", "row_ref", "string, null"), ("", "check", "string, null"),
    ("", "kind", "explain | chat"), ("", "text", "text"), ("", "generator", "string"), ("", "model_id", "string"),
    ("", "generated", "bool"), ("", "... 5 more columns", "")], AMBER)
V = table("reviews", 11.2, 4.4, 3.8, "reviews", [
    ("PK", "id", "int"), ("FK", "run_id", "int"), ("", "row_ref", "string"), ("", "station_id", "string"), ("", "decision", "string"),
    ("", "note", "text, null"), ("", "reviewer", "string, null"), ("", "verdict_at_review", "string"), ("", "created_at", "datetime")], PURPLE)

rx = R["x"] + R["w"]                       # right edge of validation_runs
y_id = R["ys"]["id"]
bus_x = 4.7
# shared start segment from validation_runs.id
path([(rx, y_id), (bus_x, y_id)], NAVY)
one((rx, y_id), (1, 0), NAVY)
# runs -> results
link([(bus_x, y_id), (bus_x, S["ys"]["run_id"]), (S["x"], S["ys"]["run_id"])], NAVY, bar=False)
# runs -> explanations
link([(bus_x, y_id), (bus_x, E["ys"]["run_id"]), (E["x"], E["ys"]["run_id"])], AMBER, bar=False)
# runs -> check_hits (over the top of results)
link([(bus_x, y_id), (bus_x, 9.05), (10.55, 9.05), (10.55, H["ys"]["run_id"]), (H["x"], H["ys"]["run_id"])], TEAL, bar=False)
# runs -> reviews (underneath explanations)
link([(bus_x, E["ys"]["run_id"]), (bus_x, 0.8), (10.55, 0.8), (10.55, V["ys"]["run_id"]), (V["x"], V["ys"]["run_id"])], PURPLE, bar=False)
# results -> check_hits (FK result_id)
link([(S["x"] + S["w"], S["ys"]["id"]), (10.2, S["ys"]["id"]), (10.2, H["ys"]["result_id"]), (H["x"], H["ys"]["result_id"])], TEAL)
# results ..> explanations and results ..> reviews: logical link through row_ref, dashed (no foreign key)
link([(7.6, S["top"] - S["h"]), (7.6, E["top"])], AMBER, dashed=True)
link([(9.2, S["top"] - S["h"]), (9.2, 5.0), (V["x"] + V["w"] / 2, 5.0), (V["x"] + V["w"] / 2, V["top"])], PURPLE, dashed=True)

# labels
ax.text(7.75, 4.95, "row_ref (logical)", fontsize=7.6, style="italic", color=AMBER, va="center")
ax.text(10.0, 5.17, "row_ref (logical)", fontsize=7.6, style="italic", color=PURPLE, va="center")
ax.text(4.8, 8.15, "run_id", fontsize=7.6, style="italic", color=NAVY, va="center")
ax.text(9.8, 8.32, "result_id", fontsize=7.6, style="italic", color=TEAL, va="center")

fig.savefig(OUT, dpi=170, bbox_inches="tight", pad_inches=0.1, facecolor="white")
print("saved", OUT)
