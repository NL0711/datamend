// Builds Research_Paper.docx in IEEE two-column format (A4, Times New Roman, 10 pt body) following the
// research-paper-writer skill's formatting spec. Numbers are the measured values used in the report
// (SYNTHETIC faults, held-out validation years 2013-2017, seed 42).
// Usage: NODE_PATH=<dir with docx> node docs/project/build_paper.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  ImageRun, Footer, PageNumber, SectionType, TabStopType, LevelFormat,
} = require("docx");

const FONT = "Times New Roman";
const FIG = path.join(__dirname, "figures");
const A4 = { width: 11906, height: 16838 };
const MARGIN = { top: 1077, bottom: 2438, left: 812, right: 812 }; // 19 / 43 / 14.32 / 14.32 mm
const COL_W = 5021; // two columns, 4.22 mm (239 twips) apart

const TITLE = "AI-Based Time Series Weather Data Validation Platform";
const AUTHORS = ["Nathasha Lewis", "Anshu Jadhav", "Rochelle Fernandes"];
const GUIDE = "Guide: Prof. Jagruti Nagaonkar";
const AFFIL = ["Department of Computer Engineering", "Fr. Conceicao Rodrigues College of Engineering, Bandra (W), Mumbai 400050, India", "University of Mumbai"];

// ---- helpers --------------------------------------------------------------------------------------------------
function runs(text, base = {}) {
  const out = [];
  text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/).forEach((part) => {
    if (!part) return;
    if (part.startsWith("**")) out.push(new TextRun({ text: part.slice(2, -2), bold: true, font: FONT, size: 20, ...base }));
    else if (part.startsWith("*")) out.push(new TextRun({ text: part.slice(1, -1), italics: true, font: FONT, size: 20, ...base }));
    else out.push(new TextRun({ text: part, font: FONT, size: 20, ...base }));
  });
  return out;
}
const P = (t) => new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 60, line: 240 }, children: runs(t) });
const H1 = (t) => new Paragraph({ keepNext: true, spacing: { before: 140, after: 60 }, children: [new TextRun({ text: t.toUpperCase(), bold: true, font: FONT, size: 20 })] });
const H2 = (t) => new Paragraph({ keepNext: true, spacing: { before: 100, after: 50 }, children: [new TextRun({ text: t, bold: true, italics: true, font: FONT, size: 20 })] });
const bullet = (t) => new Paragraph({ numbering: { reference: "bul", level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { after: 30, line: 240 }, children: runs(t) });
const cap = (t, o = {}) => new Paragraph({ alignment: AlignmentType.CENTER, keepNext: !!o.keepNext, spacing: { before: o.before ?? 40, after: o.after ?? 120 }, children: runs(t, { size: 16 }) });

function fig(file, w, h, caption) {
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 80, after: 20 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(path.join(FIG, file)), transformation: { width: w, height: h }, altText: { title: caption, description: caption, name: file } })] }),
    cap(`**Fig. ${caption.n}.** ${caption.t}`),
  ];
}
const b1 = { style: BorderStyle.SINGLE, size: 4, color: "808080" };
const borders = { top: b1, bottom: b1, left: b1, right: b1 };
function table(label, title, cols, head, rows) {
  const total = cols.reduce((a, b) => a + b, 0);
  const cell = (t, w, hd) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders, margins: { top: 20, bottom: 20, left: 50, right: 50 },
    shading: hd ? { fill: "E0E6F0", type: ShadingType.CLEAR, color: "auto" } : undefined,
    children: [new Paragraph({ keepNext: true, children: runs(t, { size: 15, bold: !!hd }) })],
  });
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 80, after: 0 }, children: runs(`TABLE ${label}`, { size: 16 }) }),
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { after: 40 }, children: runs(title.toUpperCase(), { size: 14 }) }),
    new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: cols,
      rows: [new TableRow({ tableHeader: true, cantSplit: true, children: head.map((h, i) => cell(h, cols[i], true)) }),
        ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((t, i) => cell(t, cols[i], false)) }))] }),
    new Paragraph({ spacing: { after: 100 }, children: [] }),
  ];
}
// equation: parts = [text | [text, "sub"|"sup"]]; number at the right tab stop
function eq(parts, n) {
  const kids = parts.map((p) => (Array.isArray(p)
    ? new TextRun({ text: p[0], font: FONT, size: 20, italics: true, subScript: p[1] === "sub", superScript: p[1] === "sup" })
    : new TextRun({ text: p, font: FONT, size: 20, italics: true })));
  return new Paragraph({ tabStops: [{ type: TabStopType.CENTER, position: COL_W / 2 }, { type: TabStopType.RIGHT, position: COL_W }],
    spacing: { before: 40, after: 60 }, children: [new TextRun({ text: "\t", font: FONT, size: 20 }), ...kids, new TextRun({ text: `\t(${n})`, font: FONT, size: 20 })] });
}

