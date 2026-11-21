"""Prepare the supplied diagrams (architecture, data flow, E-R) for the report and slides:
remove the title header, repaint a small corner watermark, trim the white border.
Usage: python docs/project/prep_diagrams.py <folder with the three PNGs>   -> figures/diagram_*.png"""
import os
import sys

import numpy as np
from PIL import Image

SRC = sys.argv[1]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")


def load(name):
    im = Image.open(os.path.join(SRC, name)).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return np.array(Image.alpha_composite(bg, im).convert("RGB"))


def dark_rows(a, y_max, thr=110):
    lum = a[:y_max].astype(float).mean(axis=2)
    return np.where((lum < thr).sum(axis=1) > 3)[0]


def erase_header(a):
    """The title is the first block of dark text rows; whiten everything above the first gap after it."""
    rows = dark_rows(a, 400)
    start = rows[0]
    end = start
    for r in rows[1:]:
        if r - end > 40:     # a real gap after the title
            break
        end = r
    a[: end + 25] = 255
    return end


def trim(a, margin=36):
    mask = a.min(axis=2) < 232
    ys, xs = np.where(mask)
    y0, y1, x0, x1 = max(ys.min() - margin, 0), min(ys.max() + margin, a.shape[0]), max(xs.min() - margin, 0), min(xs.max() + margin, a.shape[1])
    return a[y0:y1, x0:x1]


def save(a, name, max_w=1800):
    im = Image.fromarray(a)
    if im.width > max_w:   # plenty for a 16 cm wide figure and a full-width slide, keeps the files small
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    im.save(os.path.join(OUT, name), optimize=True)
    print(name, im.width, "x", im.height)


# --- architecture: star watermark straddling the pale box edge (x~2658) and the teal band ---
a = load("architecture_diagram.png")
print("arch title ends at row", erase_header(a))
x0, x1, y0, y1, edge = 2575, 2693, 1365, 1485, 2658
teal = np.median(a[1250:1310, 2664:2692].reshape(-1, 3), axis=0).astype(np.uint8)   # clean patch of the teal band above the star
for y in range(y0, y1):
    a[y, x0:edge] = a[y, x0 - 10]
    a[y, edge:x1] = teal
save(trim(a), "diagram_architecture.png")

# --- data flow: a small light tip on the bottom edge of the D4 box; copy the row colours from the left neighbour ---
b = load("data_flow_diagram.png")
print("dfd title ends at row", erase_header(b))
for y in range(1362, 1418):
    b[y, 2605:2680] = b[y, 2592]
save(trim(b), "diagram_dataflow.png")

# --- E-R: header only ---
c = load("er_diagram.png")
c[:172] = 255   # the title ends near row ~160; the first table starts at ~185 (auto-detection merges them, so fixed here)
save(trim(c), "diagram_er.png")
