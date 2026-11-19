// Builds Seminar_Presentation.pptx following the 11 presentation sections of the ESE notice (16/11/2026).
// Usage: NODE_PATH=<dir with pptxgenjs> node docs/seminar/build_deck.js
const path = require("path");
const pptxgen = require("pptxgenjs");
const C = require("./content.js");

const FIG = path.join(__dirname, "figures");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
pres.title = C.TITLE;
pres.author = C.STUDENT;

const INK = "10263B", TEAL = "1B6A7A", MINT = "D8EEF0", AMBER = "E9A23B", LIGHT = "F4F8FA", WHITE = "FFFFFF", GREY = "5B6B7A", RED = "B23A48";
const HEAD = "Cambria", BODY = "Calibri";
const W = 13.33, M = 0.6;

function base(title, notes, dark = false) {
  const s = pres.addSlide();
  s.background = { color: dark ? INK : WHITE };
  if (title) s.addText(title, { x: M, y: 0.35, w: W - 2 * M, h: 0.9, fontFace: HEAD, fontSize: 34, bold: true, color: dark ? WHITE : INK, margin: 0, valign: "middle", isTextBox: true });
  if (notes) s.addNotes(notes);
  return s;
}
const foot = (s, n) => s.addText(`Weather Anomaly Detection Using Federated Learning   |   ${n}`, { x: M, y: 7.05, w: W - 2 * M, h: 0.3, fontFace: BODY, fontSize: 10, color: GREY, margin: 0, isTextBox: true });
const card = (s, x, y, w, h, head, text, o = {}) => {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, fill: { color: o.fill || LIGHT }, line: { color: o.line || "D5E1E8", width: 1 }, rectRadius: 0.08 });
  s.addText(head, { x: x + 0.25, y: y + 0.15, w: w - 0.5, h: 0.5, fontFace: HEAD, fontSize: 20, bold: true, color: o.headColor || TEAL, margin: 0, isTextBox: true });
  s.addText(text, { x: x + 0.25, y: y + 0.7, w: w - 0.5, h: h - 0.85, fontFace: BODY, fontSize: o.size || 18, color: o.color || INK, margin: 0, valign: "top", isTextBox: true });
};
const bullets = (items, o = {}) => items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: o.gap ?? 8 } }));
const stat = (s, x, y, w, big, label, color = TEAL) => {
  s.addText(big, { x, y, w, h: 0.9, fontFace: HEAD, fontSize: 44, bold: true, color, margin: 0, align: "left", isTextBox: true });
  s.addText(label, { x, y: y + 0.95, w, h: 1.1, fontFace: BODY, fontSize: 17, color: INK, margin: 0, valign: "top", isTextBox: true });
};
function tableSlide(s, head, rows, cols, y, fs = 13) {
  const hdr = head.map((h) => ({ text: h, options: { bold: true, color: WHITE, fill: { color: TEAL }, fontFace: BODY, fontSize: fs } }));
  const body = rows.map((r) => r.map((t) => ({ text: t, options: { fontFace: BODY, fontSize: fs, color: INK, fill: { color: WHITE } } })));
  s.addTable([hdr, ...body], { x: M, y, w: cols.reduce((a, b) => a + b, 0), colW: cols, border: { type: "solid", color: "C9D6DE", pt: 1 }, margin: [0.06, 0.1, 0.06, 0.1], valign: "middle" });
}