// ---- front block (single column) -----------------------------------------------------------------------------------
const center = (text, size, o = {}) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: o.after ?? 60, line: 240 }, children: [new TextRun({ text, font: FONT, size, bold: !!o.bold, italics: !!o.italics })] });
const front = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240, line: 280 }, children: [new TextRun({ text: TITLE, bold: true, font: FONT, size: 48 })] }),
  center(AUTHORS.join("    "), 22, { after: 40 }),
  ...AFFIL.map((a) => center(a, 20, { after: 0 })),
  center(GUIDE, 20, { italics: true, after: 240 }),
];

// ---- body ----------------------------------------------------------------------------------------------------------
const abstract = "Rainfall records underpin flood warning, agriculture and climate research, yet every record contains faulty values such as stuck gauges, spikes, scaling errors and phantom rain. This paper presents DataMend, an AI-based validation platform that accepts a rainfall time series from a file, a live gauge feed or a gridded product and returns a verdict for every value together with the evidence behind it. The platform combines a transparent catalogue of eight reading checks and four daily checks, each declaring its inputs and reporting explicitly when it cannot run, with STNet, a compact spatio-temporal network (1.76 million parameters) trained on the 0.25-degree IMD RF25 grid. STNet couples a convolutional spatial encoder with a ConvGRU memory and three output heads, and its scores are fused with the rules at a fixed budget of one false alarm per 1,000 clean cell-days. On a frozen benchmark of six synthetic fault families in held-out validation years, a linear probe on STNet features separates every family with an AUC between 0.888 and 0.999, and the fused detector reaches a PR-AUC of 0.691 and a recall of 0.635 while flagging only 0.6% of protected heavy-rain cell-days. The system is delivered as a FastAPI backend and a React dashboard, is verified by 569 automated tests and follows an evaluation protocol that fixes budgets on validation data before any test year is scored.";
const keywords = "rainfall quality control, time-series validation, spatio-temporal neural networks, anomaly detection, explainable flags, IMD RF25";

