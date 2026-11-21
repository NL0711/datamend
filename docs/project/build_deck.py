"""Builds the project presentation from the college 'Presentation format.pptx' (title slide, outline, content slides).
Usage: python docs/project/build_deck.py <template.pptx> <out.pptx>
Numbers are the same as in the report (content.js); fault results are on SYNTHETIC faults."""
import copy
import os
import sys
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Emu, Pt, Inches
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
DATE = "20-11-2026"
TITLE = "AI-Based Time Series Weather Data Validation Platform"
BLUE = RGBColor(0x2F, 0x55, 0x97)
PALE = RGBColor(0xE9, 0xEE, 0xF7)
INK = RGBColor(0x22, 0x2B, 0x38)

prs = Presentation(sys.argv[1])
slides = list(prs.slides)
title_slide, outline = slides[0], slides[1]


def set_runs(par, text, size=None, bold=None):
    """Replace a paragraph's text keeping the first run's formatting."""
    runs = par.runs
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r._r.getparent().remove(r._r)
        r0 = runs[0]
    else:
        r0 = par.add_run(); r0.text = text
    if size: r0.font.size = Pt(size)
    if bold is not None: r0.font.bold = bold
    return r0


def set_date(sh):
    """The date may be a text run or a date field; set the visible text either way."""
    ts = list(sh._element.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t"))
    ts[0].text = DATE
    for t in ts[1:]:
        t.text = ""


# ---- slide 1 (title) -------------------------------------------------------------------------------------------
for sh in title_slide.shapes:
    if sh.name == "Title 1":
        tf = sh.text_frame
        p = tf.paragraphs[0]
        # runs: line-break, "Course Seminar ISE-2 Evaluation ", line-break, "(Seminar Title )"
        for r in p.runs:
            if "Seminar ISE-2" in r.text: r.text = "Major Project Evaluation "
            elif "Seminar Title" in r.text: r.text = TITLE
    elif sh.name == "Content Placeholder 2":
        p = sh.text_frame.paragraphs[0]
        set_runs(p, "Nathasha Lewis (10257)  -  Anshu Jadhav (10247)  -  Rochelle Fernandes (10245)", size=20)
        for q in p.runs[1:]: pass
    elif sh.name == "Content Placeholder 3":
        keep = ["Under the Guidance ", "of ", "Dr. Sujuta Deshmukh", "Professor", "Department of Computer Engineering", ""]
        for par in sh.text_frame.paragraphs:
            if par.text.startswith("Dr. Sujuta"):
                set_runs(par, "Prof. Jagruti Nagaonkar")
            elif par.text.strip() == "Professor":
                par._p.getparent().remove(par._p)  # designation not provided: remove the line
    elif sh.name == "Date Placeholder 5":
        set_date(sh)

for sh in outline.shapes:
    if sh.name == "Date Placeholder 3":
        set_date(sh)

layout = outline.slide_layout


def new_slide(title):
    s = prs.slides.add_slide(layout)
    for sh in list(s.shapes):
        sh._element.getparent().remove(sh._element)
    for sh in outline.shapes:
        s.shapes._spTree.append(copy.deepcopy(sh._element))
    for sh in s.shapes:
        if sh.name == "Title 1":
            sh.text_frame.paragraphs[0].runs[0].text = title
            for r in sh.text_frame.paragraphs[0].runs[1:]:
                r._r.getparent().remove(r._r)
        elif sh.name == "Slide Number Placeholder 5":
            pass
    return s


def body_of(s):
    return next(sh for sh in s.shapes if sh.name == "Content Placeholder 8")


def bullets(s, items, size=20, left=None, width=None, top=None, height=None):
    b = body_of(s)
    if left is not None: b.left = Emu(left)
    if width is not None: b.width = Emu(width)
    if top is not None: b.top = Emu(top)
    if height is not None: b.height = Emu(height)
    tf = b.text_frame
    tf.word_wrap = True
    pars = tf.paragraphs
    proto = copy.deepcopy(pars[0]._p)
    for p in pars:
        p._p.getparent().remove(p._p)
    for t in items:
        np_ = copy.deepcopy(proto)
        tf._txBody.append(np_)
    for p, t in zip(tf.paragraphs, items):
        for r in p.runs[1:]:
            r._r.getparent().remove(r._r)
        r0 = p.runs[0]
        r0.text = t
        r0.font.size = Pt(size)
        p.space_after = Pt(8)
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", "285750"); pPr.set("indent", "-285750")
        for old in pPr.findall(A + "buNone") + pPr.findall(A + "buChar"):
            pPr.remove(old)
        bu = pPr.makeelement(A + "buChar", {"char": "•"})
        pPr.append(bu)
    return b


def remove_body(s):
    b = body_of(s)
    b._element.getparent().remove(b._element)


def picture(s, name, left, top, max_w, max_h):
    path = os.path.join(FIG, name)
    w, h = Image.open(path).size
    sc = min(max_w / w, max_h / h)
    pw, ph = int(w * sc), int(h * sc)
    s.shapes.add_picture(path, Emu(left + (max_w - pw) // 2), Emu(top + (max_h - ph) // 2), Emu(pw), Emu(ph))


def table(s, head, rows, left, top, width, col_w, size=14, row_h=370000):
    n = len(rows) + 1
    gs = s.shapes.add_table(n, len(head), Emu(left), Emu(top), Emu(width), Emu(row_h * n))
    t = gs.table
    tot = sum(col_w)
    for i, w in enumerate(col_w):
        t.columns[i].width = Emu(int(width * w / tot))
    for r in range(n):
        t.rows[r].height = Emu(row_h)
        for c in range(len(head)):
            cell = t.cell(r, c)
            cell.text = head[c] if r == 0 else rows[r - 1][c]
            cell.margin_left = cell.margin_right = Emu(70000)
            cell.margin_top = cell.margin_bottom = Emu(35000)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            for run in p.runs:
                run.font.size = Pt(size)
                run.font.bold = (r == 0)
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF) if r == 0 else INK
            cell.fill.solid()
            cell.fill.fore_color.rgb = BLUE if r == 0 else (PALE if r % 2 == 0 else RGBColor(0xFF, 0xFF, 0xFF))
    return t


def stat(s, left, top, w, h, big, small):
    from pptx.enum.shapes import MSO_SHAPE
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(left), Emu(top), Emu(w), Emu(h))
    box.fill.solid(); box.fill.fore_color.rgb = PALE; box.line.fill.background(); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = big; r.font.size = Pt(30); r.font.bold = True; r.font.color.rgb = BLUE
    p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run(); r2.text = small; r2.font.size = Pt(14); r2.font.color.rgb = INK


def caption(s, left, top, w, text):
    tb = s.shapes.add_textbox(Emu(left), Emu(top), Emu(w), Emu(300000))
    tb.text_frame.word_wrap = True
    p = tb.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = text; r.font.size = Pt(12); r.font.italic = True; r.font.color.rgb = RGBColor(0x55, 0x5F, 0x6B)


A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
L = 838200; W = 10515600; T = 1117600; H = 5059363
HALF = 5200000

# 3 Abstract
s = new_slide("Abstract")
bullets(s, [
    "Rainfall records drive flood warning, agriculture and climate work, yet every record contains faulty values: stuck gauges, spikes, scaling errors, phantom rain",
    "DataMend validates a rainfall series layer by layer and returns a verdict for every reading with the evidence behind it",
    "Rule engine (8 reading + 4 daily checks) plus STNet, a spatio-temporal network trained on the IMD RF25 grid",
    "At one false alarm per 1,000 clean cell-days: PR-AUC 0.69, recall 0.64, only 0.6% of protected extremes flagged",
    "FastAPI backend, React dashboard, live gauge feed, 569 automated tests",
], size=20)

# 4 Introduction
s = new_slide("Introduction")
bullets(s, [
    "Rain is zero on most days and highly skewed on the rest: one wrong value can change a flood model or an advisory",
    "Quality control (QC) must catch faults without erasing genuine extremes",
    "Objective: one reproducible platform that takes a rainfall series from any source, explains every flag and keeps a record",
    "Part A: validation platform. Part B: trained model system (STNet)",
], size=20, width=6300000)
stat(s, 7400000, 1300000, 1900000, 1300000, "569", "automated tests")
stat(s, 9500000, 1300000, 1900000, 1300000, "6", "fault families")
stat(s, 7400000, 2850000, 1900000, 1300000, "1.76M", "STNet parameters")
stat(s, 9500000, 2850000, 1900000, 1300000, "1,121", "gauges and stations mapped")
caption(s, 7400000, 4250000, 4000000, "580 Weather Union gauges + 541 Indian synoptic stations")

# 5 Literature survey
s = new_slide("Literature Survey / Existing System References")
bullets(s, [
    "Rule-based QA of GHCN-Daily: duplicate, outlier, persistence and spatial tests; 0.24% of 1.5 billion values flagged [6]",
    "Anomaly detection survey: sequence and reconstruction models [5], LSTM [12], GRU [13], ConvLSTM for gridded fields [18]",
    "CNN precipitation QC on gridded fields: AUC 0.927 [10]",
    "Federated detection for sensor faults, forecasting and time-series benchmarks [7]-[9]",
    "Data: IMD RF25 0.25-degree grid [11]; Weather Union gauges [16]; NOAA ISD station list [17]",
], size=20)

# 6 Comparative study
s = new_slide("Comparative Study of Technical Papers")
remove_body(s)
table(s, ["Approach", "Strength", "Typical limitation", "How DataMend builds on it"], [
    ["Rule-based QA [6]", "Transparent, cheap", "Hand-set thresholds", "Rule catalogue with declared needs and explicit 'not run'"],
    ["CNN precipitation QC [10]", "Uses spatial context", "Single region, centralised", "Spatial encoder over the national grid, regional clients"],
    ["Recurrent models [12], [13], [18]", "Temporal memory", "Accuracy-style scores", "ConvGRU memory, fixed false-alarm budget"],
    ["Federated detection [7]-[9]", "Data stays with holders", "Non-rainfall or non-spatial", "Eight regional clients, held-out regions"],
], L, 1400000, W, [2.6, 2.2, 2.4, 3.6], size=16, row_h=800000)

# 7 Framework
s = new_slide("Framework: Architecture of DataMend")
remove_body(s)
picture(s, "fig_architecture.png", L, 1000000, W, 4850000)
caption(s, L, 5850000, W, "Part A: validation platform (FastAPI + React). Part B: model system on the RF25 grid (STNet).")

# 8 Design details: modules
s = new_slide("Design Details: Platform Modules")
remove_body(s)
table(s, ["Module", "Role"], [
    ["Input contract", "CSV / JSON, reading or daily profile; reject the file or flag the row"],
    ["Check catalogue", "8 reading + 4 daily checks; verdict, rule score, tagged evidence"],
    ["Runs and reports", "Input hash, settings, version; JSON and CSV export"],
    ["Evidence and explainers", "evidence-v1 contract; rule-based baseline or AI narrator"],
    ["Live feed and places", "Weather Union gauges; grid cell, land / sea, region lookup"],
    ["Review loop and lab", "Reviewer decisions kept apart; seeded synthetic faults"],
    ["Dashboard", "Overview, Runs, Explorer, Review queue, Station network, Settings"],
], L, 1300000, W, [2.6, 7.4], size=16, row_h=590000)

# 9 Design details: data flow and storage
s = new_slide("Design Details: Data Flow and Storage")
bullets(s, [
    "Input contract creates Reading or DailyTotal records; the original row stays untouched",
    "Catalogue emits verdicts; checks that cannot run are listed as 'not run'",
    "Run service stores results and builds a report from measured numbers only",
    "Explainer reads stored evidence; text is stored apart and marked generated",
    "Reviewer decisions never change a verdict or score",
], size=18, width=5300000)
table(s, ["Table", "Content"], [
    ["validation_runs", "Run id, input hash, settings, version"],
    ["validation_results", "Row, verdict, rule score, severity"],
    ["validation_check_hits", "Fired check and its evidence"],
    ["explanations", "Generated text, explainer name"],
    ["reviews", "Decision, note, reviewer label"],
], 6400000, 1300000, 5100000, [2.4, 3.2], size=14, row_h=620000)
caption(s, 6400000, 5150000, 5100000, "SQLite now, written so it can move to PostgreSQL")

# 10 Methodology
s = new_slide("Methodology: Data, Benchmark and STNet")
bullets(s, [
    "IMD RF25 daily grid, split by time: train earlier, validate later, score test years once",
    "8 regional clients from whole IMD sub-divisions; clients 3 and 6 held out",
    "Frozen benchmark: 6 fault families; protected extremes are never corrupted",
    "STNet: CNN encoder + ConvGRU memory; fault, clean and discrimination heads",
    "Trained in 9,172 s on one T4 GPU; 6.8 MB; 8.2 GFLOPs per day over the full grid",
], size=18, width=6300000)
picture(s, "fig_client_map.png", 7400000, 1250000, 4100000, 4400000)
caption(s, 7400000, 5650000, 4100000, "Eight regional clients (dashed: held out)")

# 11 Proposal
s = new_slide("Proposed Solution: Layered Validation")
bullets(s, [
    "Deterministic checks first, then one robust statistic and a neighbour check",
    "Optional trained score enters through a defined score-provider seam",
    "Verdict always carries its evidence; magnitude alone is never a fault",
    "Rule score and calibrated flag are kept separate and never blended",
    "Fusion with the rules at a fixed budget of 1 false alarm per 1,000 clean cell-days",
    "Budgets are fixed on validation data; test years are scored once",
], size=20)

# 12 Results figures
s = new_slide("Results: Fault Separability and Detection")
remove_body(s)
picture(s, "fig_probe_auc.png", L, 1300000, 5100000, 3300000)
picture(s, "fig_recall_vs_size.png", L + 5400000, 1300000, 5100000, 3300000)
caption(s, L, 4750000, 5100000, "AUC from 0.888 to 0.999 across six fault families")
caption(s, L + 5400000, 4750000, 5100000, "Recall reaches 0.885 for changes of 20-100 mm")
caption(s, L, 5250000, W, "SYNTHETIC faults, held-out validation years 2013-2017, seed 42")

# 13 Results table
s = new_slide("Results: Fused Operating Point")
body_keep = None
table(s, ["Variant", "PR-AUC", "Recall", "Event recall", "False / 1,000", "Protected flagged"], [
    ["Rules + fault head (logistic)", "0.691", "0.635", "0.619", "1.27", "0.6%"],
    ["Rules + fault head (boosted)", "0.682", "0.629", "0.573", "0.73", "2.7%"],
    ["Rules + fault + clean heads", "0.693", "0.636", "0.608", "1.24", "1.9%"],
    ["Rules + four STNet heads", "0.707", "0.644", "0.637", "1.38", "2.3%"],
], L, 1300000, W, [3.6, 1.2, 1.2, 1.5, 1.6, 1.9], size=16, row_h=560000)
bullets(s, [
    "Budget: 1 false alarm per 1,000 clean cell-days; synthetic faults, validation years",
    "Longer-memory encoder: recall +3.4 points, PR-AUC +2.1 points, better in 5 of 5 years",
    "Strong faults (5 mm or more, wide footprint): recall 0.778",
], size=18, top=4350000, height=1800000)

# 14 Testing
s = new_slide("System Testing")
bullets(s, [
    "239 platform tests and 330 model-system tests on generated data and mocked transports",
    "Unit: input contract, every check, scoring, evidence builder, explainers, settings, place lookup",
    "Integration: upload to checks to storage to API, live feed, narrator client, review loop",
    "Acceptance: anomaly lab, every injected fault flagged across 3 seeds and both profiles",
    "Edge cases: empty file, missing columns, duplicates, frozen and extreme values",
], size=20)

# 15 Conclusion
s = new_slide("Conclusion")
bullets(s, [
    "A complete, reproducible rainfall validation platform with an explainable check catalogue and honest 'not run' reporting",
    "STNet is compact (1.76M parameters), trains in 2.5 hours on one GPU and separates six fault families",
    "Works at a stated false-alarm budget while protecting genuine extremes",
    "Contribution: layered validation, extreme-versus-fault discrimination, evidence behind every flag and a frozen evaluation",
], size=20)

# 16 Future scope
s = new_slide("Future Scope")
bullets(s, [
    "Connect the trained score to the platform and score live gauges against grid neighbours",
    "Evaluate on expert-reviewed labels for Indian stations; three-seed training",
    "Connect the AI narrator; add PDF export, Parquet input and accounts",
    "NOAA ISD India replay and IMD sub-division lookup",
    "Federated variants and the phone-based rain-gauge prototype with real clients",
], size=20)

# 17 References
s = new_slide("References")
bullets(s, [
    "[1] B. McMahan et al., \"Communication-efficient learning of deep networks from decentralized data,\" AISTATS, 2017",
    "[5] V. Chandola, A. Banerjee, V. Kumar, \"Anomaly detection: A survey,\" ACM Computing Surveys, 2009",
    "[6] I. Durre et al., \"Comprehensive automated quality assurance of daily surface observations,\" J. Appl. Meteorol. Climatol., 2010",
    "[7] R. Khan, U. Saeed, I. Koo, \"FedLSTM,\" Electronics, vol. 13, 2024",
    "[10] Y. Sha et al., \"Deep-learning-based precipitation observation quality control,\" J. Atmos. Ocean. Technol., 2021",
    "[11] D. S. Pai et al., \"0.25 x 0.25 degree daily gridded rainfall data set over India,\" MAUSAM, 2014",
    "[18] X. Shi et al., \"Convolutional LSTM network,\" NeurIPS, 2015",
    "Full list of 18 references: see the project report",
], size=14)

# 18 Additional information
s = new_slide("Additional Information")
bullets(s, [
    "Publications: none",
    "Certifications: none",
    "Additional documents: project report, source code (backend, frontend, model system), evaluation protocol, result tables",
    "Thank you. Questions?",
], size=20)

# ---- slide numbers: the copied number placeholders hold a field; refresh the visible text to the position -------
for i, sl in enumerate(prs.slides, 1):
    for sh in sl.shapes:
        if sh.name.startswith("Slide Number"):
            for r in sh.text_frame.paragraphs[0]._p.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t"):
                r.text = str(i)

prs.save(sys.argv[2])
print("saved", sys.argv[2], len(prs.slides), "slides")
