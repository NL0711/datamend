"""Update the project presentation with the supplied diagrams:
slide 7 gets the new architecture diagram, and two slides (data flow, E-R) are inserted after the modules slide.
Usage: python docs/project/update_deck.py <in.pptx> <out.pptx>"""
import copy
import os
import sys

from PIL import Image
from pptx import Presentation
from pptx.util import Emu

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
L, T, W, H = 838200, 1000000, 10515600, 4750000
NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

prs = Presentation(sys.argv[1])
slides = list(prs.slides)


def find(slide, startswith):
    return next(sh for sh in slide.shapes if sh.name.startswith(startswith))


def place(slide, name):
    path = os.path.join(FIG, name)
    w, h = Image.open(path).size
    sc = min(W / w, H / h)
    pw, ph = int(w * sc), int(h * sc)
    slide.shapes.add_picture(path, Emu(L + (W - pw) // 2), Emu(T + (H - ph) // 2), Emu(pw), Emu(ph))


def set_text(shape, text):
    ts = list(shape._element.iter(NS + "t"))
    ts[0].text = text
    for t in ts[1:]:
        t.text = ""


# ---- slide 7: swap the picture and the caption ------------------------------------------------------------------------
arch = next(s for s in slides if find(s, "Title").text_frame.text.startswith("Framework"))
for sh in list(arch.shapes):
    if sh.shape_type == 13:
        sh._element.getparent().remove(sh._element)
place(arch, "diagram_architecture.png")
set_text(find(arch, "TextBox"), "React frontend, FastAPI backend, external services and offline STNet training")


def new_slide_like(src, title, picture, caption):
    s = prs.slides.add_slide(src.slide_layout)
    for sh in list(s.shapes):
        sh._element.getparent().remove(sh._element)
    for sh in src.shapes:
        if sh.shape_type == 13 or sh.name.startswith("TextBox"):
            continue
        s.shapes._spTree.append(copy.deepcopy(sh._element))
    set_text(find(s, "Title"), title)
    place(s, picture)
    cap = copy.deepcopy(find(src, "TextBox")._element)
    s.shapes._spTree.append(cap)
    set_text(find(s, "TextBox"), caption)
    return s


dfd = new_slide_like(arch, "Design Details: Data Flow Diagram", "diagram_dataflow.png",
                     "Level 1: validation pipeline (top) and explanation and review loop (bottom)")
er = new_slide_like(arch, "Design Details: E-R Diagram", "diagram_er.png",
                    "SQLite run store: runs, results, check hits, explanations and reviews")

# ---- reorder: data flow slide after the modules slide, E-R after "Data Flow and Storage" ---------------------------------
lst = prs.slides._sldIdLst
ids = list(lst)
by_title = {}
for sl, sid in zip(prs.slides, ids):
    by_title[find(sl, "Title").text_frame.text.strip()] = sid
sid_dfd, sid_er = ids[-2], ids[-1]
for e in (sid_dfd, sid_er):
    lst.remove(e)
ids = list(lst)
mod = by_title["Design Details: Platform Modules"]
store = by_title["Design Details: Data Flow and Storage"]
lst.insert(list(lst).index(mod) + 1, sid_dfd)
lst.insert(list(lst).index(store) + 1, sid_er)

# ---- slide numbers follow the new order ------------------------------------------------------------------------------------
for i, sl in enumerate(prs.slides, 1):
    for sh in sl.shapes:
        if sh.name.startswith("Slide Number"):
            ts = list(sh._element.iter(NS + "t"))
            if ts:
                ts[0].text = str(i)

prs.save(sys.argv[2])
print("saved", len(prs.slides), "slides")