const body = [
  new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 60, line: 240 }, children: [new TextRun({ text: "Abstract—", bold: true, italics: true, font: FONT, size: 20 }), ...runs(abstract, { bold: true })] }),
  new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 100, line: 240 }, children: [new TextRun({ text: "Keywords—", bold: true, italics: true, font: FONT, size: 20 }), ...runs(keywords, { italics: true })] }),

  H1("1. Introduction"),
  P("Rainfall is the most consequential and the most irregular of the weather variables. It is zero on most days and strongly skewed on the rest, so a single erroneous value can change a flood model, an agricultural advisory or a climate trend. Gauges jam and repeat one reading for weeks, loggers write zeros during faults, transmission errors scale values by an order of magnitude, and interpolation spreads one bad gauge across its neighbours. Detecting such errors before the data are used is the task of quality control (QC) [1], [2]."),
  P("Operational QC rests on long lists of fixed tests and manual review [1], while learned detectors that exploit spatial context have recently been shown to improve precipitation QC [3]. A practical gap remains: a single, reproducible system that takes a rainfall series from any source, applies both rule-based and learned evidence, explains every flag and records exactly what was done. Two requirements make the problem distinctive. First, an unusual value is not necessarily a wrong value, because the heaviest rainfall is also the most valuable, so extremes must be separated from faults. Second, every flag has an operational cost, so performance must be stated at an explicit false-alarm budget rather than as accuracy."),
  P("This paper presents DataMend, a rainfall validation platform with two parts: a validation platform (Part A) and a trained model system, STNet (Part B), operating on the 0.25-degree IMD RF25 daily grid [4]. The contributions are:"),
  bullet("A layered validation platform with a strict input contract, a catalogue of eight reading and four daily checks that declare their needs and report “not run” explicitly, stored runs, JSON and CSV reports, an explainer interface and a reviewer loop."),
  bullet("STNet, a compact spatio-temporal fault detector (1.76 million parameters, 6.8 MB) with fault, clean and discrimination heads that separates genuine extremes from faults."),
  bullet("A fusion and calibration scheme that fixes the flag threshold from validation curves at a stated false-alarm budget and reports the rate at which protected extremes are flagged."),
  bullet("A frozen, reproducible evaluation protocol on six synthetic fault families, with 569 automated tests supporting the implementation."),
  P("The remainder of the paper is organised as follows. Section 2 reviews related work, Section 3 describes the system design, Section 4 the implementation, Section 5 the evaluation, Section 6 discusses the results and Section 7 concludes."),

  H1("2. Related Work"),
  H2("2.1 Rule-Based Quality Control"),
  P("Durre et al. describe the automated quality assurance of the Global Historical Climatology Network-Daily data set: duplicate and impossible values, outliers against station climatology, temporal persistence, internal consistency and spatial comparison, validated manually and flagging 0.24% of more than 1.5 billion values [1]. Such systems are transparent and inexpensive, and they define the vocabulary of checks that the DataMend catalogue adopts. Their thresholds are set by hand, which motivates adding a calibrated, budgeted learned layer."),
  H2("2.2 Learned Detectors"),
  P("Chandola et al. organise anomaly detection by data type and learning setting [2]. Recurrent models such as LSTM [5] and GRU [6] predict or reconstruct series, and convolutional recurrent networks carry the idea to gridded fields by replacing matrix products with convolutions [7]. Sha et al. applied convolutional networks to gridded precipitation and elevation fields to quality-control gauge observations and reported an AUC of 0.927 [3], demonstrating the value of spatial context. STNet follows this direction with a convolutional encoder for the spatial neighbourhood and a ConvGRU for temporal memory."),
  H2("2.3 Federated and Distributed Learning"),
  P("Federated learning trains a model across data holders by exchanging parameters rather than data [8], [9]. FedProx [10] and FedPer [11] address non-identical clients and Li et al. survey the open problems [12]. Federated fault detection has been demonstrated for sensor networks [13], weather forecasting [14] and as a time-series benchmark [15]. The DataMend model system defines eight regional clients composed of whole IMD sub-divisions, which keeps the design ready for settings in which regional data cannot be pooled."),
  H2("2.4 Positioning"),
  P("DataMend builds on these strands through their integration: layered validation with explicit not-run reporting, discrimination of genuine extremes from faults, evidence behind every flag, an explanation seam and an evaluation anchored to a fixed false-alarm budget. The data sources are the IMD RF25 grid [4], the Weather Union gauge network [16] and station metadata derived from NOAA’s Integrated Surface Database history file [17]."),

  H1("3. System Design"),
  H2("3.1 Architecture"),
  P("Fig. 1 shows the system. A series enters through the input contract, passes the check catalogue and leaves as per-row verdicts, scores and evidence collected in a stored run report. A score-provider seam accepts a calibrated trained score from Part B, and an explainer interface serves a rule-based baseline and an external AI narrator. Two invariants hold throughout: the original data are never overwritten, and the narrator never changes a verdict, score or evidence."),
];
// Fig. 1 spans both columns (single-column section between the two column sections)
const archFig = fig("fig_architecture.png", 640, 395, { n: 1, t: "Architecture of DataMend: data sources, validation platform (Part A) and model system (Part B)." });
const body2 = [
  H2("3.2 Input Contract and Check Catalogue"),
  P("The input contract accepts CSV and JSON in a reading profile or a daily profile. A file-level problem rejects the file, whereas a row-level problem (missing, negative, non-numeric, duplicated or out-of-order values) keeps the row with a flag and a reason. The catalogue contains eight reading checks, four daily checks and duplicate-row detection. Each check declares the inputs it needs, so a check that cannot run, for example a neighbour check without neighbours, is listed as not run instead of silently passing. Each row receives a verdict (OK, SUSPECT, UNCERTAIN or NO_DATA), an uncalibrated rule score with a severity band and evidence tagged as measured, assumed or derived."),
  H2("3.3 Evidence, Explanation and Review"),
  P("Evidence follows a versioned JSON contract (evidence-v1) with a window cap of 24 readings or 14 days and a 64 KB size cap. An explainer interface produces explanations from the stored evidence; a rule-based baseline is always available, and an external AI narrator can be attached behind the same interface. Explanations are stored separately and always marked as generated. Reviewers record decisions (confirmed fault, false alarm, genuine extreme or needs follow-up) that are stored apart from the evidence and never alter a verdict."),
  H2("3.4 STNet"),
  P("STNet reads a window of consecutive daily rainfall fields. A convolutional encoder (width 32, 16 features) summarises each cell’s spatial neighbourhood, a ConvGRU carries temporal memory and an optional long-range LSTM branch provides seasonal memory. Three heads share the representation: a fault head scores each cell-day for faults, a clean head scores plausibility and a discrimination head separates genuine extremes from faults. A robust input transform handles the heavy tail of rainfall. Training weights fault cell-days with 10, protected extremes with 3 and ambiguous extremes with 2. The network has 1,761,769 parameters (6.8 MB) and requires 8.2 GFLOPs per day over the full grid."),
  H2("3.5 Fusion and False-Alarm Budget"),
  P("For a cell-day *i*, the rule score and the STNet fault score are fused by a logistic layer,"),
  eq(["p", ["i", "sub"], " = σ(β", ["0", "sub"], " + β", ["r", "sub"], " r", ["i", "sub"], " + β", ["s", "sub"], " s", ["i", "sub"], ")"], 1),
  P("where *r* is the rule score, *s* is the STNet fault score and β are learned weights; a boosted variant is evaluated in parallel. For a budget *b*, the threshold τ is the smallest value for which the false-alarm rate on the clean set *C* does not exceed *b*,"),
  eq(["FA(τ) = 1000 · |{i ∈ C : p", ["i", "sub"], " > τ}| / |C| ≤ b"], 2),
  P("with *b* = 1 in this work. Recall is then the share of the fault set *F* whose fused probability exceeds τ. The rule score and the calibrated flag are never mixed in one number."),

  H1("4. Implementation"),
  P("The backend is written in Python with FastAPI, with business logic in services rather than in routes; storage is SQLite with portable JSON columns so that it can move to PostgreSQL. The dashboard is a React and TypeScript application with views for overview, runs, data explorer, review queue, anomaly lab, locations, live gauge feed, station network and settings. The station network view maps 580 Weather Union gauges and 541 Indian synoptic stations, coloured by check, flag and audit state. A live Weather Union feed is scored by the same catalogue as one open run per rain day. Settings editable from the dashboard are protected by an admin token with constant-time comparison and rate limiting, and secrets are write-only. The system is containerised with Docker. The model system is implemented in PyTorch with YAML configurations that fix splits, seeds and the benchmark, and every run records wall time, memory, GPU use and energy."),

  H1("5. Evaluation"),
  H2("5.1 Data, Benchmark and Protocol"),
  P("The IMD RF25 daily grid [4] is split by time: earlier years train, validation years 2013–2017 are used for selection and the final years are test years scored once. Eight regional clients are formed from whole IMD sub-divisions so that no sub-division mixes trained and unseen cells, and two clients (3 and 6) are held out. Because expert error labels are not available for the grid, a frozen, hash-checked benchmark corrupts clean data with six fault families (spike, stuck, scale, phantom rain, zeroed and drift), together with protected extremes that are never corrupted and ambiguous single-cell extremes that are tracked separately. Fault results are therefore reported on synthetic faults. Budgets are fixed on validation data only, and each design decision is accepted or declined by a rule written before the run. Metrics are PR-AUC, recall, event recall, false alarms per 1,000 clean cell-days and the share of protected extremes flagged."),
  H2("5.2 Separability of Fault Families"),
  P("A linear probe fitted on 2013 and tested on 2014 shows that STNet’s features separate every fault family from clean data (Fig. 2): AUC is 0.999 for spikes, 0.987 for phantom rain, 0.975 for stuck gauges, 0.938 for scale errors, 0.895 for drift and 0.888 for zeroed values."),
  ...fig("pp_probe_auc.png", 326, 189, { n: 2, t: "Linear-probe AUC of STNet features by fault family (synthetic faults; fit 2013, test 2014)." }),
  H2("5.3 Operating Point"),
  P("TABLE I gives the results at one false alarm per 1,000 clean cell-days. With the rules and the fault head fused by the logistic layer, the detector reaches a PR-AUC of 0.691, a recall of 0.635, an event recall of 0.619 and an IoU of 0.755, while flagging 0.6% of protected extremes. Event recall is highest for spikes (0.993), stuck gauges (0.991) and phantom rain (0.957), and the overall event recall of the fault head is 0.659."),
  ...table("I", "Fused rules + STNet at one false alarm per 1,000 (synthetic faults)", [1900, 640, 600, 640, 620, 621],
    ["Variant", "PR-AUC", "Recall", "Event rec.", "FA/1,000", "Prot."],
    [["Rules + fault head (logistic)", "0.691", "0.635", "0.619", "1.27", "0.6%"],
      ["Rules + fault head (boosted)", "0.682", "0.629", "0.573", "0.73", "2.7%"],
      ["Rules + fault + clean heads", "0.693", "0.636", "0.608", "1.24", "1.9%"],
      ["Rules + four STNet heads", "0.707", "0.644", "0.637", "1.38", "2.3%"]]),
  H2("5.4 Detection Against Fault Size"),
  P("Recall grows monotonically with the size of the fault (Fig. 3), from 0.427 for changes below 0.1 mm to 0.885 for changes of 20–100 mm and 0.896 above 100 mm. For strong faults, defined as a change of at least 5 mm with a footprint weight of at least 0.5, the recall is 0.778. These are the faults with the largest operational consequence."),
  ...fig("pp_recall_vs_size.png", 326, 210, { n: 3, t: "Recall of the STNet fault head at one false alarm per 1,000 against the size of the fault." }),
  H2("5.5 Regional Calibration"),
  P("Across the eight regional clients, the calibrated false-alarm rate under the global threshold lies between 0.56 and 1.80 per 1,000 clean cell-days (mean 1.12, derived), with 95% intervals computed from 358,125 to 484,827 clean cell-days per client; the two held-out regions score 1.80 and 1.15."),
  H2("5.6 Design Decisions Under the Protocol"),
  P("A paired comparison with a longer-memory encoder, resampled over whole validation years, improved recall by 3.4 points and PR-AUC by 2.1 points, better in all five years, with the largest gains for stuck-gauge faults (recall 0.770 to 0.860) and zeroed faults (event recall 0.282 to 0.366). A candidate cumulative-sum drift stage was evaluated against the fault head under an acceptance rule fixed before the run; it did not meet the rule and was not added, which keeps the delivered pipeline compact."),
  H2("5.7 Cost and Verification"),
  P("Training STNet took 9,172 s on a single Tesla T4 GPU (165.7 Wh of GPU energy, 5.3 GB peak GPU memory). Network inference runs at about 50 days of the full grid per second. The platform and model system are covered by 239 and 330 automated tests respectively, using generated data and mocked transports, and a seeded anomaly lab injected faults through the real pipeline, with every injected fault flagged across three seeds and both profiles."),

  H1("6. Discussion"),
  P("The results show that a compact network trained on a national grid yields features that separate all six synthetic fault families, and that fusing its score with transparent rules gives a detector that operates at a stated false-alarm budget while rarely flagging protected heavy-rain events. Recall rises with fault magnitude, which matches operational need: the faults that matter most for flood and water-resource decisions are the ones detected most reliably. The layered design also keeps every flag explainable, since the rule evidence is stored with each verdict and the trained score enters only through a defined seam."),
  P("The benchmark uses synthetic faults, which provide exact ground truth and controlled stress tests across fault types and magnitudes; the corresponding result on expert-reviewed labels is the natural next step as such labels become available for Indian stations. The frozen protocol, in which budgets are fixed on validation data and test years are scored once, makes every figure reproducible and prevents tuning against the test period."),

  H1("7. Conclusion and Future Work"),
  P("This paper presented DataMend, an AI-based rainfall time-series validation platform that combines an explainable catalogue of checks, a compact spatio-temporal detector and a budgeted fusion scheme. STNet, with 1.76 million parameters, trains in 2.5 hours on one GPU and separates six fault families with an AUC between 0.888 and 0.999; fused with the rules at one false alarm per 1,000 clean cell-days it reaches a PR-AUC of 0.691 and recall of 0.635 while flagging 0.6% of protected extremes. The platform, with its input contract, runs, explainer seam, live feed, station-network view and reviewer loop, is verified by 569 automated tests."),
  P("Future work comprises connecting the trained score to live gauges through the score-provider seam, evaluating on expert-reviewed labels and with multiple seeds, attaching the AI narrator through the documented contract, replaying NOAA ISD history for India, and extending the federated variants to real regional clients. Reliable rainfall records support flood preparedness, food security and climate action, in line with the Sustainable Development Goals [18]."),
];