let n = 0;
// 1 ---------------------------------------------------------------- title
{
  const s = base(null, "Introduce the topic: detecting faulty weather observations when the data are spread over different regions. Mention that the work is a survey plus a case study of an implemented system.", true);
  s.addText("Course Seminar, Sem VII  |  25SEM14CE01  |  ESE Presentation", { x: M, y: 0.7, w: 9, h: 0.4, fontFace: BODY, fontSize: 16, color: "9FD0D6", margin: 0, isTextBox: true });
  s.addText(C.TITLE, { x: M, y: 1.7, w: 8.2, h: 2.4, fontFace: HEAD, fontSize: 46, bold: true, color: WHITE, margin: 0, valign: "top", isTextBox: true });
  s.addText([{ text: `${C.STUDENT} (${C.ROLL})`, options: { breakLine: true, bold: true } }, { text: `Guide: ${C.GUIDE}`, options: { breakLine: true } },
    { text: "Department of Computer Engineering", options: { breakLine: true } }, { text: "Fr. Conceicao Rodrigues College of Engineering, Mumbai", options: { breakLine: true } }, { text: "21 November 2026" }],
    { x: M, y: 4.6, w: 8, h: 2, fontFace: BODY, fontSize: 18, color: WHITE, margin: 0, valign: "top", paraSpaceAfter: 6, isTextBox: true });
  s.addImage({ path: path.join(FIG, "fig_client_map.png"), x: 9.0, y: 1.1, w: 3.9, h: 4.03, altText: "Map of India divided into eight federated clients" });
  s.addText("The eight federated clients used in the case study", { x: 9.0, y: 5.25, w: 3.9, h: 0.5, fontFace: BODY, fontSize: 12, italic: true, color: "9FD0D6", margin: 0, isTextBox: true });
}
// 2 ---------------------------------------------------------------- abstract
{
  const s = base("Abstract", "Three sentences: the problem (faulty values and heterogeneous, distributed data), the approach (federated, personalised detector with four evidence components), and the status (implemented and unit-tested, simulation only, no real-data result yet).");
  card(s, M, 1.6, 3.85, 4.9, "The problem", "Weather data contain stuck, spiked and mis-scaled values. Genuine extremes look like errors. Data sit with different agencies and regions, and climate differs between them.");
  card(s, M + 4.05, 1.6, 3.85, 4.9, "The approach", "Federated learning trains a detector across regional clients without pooling raw data. Four evidence components are fused into one score at a fixed false-alarm budget.");
  card(s, M + 8.1, 1.6, 3.83, 4.9, "The status", "Literature surveyed. A case study (rainfall QC over India) is built and unit-tested. Federated training is a one-machine simulation, and no real-data result exists yet.", { fill: "FFF4E0", line: "F0D9A8", headColor: "9A5B00" });
  foot(s, ++n + 1);
}
// 3 ---------------------------------------------------------------- introduction
{
  const s = base("Introduction: three ideas to join", "Anomaly detection finds values that do not fit expected behaviour. Quality control asks whether a value is an error. Federated learning moves the model to the data. The combination is the topic.");
  s.addText(bullets([
    "**Quality control** decides whether an observation is an error.",
    "**Anomaly detection** finds values that do not fit expected behaviour.",
    "**Federated learning** trains one model across data holders by sharing parameters, not raw data.",
  ].map((t) => t.replace(/\*\*/g, ""))), { x: M, y: 1.6, w: 6.2, h: 3.0, fontFace: BODY, fontSize: 20, color: INK, margin: 0, valign: "top", isTextBox: true });
  card(s, 7.2, 1.5, 5.5, 1.7, "An unusual value is not always wrong", "A very heavy rainfall total may be a real storm, so removing every extreme erases the events that matter most.", { size: 15 });
  card(s, 7.2, 3.3, 5.5, 1.7, "Data cannot always be pooled", "Some data may not be redistributed, for example non-US data in NOAA's ISD, and agencies hold their own networks.", { size: 15 });
  card(s, 7.2, 5.1, 5.5, 1.7, "Regions differ", "India spans arid plains, the wet north-east and monsoon coasts, so one average model fits none of them well.", { size: 15 });
  foot(s, ++n + 1);
}
// 4 ---------------------------------------------------------------- need, scope, objectives
{
  const s = base("Need, scope and objectives", "Need: data quality limits every downstream use, and false alarms are costly. Scope: rainfall, survey plus one case study, simulation only. Objectives mirror the report.");
  s.addText("Why it matters", { x: M, y: 1.5, w: 5.7, h: 0.4, fontFace: HEAD, fontSize: 22, bold: true, color: TEAL, margin: 0, isTextBox: true });
  s.addText(bullets(["Forecasts, flood models and climate records inherit observation errors", "Regions are non-IID, which is hard for plain federated averaging", "Every alert needs review, so false alarms must be bounded"], { gap: 10 }),
    { x: M, y: 2.0, w: 5.7, h: 2.2, fontFace: BODY, fontSize: 18, color: INK, margin: 0, valign: "top", isTextBox: true });
  s.addText("Scope", { x: M, y: 4.3, w: 5.7, h: 0.4, fontFace: HEAD, fontSize: 22, bold: true, color: TEAL, margin: 0, isTextBox: true });
  s.addText(bullets(["Daily rainfall; survey plus one implemented case study", "Not a new federated algorithm; simulation, no privacy claim"], { gap: 10 }),
    { x: M, y: 4.8, w: 5.7, h: 1.6, fontFace: BODY, fontSize: 18, color: INK, margin: 0, valign: "top", isTextBox: true });
  s.addShape(pres.ShapeType.roundRect, { x: 6.9, y: 1.5, w: 5.83, h: 5.0, fill: { color: MINT }, line: { color: MINT }, rectRadius: 0.08 });
  s.addText("Objectives", { x: 7.2, y: 1.65, w: 5.2, h: 0.5, fontFace: HEAD, fontSize: 22, bold: true, color: INK, margin: 0, isTextBox: true });
  s.addText([...["Explain anomaly detection and federated learning", "Review conventional, learning-based and federated methods", "Compare published federated approaches", "State the research gap and problem", "Evaluate a concrete framework and its status", "Discuss applications, ethics and SDGs"].map((t, i, a) => ({ text: t, options: { bullet: { type: "number" }, breakLine: i < a.length - 1, paraSpaceAfter: 9 } }))],
    { x: 7.2, y: 2.25, w: 5.2, h: 4.1, fontFace: BODY, fontSize: 18, color: INK, margin: 0, valign: "top", isTextBox: true });
  foot(s, ++n + 1);
}
// 5 ---------------------------------------------------------------- literature survey
{
  const s = base("Literature survey: three generations", "Conventional QC (Durre et al.) is transparent but hand-tuned. Learning-based detectors (Sha et al., recurrent networks) use context. Federated work covers sensor faults (FedLSTM) and forecasting (prompt FL), not rainfall QC.");
  const col = (x, head, sub, items) => {
    s.addShape(pres.ShapeType.roundRect, { x, y: 1.6, w: 3.85, h: 4.9, fill: { color: LIGHT }, line: { color: "D5E1E8", width: 1 }, rectRadius: 0.08 });
    s.addText(head, { x: x + 0.25, y: 1.75, w: 3.35, h: 0.5, fontFace: HEAD, fontSize: 21, bold: true, color: TEAL, margin: 0, isTextBox: true });
    s.addText(sub, { x: x + 0.25, y: 2.25, w: 3.35, h: 0.4, fontFace: BODY, fontSize: 13, italic: true, color: GREY, margin: 0, isTextBox: true });
    s.addText(bullets(items, { gap: 8 }), { x: x + 0.25, y: 2.75, w: 3.35, h: 3.6, fontFace: BODY, fontSize: 17, color: INK, margin: 0, valign: "top", isTextBox: true });
  };
  col(M, "Conventional QC", "Rules and statistics", ["Durre et al. (2010): fixed tests on GHCN-Daily", "Limits, persistence, spatial and cross-element checks", "Transparent, but thresholds set by hand"]);
  col(M + 4.05, "Learning-based", "Context and sequences", ["Sha et al. (2021): CNN on gridded rainfall, AUC 0.927", "LSTM and GRU models of sequences", "Mostly one region, centralised"]);
  col(M + 8.1, "Federated", "Data stay local", ["FedAvg, FedProx, FedPer", "FedLSTM (2024): sensor faults", "Prompt FL (IJCAI 2023): forecasting"]);
  foot(s, ++n + 1);
}
// 6 ---------------------------------------------------------------- comparative study
{
  const s = base("Comparative study of the papers", "The compared works use different data, faults and metrics, so this compares design, not performance. The last row is the case study.");
  tableSlide(s, ["Work", "Task and data", "Method", "Federated", "Main limitation"], [
    ["Durre et al. [6]", "Daily surface QC, GHCN-Daily", "Fixed tests, manual validation", "No", "Hand-set thresholds"],
    ["Sha et al. [10]", "Gauge QC, British Columbia", "CNN ensemble, gridded context", "No", "One region, centralised"],
    ["Khan et al. [7]", "Sensor faults, temperature", "Federated LSTM", "Yes", "Synthetic faults, no spatial context"],
    ["Chen et al. [8]", "Weather forecasting", "Federated transformer, prompts", "Yes", "Forecasting, not QC"],
    ["Liu et al. [9]", "Time-series anomaly benchmark", "5 detectors x 4 FL methods", "Yes", "General series, not weather"],
    ["Case study", "Gridded rainfall QC, India", "4 components + fusion, 4 FL variants", "Yes (simulated)", "No real-data result yet"],
  ], [2.1, 2.9, 3.1, 1.6, 2.43], 1.5, 17);
  foot(s, ++n + 1);
}
// 7 ---------------------------------------------------------------- federated methods
{
  const s = base("Analysis: how federated training works", "FedAvg averages everything weighted by data size. FedProx adds a proximal term against client drift. FedPer keeps the final layer local, which suits regions with different statistics.");
  card(s, M, 1.6, 3.85, 3.4, "FedAvg [1]", "Each client trains locally. The server averages all parameters, weighted by local data size. Works best when clients are alike.");
  card(s, M + 4.05, 1.6, 3.85, 3.4, "FedProx [2]", "FedAvg plus a proximal term that limits how far local training drifts from the global model. Tolerates uneven local work.");
  card(s, M + 8.1, 1.6, 3.83, 3.4, "FedPer [3]", "Shared body is averaged; each client keeps a private final layer trained only on its own data. Our main variant.", { fill: MINT, line: "A8D4D8" });
  s.addText("Non-IID data (regions with different statistics) is the central difficulty [2], [4], [14]. Personalisation is the established response.", { x: M, y: 5.3, w: 12.1, h: 1.0, fontFace: BODY, fontSize: 18, color: INK, margin: 0, valign: "top", isTextBox: true });
  foot(s, ++n + 1);
}
// 8 ---------------------------------------------------------------- gap and problem
{
  const s = base("Research gap and problem statement", "In the sources checked, no federated or personalised rainfall QC, no held-out regions, no explicit extreme protection, no fixed false-alarm budget. A literature search cannot prove absence, so say 'in the sources checked'.");
  s.addText("Gaps in the sources checked", { x: M, y: 1.5, w: 5.8, h: 0.45, fontFace: HEAD, fontSize: 22, bold: true, color: TEAL, margin: 0, isTextBox: true });
  s.addText([...["Federated or personalised learning for rainfall QC", "Evaluation on held-out regions", "Explicit protection of genuine extremes", "A fixed false-alarm budget chosen before testing"].map((t, i, a) => ({ text: t, options: { bullet: { type: "number" }, breakLine: i < a.length - 1, paraSpaceAfter: 12 } }))],
    { x: M, y: 2.1, w: 5.8, h: 3.6, fontFace: BODY, fontSize: 18, color: INK, margin: 0, valign: "top", isTextBox: true });
  s.addShape(pres.ShapeType.roundRect, { x: 6.9, y: 1.5, w: 5.83, h: 5.0, fill: { color: INK }, line: { color: INK }, rectRadius: 0.08 });
  s.addText("Problem statement", { x: 7.2, y: 1.7, w: 5.2, h: 0.5, fontFace: HEAD, fontSize: 22, bold: true, color: AMBER, margin: 0, isTextBox: true });
  s.addText("Given daily rainfall on a 0.25-degree grid over India, split into regional clients whose raw data stay local, build a detector that scores each cell-day for contamination, flags faults at a fixed false-alarm budget, keeps genuine heavy rain, and compare federated, personalised, local-only and centralised training, including on unseen regions.",
    { x: 7.2, y: 2.3, w: 5.2, h: 4.0, fontFace: BODY, fontSize: 17, color: WHITE, margin: 0, valign: "top", isTextBox: true });
  foot(s, ++n + 1);
}
// 9 ---------------------------------------------------------------- framework
{
  const s = base("Framework: four evidence components, one fused score", "Spatial and temporal components are trained (federated). Slow and rules need no training. The hidden disc stops the spatial model copying the value it checks. Fusion is a logistic regression.");
  s.addImage({ path: path.join(FIG, "fig_pipeline.png"), x: M, y: 1.5, w: 7.6, h: 3.62, altText: "Four components feeding a fusion layer that outputs final and review flags" });
  s.addText(bullets(["**Hidden disc**: the target and cells within 2 cells are removed from the spatial input", "**Temporal**: only the cell's own previous 30 days", "**Rainfall model**: zero-inflated Gamma, not a single number", "**Never overwrites** observations; flags for review"].map((t) => t.replace(/\*\*/g, "")), { gap: 10 }),
    { x: 8.5, y: 1.6, w: 4.3, h: 4.6, fontFace: BODY, fontSize: 18, color: INK, margin: 0, valign: "top", isTextBox: true });
  foot(s, ++n + 1);
}
// 10 --------------------------------------------------------------- design: clients
{
  const s = base("Design: clients are whole IMD sub-divisions", "An earlier version used k-means blocks that split 17 of 34 sub-divisions. The final map nests clients inside sub-divisions. Clients 3 and 6 are held out entirely behind a six-cell buffer.");
  s.addImage({ path: path.join(FIG, "fig_client_map.png"), x: M, y: 1.4, w: 5.3, h: 5.47, altText: "Client map of India with eight clients, clients 3 and 6 held out" });
  stat(s, 6.6, 1.6, 3, "8", "clients, 493 to 665 land cells each");
  stat(s, 9.9, 1.6, 3, "2", "held-out clients: 3 (north-east, wettest) and 6 (west-central)", AMBER);
  stat(s, 6.6, 4.0, 3, "4,964", "land cells on the 129 x 135 grid at 0.25 degree");
  stat(s, 9.9, 4.0, 3, "6", "cell buffer between held-out and training cells", AMBER);
  foot(s, ++n + 1);
}
// 11 --------------------------------------------------------------- federated variants
{
  const s = base("Methodology: the federated variants compared", "One round: every training client runs one local epoch with other clients' cells masked, the server averages. Rounds are set so total gradient steps equal the centralised run. Unseen clients get the body plus the mean of heads in FedPer.");
  s.addImage({ path: path.join(FIG, "fig_federated.png"), x: M, y: 1.5, w: 6.4, h: 3.51, altText: "One federated round with a server, six training clients and two held-out clients" });
  s.addTable([["Variant", "Shared across clients"].map((h) => ({ text: h, options: { bold: true, color: WHITE, fill: { color: TEAL }, fontFace: BODY, fontSize: 15 } })),
    ...[["FedPer (main)", "Body; local head and scaling"], ["FedAvg", "All parameters"], ["FedAvg + fine-tune", "All, then local tuning"], ["Local-only", "Nothing; no model for unseen regions"], ["Centralised", "Reference: data pooled"]]
      .map((r) => r.map((t) => ({ text: t, options: { fontFace: BODY, fontSize: 15, color: INK, fill: { color: WHITE } } })))],
    { x: 7.3, y: 1.5, w: 5.43, colW: [1.95, 3.48], border: { type: "solid", color: "C9D6DE", pt: 1 }, margin: [0.07, 0.1, 0.07, 0.1], valign: "middle" });
  s.addText("Simulation on one machine: no privacy claim. Total gradient steps match the centralised run.", { x: M, y: 5.6, w: 12, h: 0.8, fontFace: BODY, fontSize: 17, italic: true, color: GREY, margin: 0, isTextBox: true });
  foot(s, ++n + 1);
}
// 12 --------------------------------------------------------------- data, splits, benchmark
{
  const s = base("Methodology: data, time splits and benchmark", "No real error labels exist for India, so evaluation uses deliberate corruption, kept in its own tier and labelled synthetic. Splits are time-ordered so no future data reach training.");
  const seg = (x, w, label, years, color, tc = WHITE) => {
    s.addShape(pres.ShapeType.rect, { x, y: 1.6, w, h: 1.1, fill: { color }, line: { color } });
    s.addText([{ text: label, options: { bold: true, breakLine: true } }, { text: years }], { x, y: 1.6, w, h: 1.1, fontFace: BODY, fontSize: 16, color: tc, align: "center", valign: "middle", margin: 0, isTextBox: true });
  };
  seg(M, 6.0, "Train", "1951 to 2012", TEAL); seg(M + 6.0, 2.8, "Validation", "2013 to 2017", AMBER, INK); seg(M + 8.8, 3.33, "Test", "2018 to 2025", INK);
  s.addText("1901 to 1950: evaluation-only stress test (older, sparser network)", { x: M, y: 2.8, w: 12, h: 0.4, fontFace: BODY, fontSize: 14, italic: true, color: GREY, margin: 0, isTextBox: true });
  card(s, M, 3.4, 3.85, 3.4, "Nine fault kinds", "Spike, stuck, scale, phantom rain, zeroed, repeat, drift, edge artefact, combination. Single cell or patch footprint.", { size: 16 });
  card(s, M + 4.05, 3.4, 3.85, 3.4, "Frozen benchmark", "About 1 percent of cell-days corrupted. Generated once, saved and hashed. Some settings appear only in test.", { size: 16 });
  card(s, M + 8.1, 3.4, 3.83, 3.4, "Protected extremes", "Connected group of at least 4 cells all above their own 99th percentile: kept, never corrupted, false-flag rate reported.", { size: 16, fill: MINT, line: "A8D4D8" });
  foot(s, ++n + 1);
}
// 13 --------------------------------------------------------------- proposal: fusion, budgets, metrics
{
  const s = base("Proposal: fusion at fixed false-alarm budgets", "Fusion is one shared logistic regression fitted on 2013 to 2015 synthetic faults. The two budgets were chosen from validation data before any test year is scored. The final choice log is still to be committed, so describe them as intended operating points.");
  stat(s, M, 1.6, 3.7, "1.0", "false alarms per 1,000 clean cell-days: final flag");
  stat(s, M + 4.1, 1.6, 3.7, "5.0", "per 1,000 clean cell-days: review flag", AMBER);
  stat(s, M + 8.2, 1.6, 3.7, "3", "seeds per model, reported as mean and range");
  s.addText("Headline metric: recall at the fixed budget", { x: M, y: 3.9, w: 12, h: 0.45, fontFace: HEAD, fontSize: 22, bold: true, color: TEAL, margin: 0, isTextBox: true });
  s.addText(bullets(["Also: precision-recall area, event recall, footprint overlap, detection delay, calibration", "Protected-extreme false removal reported by client, season and event size", "ROC AUC is not a headline number: false alarms matter more when faults are rare", "Intervals by resampling whole years; none given for fewer than 5 years"], { gap: 8 }),
    { x: M, y: 4.45, w: 12, h: 2.4, fontFace: BODY, fontSize: 18, color: INK, margin: 0, valign: "top", isTextBox: true });
  foot(s, ++n + 1);
}
// 14 --------------------------------------------------------------- operational prototype
{
  const s = base("Real-time demonstration: live rain-gauge feed", "A small operational path reads a public rain-gauge API within its 1,000 calls per day limit and scores readings with rules and a neighbour check. It is not a trained model. Units of the provider's accumulation field are undocumented, so totals are marked unconfirmed. Not yet run through a rain event.");
  stat(s, M, 1.6, 3, "580", "stations catalogued, in 30 cities");
  stat(s, M + 3.2, 1.6, 3, "267", "of them rain gauges", AMBER);
  stat(s, M + 6.4, 1.6, 3, "1,000", "API calls per day on the free key");
  stat(s, M + 9.4, 1.6, 2.6, "9", "stations polled every 15 minutes", AMBER);
  s.addShape(pres.ShapeType.roundRect, { x: M, y: 4.0, w: 12.13, h: 2.7, fill: { color: "FFF4E0" }, line: { color: "F0D9A8", width: 1 }, rectRadius: 0.08 });
  s.addText("What it is, and is not", { x: M + 0.3, y: 4.1, w: 11.5, h: 0.45, fontFace: HEAD, fontSize: 20, bold: true, color: "9A5B00", margin: 0, isTextBox: true });
  s.addText(bullets(["Rules and a neighbour check, labelled as not a trained model", "Daily totals on the 03 to 03 UTC rain day; units and reset period unconfirmed", "Tested with a mocked service (27 tests); not yet run through a real rain event"], { gap: 6 }),
    { x: M + 0.3, y: 4.65, w: 11.5, h: 1.9, fontFace: BODY, fontSize: 18, color: INK, margin: 0, valign: "top", isTextBox: true });
  foot(s, ++n + 1);
}
// 15 --------------------------------------------------------------- status & verification
{
  const s = base("Case study status: what exists and what does not", "Be direct about this slide. Everything is implemented and unit-tested on generated data. Nothing has run on real RF25 data, so no performance claim is made. The comparison of variants is a set of hypotheses.");
  tableSlide(s, ["Stage", "Status", "Real-data result"], [
    ["Data contract, clients, splits, leakage audit", "Built and tested", "No"],
    ["Corruption benchmark, protected extremes", "Built and tested", "No"],
    ["Spatial and temporal components, fusion", "Built; tiny CPU runs", "No"],
    ["Federated variants (masking, aggregation)", "Built; 14 tests pass", "No"],
    ["Test-year scoring, unseen clients, UK study", "Built; generated data only", "No"],
  ], [5.7, 3.9, 2.53], 1.5, 17);
  s.addShape(pres.ShapeType.roundRect, { x: M, y: 5.0, w: 12.13, h: 1.7, fill: { color: "FFF4E0" }, line: { color: "F0D9A8", width: 1 }, rectRadius: 0.08 });
  s.addText("Next: timing run, three-seed training, budget log, one test-scoring pass on real RF25. Until then the conclusions concern design and literature, not measured performance.", { x: M + 0.3, y: 5.1, w: 11.5, h: 1.5, fontFace: BODY, fontSize: 20, color: INK, margin: 0, valign: "middle", isTextBox: true });
  foot(s, ++n + 1);
}
// 16 --------------------------------------------------------------- societal / ethical / SDG
{
  const s = base("Societal, ethical and environmental impact", "Federated learning keeps data local but parameters can still leak, so no privacy claim is made. Held-out regions test fairness. Flags are for review and never overwrite. Training energy is limited by small networks and run caps.");
  card(s, M, 1.5, 3.85, 2.7, "Ethics", "No privacy claim without formal mechanisms. Regional fairness tested on held-out regions. Every flag carries its component scores.", { size: 15 });
  card(s, M + 4.05, 1.5, 3.85, 2.7, "Society", "Reliable rainfall data support early warning and water management. Flags go to review; observations are never overwritten.", { size: 15 });
  card(s, M + 8.1, 1.5, 3.83, 2.7, "Environment", "Small networks, untrained components where enough, and run caps limit training energy.", { size: 15 });
  s.addText("Sustainable Development Goals [15]", { x: M, y: 4.3, w: 12, h: 0.45, fontFace: HEAD, fontSize: 22, bold: true, color: TEAL, margin: 0, isTextBox: true });
  const sdg = [["13", "Climate Action"], ["9", "Industry, Innovation, Infrastructure"], ["11", "Sustainable Cities"], ["2", "Zero Hunger"], ["17", "Partnerships"]];
  sdg.forEach(([num, label], i) => {
    const x = M + i * 2.45;
    s.addShape(pres.ShapeType.ellipse, { x, y: 4.95, w: 0.85, h: 0.85, fill: { color: TEAL }, line: { color: TEAL } });
    s.addText(num, { x, y: 4.95, w: 0.85, h: 0.85, fontFace: HEAD, fontSize: 22, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0, isTextBox: true });
    s.addText(label, { x: x + 0.95, y: 4.95, w: 1.45, h: 0.85, fontFace: BODY, fontSize: 14, color: INK, margin: 0, valign: "middle", isTextBox: true });
  });
  foot(s, ++n + 1);
}
// 17 --------------------------------------------------------------- applications, limits, future
{
  const s = base("Applications, limitations and future scope", "Applications: screening national grids, pre-processing for flood and crop models, cross-agency collaboration, crowd-supported gauges. Limitations are central: simulation, synthetic labels, interpolated product, no real result. Future work is to run it for real.");
  card(s, M, 1.5, 3.85, 5.0, "Applications", "National grid and network screening.\n\nFlood, drought and crop pre-processing.\n\nCross-agency collaboration without sharing raw data.\n\nLow-cost gauge networks.", { size: 18 });
  card(s, M + 4.05, 1.5, 3.85, 5.0, "Limitations", "Federated training is simulated.\n\nSynthetic faults only.\n\nRF25 is itself interpolated.\n\nNo real-data result yet.", { size: 18, fill: "FFF4E0", line: "F0D9A8", headColor: "9A5B00" });
  card(s, M + 8.1, 1.5, 3.83, 5.0, "Future scope", "Run on real RF25 and report the tables.\n\nReal-label study with UK station corrections.\n\nTrue distributed run, secure aggregation.\n\nReviewer feedback loop.", { size: 18 });
  foot(s, ++n + 1);
}
// 18 --------------------------------------------------------------- conclusion
n++;
{
  const s = base("Conclusion", "Summarise: FL is suitable where data are distributed and regions differ; the case study gives an implemented design and a fixed evaluation protocol; the open question is whether the personalised variant matches centralised training and holds on unseen regions.", true);
  s.addText(bullets([
    "Federated learning suits weather anomaly detection where data are distributed and regions differ",
    "Personalisation is the main tool against regional heterogeneity",
    "In the sources checked, federated rainfall QC with held-out regions was not found",
    "DataMend gives an implemented, tested design and a fixed evaluation protocol",
    "The open question for real data: does the personalised variant match centralised training on unseen regions?",
  ], { gap: 14 }), { x: M, y: 1.6, w: 12.1, h: 4.9, fontFace: BODY, fontSize: 22, color: WHITE, margin: 0, valign: "top", isTextBox: true });
}
// 19 --------------------------------------------------------------- references
{
  const s = base("References and additional documents", "Publications and certifications: none to report.");
  const refs = [
    "[1] McMahan et al., Communication-efficient learning of deep networks from decentralized data, AISTATS 2017",
    "[2] Li et al., Federated optimization in heterogeneous networks, MLSys 2020",
    "[3] Arivazhagan et al., Federated learning with personalization layers, arXiv:1912.00818",
    "[4] Kairouz et al., Advances and open problems in federated learning, Found. Trends ML, 2021",
    "[5] Chandola, Banerjee, Kumar, Anomaly detection: a survey, ACM Comput. Surv., 2009",
    "[6] Durre et al., Comprehensive automated quality assurance of daily surface observations, JAMC, 2010",
    "[7] Khan, Saeed, Koo, FedLSTM, Electronics 13(24):4907, 2024",
    "[8] Chen, Long, Shen, Jiang, Prompt federated learning for weather forecasting, IJCAI 2023",
    "[9] Liu et al., FedTADBench, arXiv:2212.09518, 2022",
    "[10] Sha, Gagne, West, Stull, Deep-learning-based precipitation observation QC, JTECH, 2021",
    "[11] Pai et al., 0.25 degree daily gridded rainfall data set over India, MAUSAM, 2014",
    "Full list of 17 references: see the seminar report. Publications and certifications: none.",
  ];
  s.addText(refs.map((t, i) => ({ text: t, options: { breakLine: i < refs.length - 1, paraSpaceAfter: 5 } })), { x: M, y: 1.45, w: 12.1, h: 5.4, fontFace: BODY, fontSize: 16, color: INK, margin: 0, valign: "top", isTextBox: true });
  foot(s, ++n + 1);
}

pres.writeFile({ fileName: path.join(__dirname, "Seminar_Presentation.pptx") }).then((f) => console.log("wrote", f));
