"""Put the corrected E-R diagram on the E-R slide and make the table-names slide match the real columns.
Usage: python docs/project/update_er_slide.py <in.pptx> <out.pptx>"""
import os
import sys

from PIL import Image
from pptx import Presentation
from pptx.util import Emu

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "figures", "diagram_er_corrected.png")
L, T, W, H = 838200, 1000000, 10515600, 4750000
NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

prs = Presentation(sys.argv[1])


def title_of(s):
    return next(sh for sh in s.shapes if sh.name.startswith("Title")).text_frame.text.strip()


def set_text(shape, text):
    ts = list(shape._element.iter(NS + "t"))
    ts[0].text = text
    for t in ts[1:]:
        t.text = ""


for s in prs.slides:
    t = title_of(s)
    if t == "Design Details: E-R Diagram":
        for sh in list(s.shapes):
            if sh.shape_type == 13:
                sh._element.getparent().remove(sh._element)
        w, h = Image.open(IMG).size
        sc = min(W / w, H / h)
        pw, ph = int(w * sc), int(h * sc)
        s.shapes.add_picture(IMG, Emu(L + (W - pw) // 2), Emu(T + (H - ph) // 2), Emu(pw), Emu(ph))
        cap = next((sh for sh in s.shapes if sh.name.startswith("TextBox")), None)
        if cap is None:   # the slide has lost its caption: copy the caption box from the data flow slide
            import copy
            donor = next(x for x in prs.slides if title_of(x) == "Design Details: Data Flow Diagram")
            el = copy.deepcopy(next(sh for sh in donor.shapes if sh.name.startswith("TextBox"))._element)
            s.shapes._spTree.append(el)
            cap = next(sh for sh in s.shapes if sh.name.startswith("TextBox"))
        set_text(cap, "SQLite run store. Solid lines are foreign keys, dashed lines are logical links through row_ref")
    elif t == "Design Details: Data Flow and Storage":
        tbl = next(sh for sh in s.shapes if sh.has_table).table
        rows = {
            "validation_runs": "Input hash, settings, version, report",
            "validation_results": "Row, verdict, rule score, severity",
            "validation_check_hits": "Check, layer, weight, evidence",
            "explanations": "Text, generator, model, kind",
            "reviews": "Decision, note, reviewer",
        }
        for r in range(1, len(tbl.rows)):
            name = tbl.cell(r, 0).text.strip()
            if name in rows:
                cell = tbl.cell(r, 1)
                runs = cell.text_frame.paragraphs[0].runs
                runs[0].text = rows[name]
                for extra in runs[1:]:
                    extra._r.getparent().remove(extra._r)

prs.save(sys.argv[2])
print("saved")