const refs = [
  "I. Durre, M. J. Menne, B. E. Gleason, T. G. Houston and R. S. Vose, “Comprehensive automated quality assurance of daily surface observations,” J. Appl. Meteorol. Climatol., vol. 49, no. 8, pp. 1615–1633, 2010.",
  "V. Chandola, A. Banerjee and V. Kumar, “Anomaly detection: A survey,” ACM Comput. Surv., vol. 41, no. 3, art. 15, 2009.",
  "Y. Sha, D. J. Gagne, G. West and R. Stull, “Deep-learning-based precipitation observation quality control,” J. Atmos. Ocean. Technol., vol. 38, no. 5, pp. 1075–1091, 2021.",
  "D. S. Pai et al., “Development of a new high spatial resolution (0.25 × 0.25 degree) long period (1901–2010) daily gridded rainfall data set over India,” MAUSAM, vol. 65, no. 1, pp. 1–18, 2014.",
  "S. Hochreiter and J. Schmidhuber, “Long short-term memory,” Neural Comput., vol. 9, no. 8, pp. 1735–1780, 1997.",
  "K. Cho et al., “Learning phrase representations using RNN encoder-decoder for statistical machine translation,” in Proc. EMNLP, 2014, pp. 1724–1734.",
  "X. Shi, Z. Chen, H. Wang, D.-Y. Yeung, W.-K. Wong and W.-C. Woo, “Convolutional LSTM network: A machine learning approach for precipitation nowcasting,” in Proc. NeurIPS, 2015, pp. 802–810.",
  "B. McMahan, E. Moore, D. Ramage, S. Hampson and B. Aguera y Arcas, “Communication-efficient learning of deep networks from decentralized data,” in Proc. AISTATS, PMLR vol. 54, 2017, pp. 1273–1282.",
  "P. Kairouz et al., “Advances and open problems in federated learning,” Found. Trends Mach. Learn., vol. 14, no. 1–2, pp. 1–210, 2021.",
  "T. Li, A. K. Sahu, M. Zaheer, M. Sanjabi, A. Talwalkar and V. Smith, “Federated optimization in heterogeneous networks,” in Proc. MLSys, 2020. arXiv:1812.06127.",
  "M. G. Arivazhagan, V. Aggarwal, A. K. Singh and S. Choudhary, “Federated learning with personalization layers,” arXiv:1912.00818, 2019.",
  "T. Li, A. K. Sahu, A. Talwalkar and V. Smith, “Federated learning: Challenges, methods, and future directions,” IEEE Signal Process. Mag., vol. 37, no. 3, pp. 50–60, 2020.",
  "R. Khan, U. Saeed and I. Koo, “FedLSTM: A federated learning framework for sensor fault detection in wireless sensor networks,” Electronics, vol. 13, no. 24, art. 4907, 2024.",
  "S. Chen, G. Long, T. Shen and J. Jiang, “Prompt federated learning for weather forecasting: Toward foundation models on meteorological data,” in Proc. IJCAI, 2023, pp. 3532–3540.",
  "F. Liu et al., “FedTADBench: Federated time-series anomaly detection benchmark,” arXiv:2212.09518, 2022.",
  "Weather Union, “Weather Union API documentation,” https://www.weatherunion.com/dashboard/, accessed Nov. 19, 2026.",
  "NOAA National Centers for Environmental Information, “Integrated Surface Database (ISD) readme,” https://www.ncei.noaa.gov/pub/data/noaa/readme.txt.",
  "United Nations General Assembly, “Transforming our world: the 2030 Agenda for Sustainable Development,” A/RES/70/1, 2015.",
];
const refParas = refs.map((r, i) => new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 20, line: 228 }, indent: { left: 360, hanging: 360 },
  tabStops: [{ type: TabStopType.LEFT, position: 360 }], children: [new TextRun({ text: `[${i + 1}]\t`, font: FONT, size: 16 }), new TextRun({ text: r, font: FONT, size: 16 })] }));

const footer = new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18 })] })] });
const doc = new Document({
  creator: AUTHORS[0], title: TITLE, description: "Research paper, IEEE two-column format",
  styles: { default: { document: { run: { font: FONT, size: 20 } } } },
  numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 300, hanging: 240 } } } }] }] },
  sections: [
    { properties: { page: { size: A4, margin: MARGIN } }, footers: { default: footer }, children: front },
    { properties: { type: SectionType.CONTINUOUS, page: { size: A4, margin: MARGIN }, column: { count: 2, space: 239 } }, children: body },
    { properties: { type: SectionType.CONTINUOUS, page: { size: A4, margin: MARGIN } }, children: archFig },
    { properties: { type: SectionType.CONTINUOUS, page: { size: A4, margin: MARGIN }, column: { count: 2, space: 239 } },
      children: [...body2, H1("References"), ...refParas] },
  ],
});
Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, "Research_Paper.docx");
  fs.writeFileSync(out, buf);
  console.log("wrote", out, buf.length, "bytes");
});
