// Text of the major project report (FRCRCE project-report template: chapters 1-7, references).
// Every number comes from the repository (tests, specs, code) or from the STNet result files
// (probe, ablation, budget check, ceiling, telemetry, paired and drift reports). Fault results are on SYNTHETIC faults.
// Markup: **bold**, *italic*. Block types: p, bullets, numbered, table, figure, h2, h3.

const TITLE = "AI-Based Time Series Weather Data Validation Platform";
const STUDENTS = [
  ["Nathasha Lewis", "10257"],
  ["Anshu Jadhav", "10247"],
  ["Rochelle Fernandes", "10245"],
];
const GUIDE = "Prof. Jagruti Nagaonkar";
const GUIDE_DESIG = ""; // not provided; the cover omits the line when empty
const keywords = "Rainfall, data validation, quality control, explainable flags, spatio-temporal neural network, IMD RF25, FastAPI, React.";

const abstract = [
  "Rainfall records drive flood warning, agriculture, hydrology and climate research, yet every record contains faulty values: stuck gauges, spikes, scaling errors, phantom rain and drifting sensors. This project presents **DataMend**, an end-to-end rainfall validation platform that accepts a rainfall series, runs layered checks on every reading and returns a verdict for each one together with the evidence behind it. The platform pairs a transparent rule engine (eight reading checks and four daily checks, each declaring what it needs and reporting honestly when it cannot run) with an optional trained layer, **STNet**, a spatio-temporal network that learns what normal rainfall looks like on India's 0.25-degree IMD grid.",
  "The platform is built as a FastAPI backend and a React dashboard with an input contract, run storage, JSON and CSV reports, an explainer interface, a live rain-gauge feed, a station-network map of 580 gauges and 541 Indian synoptic stations, and a review loop for human reviewers. STNet (1.76 million parameters, 6.8 MB) was trained on IMD RF25 data in 2.5 hours on a single T4 GPU and separates six fault families with AUC between 0.888 and 0.999 on a next-year test. Fused with the rules at a fixed budget of one false alarm per 1,000 clean cell-days, it reaches PR-AUC 0.69 and recall 0.64 while flagging only 0.6 percent of protected heavy-rain cell-days, so genuine extremes are preserved.",
  "The project is supported by 569 automated tests, a frozen evaluation protocol that fixes budgets on validation data before any test year is scored, and documented decisions for every design choice. Fault results are reported on synthetic faults and are labelled as such. The result is a reproducible, explainable and extensible foundation for rainfall data quality control in India.",
];

const glossary = [
  ["API", "Application Programming Interface."],
  ["CSV", "Comma-Separated Values file."],
  ["CUSUM", "Cumulative Sum, a change-detection statistic."],
  ["ConvGRU", "Convolutional Gated Recurrent Unit."],
  ["IMD", "India Meteorological Department."],
  ["PR-AUC", "Area under the precision-recall curve."],
  ["QC", "Quality Control."],
  ["RF25", "IMD's 0.25-degree gridded daily rainfall data set for India."],
  ["STNet", "The spatio-temporal fault-detection network of this project."],
  ["Cell-day", "One grid cell on one day, the unit that is scored and flagged."],
  ["Protected extreme", "A connected group of cells all above their own heavy-rain threshold, never corrupted in the benchmark."],
  ["Synthetic fault", "A deliberate, recorded corruption of clean data used as a controlled test."],
];

const chapters = [];

// -------------------------------------------------------------------------------------------------------- 1
chapters.push({
  title: "Introduction",
  blocks: [
    { p: "Rainfall is the most consequential and the most irregular of the weather variables. It is zero on most days and extremely skewed on the rest, so a single wrong value can change a flood model, an agricultural advisory or a climate trend. Gauges jam and repeat one value for weeks, loggers write zeros during faults, transmission errors multiply readings by ten, and interpolation spreads one bad gauge over its neighbours. Catching such errors before data are used is the task of quality control (QC) [1], [2]." },
    { h2: "1.1 Background" },
    { p: "Manual review and a lengthy list of fixed tests are the mainstays of operational quality control for daily surface data [2]. Since then, learning-based detectors that make use of spatial context have demonstrated impressive performance for precipitation gauges [3]. A working group still lacks a single, repeatable system that can take a rainfall series from any source, apply both types of evidence, explain each flag, and document the actions taken. DataMend is designed to be that kind of system." },
    { p: "There are two components to the platform. A FastAPI backend and a React dashboard that perform layered checks and generate evidence-based verdicts make up Part A, the validation platform. The evaluation harness and model system, STNet, are part of Part B. They were trained on the IMD RF25 daily grid [4] and provide an optional trained score via a specified seam." },
    { h2: "1.2 Motivation" },
    { p: "There is a growing need for data validation in this day of machine learning and artificial intelligence. Weather data, in general, tends to be huge with sporadic values in between. Anomalies raise flags and a flag is only useful when the reviewer can see why it was raised. Hence, we opted for a platform that can assist users in handling this data with the help of AI assistance for explainability. Heavy rain is the rarest and most valuable, so the system separates extremes from faults and never treats magnitude alone as a fault. Uploaded files, a live gauge feed and gridded products all flow through the same catalogue of checks. Splits, seeds, configurations and budgets are fixed and recorded, so another developer can repeat every result. Reliable rainfall records also support flood preparedness, food security and climate action, which align with the Sustainable Development Goals [7]." },
    { h2: "1.3 Objectives" },
    { numbered: [
      "To design and build a rainfall validation platform with a strict input contract, a catalogue of explainable checks and stored, exportable runs.",
      "To develop STNet, a trained spatio-temporal detector for gridded rainfall, and to evaluate it under a frozen protocol with a fixed false-alarm budget.",
      "To provide an explanation interface, a review loop, a live gauge feed and a station-network view in one dashboard.",
      "To verify the system with unit, integration and acceptance tests on generated data and with a documented evaluation.",
    ] },
    { h2: "1.4 Scope" },
    { p: "Rainfall is the only parameter. The core platform needs only the rainfall series; station identity, coordinates and quality flags are optional metadata. Raw data are never overwritten, and corrected values, where produced, are stored separately. The trained layer targets the IMD RF25 grid and reports results on synthetic faults, which are labelled as synthetic throughout." },
  ],
});

// -------------------------------------------------------------------------------------------------------- 2
chapters.push({
  title: "Literature Review",
  blocks: [
    { p: "This chapter reviews the work on which DataMend builds: operational rule-based QC, learning-based precipitation QC, sequence and spatio-temporal models, and the data sources used." },
    { h2: "2.1 Rule-Based Quality Control" },
    { p: "Durre and colleagues describe the automated quality assurance of the Global Historical Climatology Network-Daily data set: duplicate and impossible values, outliers against station climatology, temporal persistence, internal consistency and spatial comparison, validated manually and flagging 0.24 percent of more than 1.5 billion values [2]. Such systems are transparent and cheap, and they set the vocabulary of checks that DataMend's catalogue adopts. Their thresholds are set by hand, which is why DataMend adds a calibrated, budgeted trained layer on top of its rules." },
    { h2: "2.2 Learning-Based Detection" },
    { p: "Chandola, Banerjee and Kumar organise anomaly detection by data type and learning setting [1]. Sequence models such as LSTM [5] and GRU [6] predict or reconstruct a series, and convolutional recurrent models carry the idea to gridded fields by replacing matrix products with convolutions [10]. Sha and co-authors applied convolutional networks to gridded precipitation and elevation to quality-control gauge observations and reported an AUC of 0.927 [3], showing that spatial context from a gridded product is valuable. STNet follows this direction: a convolutional encoder reads the spatial neighbourhood, and a ConvGRU carries temporal memory." },
    { h2: "2.3 Data Sources" },
    { p: "The IMD RF25 data set provides daily rainfall on a 0.25-degree grid over India [4]. The live gauge network is provided through the Weather Union API [8], and the station metadata for Indian synoptic stations is derived from NOAA's Integrated Surface Database history file [9]. Non-US ISD data are not redistributed, in line with the data-sharing rules attached to them." },
    { table: {
      caption: "Table 2.1: Positioning of DataMend against representative approaches",
      cols: [1900, 2500, 2300, 2326],
      head: ["Approach", "Strength", "Typical limitation", "How DataMend builds on it"],
      rows: [
        ["Rule-based QA [2]", "Transparent, cheap", "Hand-set thresholds", "Rule catalogue with declared needs and explicit 'not run'"],
        ["CNN precipitation QC [3]", "Uses spatial context", "Single region", "Spatial encoder over the national grid, eight evaluation regions"],
        ["Recurrent models [5], [6], [10]", "Temporal memory", "Report accuracy-style scores", "ConvGRU memory, fixed false-alarm budget"],
      ],
    } },
  ],
});

// -------------------------------------------------------------------------------------------------------- 3
chapters.push({
  title: "Problem Statement",
  blocks: [
    { p: "Given a rainfall series from a file, a live gauge or a grid, decide for every value whether it is plausible, suspect or uncertain, say why, and do so at a false-alarm rate a reviewer can sustain, without ever discarding genuine extremes." },
    { h2: "3.1 Requirements Identified" },
    { bullets: [
      "**Evidence with every flag**, so a reviewer can act on it and an explainer can narrate it.",
      "**Genuine extreme versus fault discrimination**, in which magnitude alone is never a fault.",
      "**Honest operating points.** Performance is stated at a fixed budget of false alarms per 1,000 clean items, with precision, recall, F1, detection delay and latency.",
      "**File-level rejection and row-level flags.** A malformed file is refused; a malformed row is kept with a flag and a reason.",
      "**Regional heterogeneity.** India spans arid plains, the heavy-rain north-east and the monsoon coasts, so one threshold cannot suit every place.",
    ] },
    { h2: "3.2 Proposed Solution" },
    { p: "Deterministic checks come first, followed by a robust statistic and a neighbour check, an optional trained score, and a verdict that includes supporting evidence. DataMend's layered design satisfies these requirements. There is never any blending of the calibrated trained flag and the rule score. An explanation can never change a verdict because explainer interfaces generate human-readable explanations that are stored separately from the evidence and identified as generated." },
  ],
});

// -------------------------------------------------------------------------------------------------------- 4
chapters.push({
  title: "Project Description",
  blocks: [
    { h2: "4.1 Overview of the Project" },
    { p: "In Figure 4.1, the entire system is displayed. After passing the check catalogue and entering through the input contract, a rainfall series departs as per-row verdicts, scores, and supporting documentation gathered in a stored run report. The explainer interface serves both the rule-based baseline and an external AI narrator, while the score-provider seam receives a calibrated trained score from Part B. The React dashboard talks to the FastAPI backend over HTTPS, the backend calls the Weather Union API and the optional AI narrator, and STNet is trained offline on the IMD rainfall data." },
    { figure: { file: "diagram_architecture.png", w: 490, h: 244, caption: "Figure 4.1: System architecture of DataMend" } },
    { h2: "4.2 Module Description" },
    { h3: "4.2.1 Modules" },
    { p: "DataMend is composed of a few basic components that function together. After cleaning up column names and timestamps and reading CSV and JSON files, the input contract either rejects a bad file or flags a bad row. After that, the check catalogue performs eight reading checks, four daily checks, and a duplicate-row check. Every row receives a verdict (OK, SUSPECT, UNCERTAIN, or NO_DATA), a rule score, and the supporting documentation for each check that indicates what it needs. Every run can be exported as JSON or CSV and is saved with its input hash, settings, and version in addition to a list of any checks that failed to execute. Using either an external AI narrator behind the same interface or an internal rule-based explainer, an explainer reads the stored evidence and writes a plain-language explanation. A place lookup provides the grid cell, the region, and whether a point is on land or at sea. The same checks also score a live Weather Union gauge feed. An anomaly lab allows us to inject fictitious faults to see if the pipeline detects them, and reviewers can document their own decisions on flagged rows, kept apart from the evidence. All of this sits behind a dashboard with views for the overview, runs, data explorer, review queue, anomaly lab, locations, live feed, station network and settings. On the model side, a separate system handles the data splits, the fault benchmark, the STNet network, fusion with the rules at a fixed false-alarm budget, calibration and a one-time test pass." },
    { h3: "4.2.2 Data Flow Diagram" },
    { p: "Figure 4.2 gives the level 1 data flow diagram, and the steps below describe it." },
    { figure: { file: "diagram_dataflow.png", w: 470, h: 218, caption: "Figure 4.2: Data flow diagram (level 1) of DataMend" } },
    { numbered: [
      "A user or the live feed supplies a series; the input contract validates it and creates internal Reading or DailyTotal records, leaving the original row untouched.",
      "The check catalogue evaluates each record, lists checks that could not run and emits verdicts with evidence.",
      "The run service stores the run, results and check hits and builds the report headline from measured numbers only.",
      "On request, the explainer reads the stored evidence and writes an explanation, stored separately and marked generated.",
      "Reviewers record decisions on flagged rows; these are stored apart and never change a verdict or score.",
    ] },
    { h3: "4.2.3 E-R Diagram" },
    { p: "A **run** has many **results** (one per row), **check hits**, **explanations** and **review decisions**, and each of these carries a *run_id* foreign key that is deleted together with the run. A check hit also belongs to one result. Explanations and review decisions point to a result row only through *row_ref*, shown as dashed lines in Figure 4.3, so one row can have several explanations and several reviews. Solid lines are foreign keys. Table 4.1 lists the entities." },
    { figure: { file: "diagram_er_corrected.png", w: 500, h: 303, caption: "Figure 4.3: Entity-relationship diagram of the DataMend run store (SQLite)" } },
    { h3: "4.2.4 Database Design" },
    { table: {
      caption: "Table 4.1: Principal tables (SQLite, written so it can move to PostgreSQL)",
      cols: [1900, 4000, 3126],
      head: ["Table", "Content", "Key relation"],
      rows: [
        ["validation_runs", "Time, profile, source, input hash, settings, version, git commit, not-run list, report", "Parent of all run data"],
        ["validation_results", "Row reference, station, verdict, rule score, severity, original row", "Belongs to a run"],
        ["validation_check_hits", "Check, layer, kind, weight, reason, evidence", "Belongs to a run and a result"],
        ["explanations", "Text, generator, model, kind (explain or chat), generated flag", "Belongs to a run, linked by row_ref"],
        ["reviews", "Decision, note, reviewer, verdict at review, time", "Belongs to a run, linked by row_ref"],
      ],
    } },
    { h3: "4.2.5 Input Design" },
    { p: "Input is a CSV or JSON file of timestamped rainfall, or a live feed. The user declares the profile (reading or daily), accumulation mode, interval and time zone. Header aliases are reported back. A file with no usable timestamp or value column is rejected; a row with a missing, negative, non-numeric, duplicated or out-of-order value is kept with a flag and a reason. Uploads up to 12 MB are accepted." },
    { h3: "4.2.6 Output Design" },
    { p: "Each run yields a report with headline numbers measured from the data, a checks-not-run list, a worklist of flagged rows ordered by rule score and paged at 50 rows, a downsampled timeline with check lanes, one-row evidence on demand, and JSON and CSV exports. The model system adds budget checks, ceiling analyses and an IMD regional summary." },
  ],
});

// -------------------------------------------------------------------------------------------------------- 5
chapters.push({
  title: "System Testing",
  blocks: [
    { p: "Testing uses generated data and mocked transports, never the live API quota. The repository carries 239 platform tests and 330 model-system tests (569 in total), together with the dashboard's front-end tests, type-checking and production build." },
    { h2: "5.1 Unit Testing" },
    { p: "Unit tests include the model system's data contract, splits, leakage audit, fault generators, metrics, fusion and calibration. They also include the evidence builder and its 64 KB cap, the explainers and their guards, the runtime settings validation, and the place lookup. They cover the input contract (file-level rejection versus row-level flags, aliases and accumulation modes) as well as each reading and daily check (pass and fail conformance, declared needs and not-run reasons). Finally, they cover scoring and severity bands." },
    { h2: "5.2 Integration and Acceptance Testing" },
    { p: "From upload to storage and the API, integration tests proceed in the following order: runs, paged rows, evidence, exports, the live feed changing one open run per rainy day, the narrator client on a simulated transport, the admin-token-protected settings, and the review loop. By injecting seeded synthetic faults through the actual pipeline and flagging each injected fault across three seeds and both profiles, the anomaly lab demonstrated acceptance." },
    { h2: "5.3 Test Cases" },
    { table: {
      caption: "Table 5.1: Representative test cases",
      cols: [2600, 3400, 3026],
      head: ["Case", "Input", "Expected outcome"],
      rows: [
        ["Empty or header-only file", "No data rows", "File rejected with a reason"],
        ["Missing required column", "CSV without a value column", "File rejected"],
        ["Duplicate and out-of-order timestamps", "Repeated and reversed rows", "Rows kept, flagged with reasons"],
        ["Frozen value", "Same non-zero value for many readings", "Persistence check fires with evidence"],
        ["Extreme value, neighbours agree", "Heavy rain at a gauge and nearby", "Not called a fault from magnitude alone"],
        ["Check lacks its inputs", "No neighbours supplied", "Neighbour check listed as not run"],
        ["Narrator not configured", "Chat request, no URL", "503 'AI narrator not connected', nothing invented"],
        ["Oversize narrator reply", "Reply above 4,000 characters", "Reply refused"],
      ],
    } },
  ],
});

// -------------------------------------------------------------------------------------------------------- 6
chapters.push({
  title: "Implementation Details",
  blocks: [
    { h2: "6.1 Methodology" },
    { h3: "6.1.1 Platform" },
    { p: "The backend is written in Python with FastAPI; business logic lives in services, not in routes. Storage is SQLite with portable JSON columns. The dashboard is React with Vite and TypeScript, and the whole system is containerised for Docker and prepared for deployment on Render and Vercel. Secrets are held in environment files only; settings edited from the dashboard are protected by an admin token with constant-time comparison and rate limiting, and secrets are write-only." },
    { h3: "6.1.2 Data and Benchmark" },
    { p: "The model system uses IMD RF25 daily rainfall on a 0.25-degree grid [4]. Splits are by time: earlier years train, later years validate and the final years are test years scored once. Eight regions are formed from whole IMD sub-divisions so that no sub-division mixes trained and unseen cells, and two regions are held out entirely. Because no expert error labels exist for the grid, a frozen benchmark corrupts clean data with six fault families (spike, stuck, scale, phantom rain, zeroed and drift), while protected extremes (spatially coherent heavy rain) are never corrupted and ambiguous single-cell extremes are tracked separately." },
    { figure: { file: "fig_region_map.png", w: 250, h: 258, caption: "Figure 6.1: The eight evaluation regions (dashed outlines are held-out regions 3 and 6)" } },
    { h3: "6.1.3 STNet" },
    { p: "A window of consecutive daily rainfall fields is read by STNet. Each cell's spatial neighbourhood is summarised by a convolutional encoder (width 32, 16 features), and temporal memory is carried by a ConvGRU. Seasonal memory is provided by an optional long-range LSTM branch. A **fault head** assigns a score to each cell-day for faults, a **clean head** assigns a score for plausibility, and a **discrimination head** distinguishes between faults and real extremes. The heavy tail of rainfall is handled by a robust input transform. Training weights fault cell-days (positive weight 10), protected extremes (3) and ambiguous extremes (2). The network requires 8.2 GFLOPs per day across the entire grid and has 1,761,769 parameters (6.8 MB)." },
    { h3: "6.1.4 Fusion, Budgets and Protocol" },
    { p: "A logistic layer fuses scores with the untrained rules (or evaluates a boosted variant). The rule is global or per region, and thresholds are set from validation curves to ensure that the flag rate on clean cell-days reaches a specified budget, in this case one per 1,000. Prior to implementation, all evaluation rules are set in stone. For example, budgets are set based solely on validation data, test years are scored once, and each design option is approved or rejected by a predetermined decision rule. A candidate cumulative-sum drift stage was assessed under this discipline against the STNet fault head; it was excluded because it did not adhere to the predetermined rule, maintaining the simplicity of the delivered pipeline." },
    { h3: "6.1.5 Telemetry" },
    { p: "Every run records wall time, process memory, GPU use and energy. Training STNet took 9,172 seconds on a Tesla T4 (GPU energy 165.7 Wh, peak memory 5.3 GB), and inference runs at about 50 days of the full grid per second." },
  ],
});

// -------------------------------------------------------------------------------------------------------- 7
chapters.push({
  title: "Conclusion and Future Enhancements",
  blocks: [
    { h2: "7.1 Result Analysis" },
    { p: "All fault results below are on synthetic faults in the held-out validation years 2013 to 2017 with seed 42. A linear probe on STNet's features separates every fault family from clean data on a next-year test (Figure 7.1), and the detector's recall rises with the size of the fault it must find (Figure 7.2), reaching 0.885 for changes of 20 to 100 mm and 0.896 above 100 mm." },
    { figure: { file: "fig_probe_auc.png", w: 400, h: 207, caption: "Figure 7.1: Separability of fault families from STNet features (AUC, fit 2013, test 2014)" } },
    { figure: { file: "fig_recall_vs_size.png", w: 400, h: 207, caption: "Figure 7.2: Recall at one false alarm per 1,000 clean cell-days against fault size" } },
    { p: "Table 7.1 gives the operating-point results. With the rules and the fault head fused at the 1-per-1,000 budget, the system reaches PR-AUC 0.691 and recall 0.635, with an event recall of 0.619 and an IoU of 0.755, while flagging only 0.6 percent of protected extremes. Across the eight regions the calibrated false-alarm rate lay between 0.56 and 1.80 per 1,000 clean cell-days, each with a 95 percent interval, including the two held-out regions." },
    { table: {
      caption: "Table 7.1: Fused rules + STNet at a budget of 1 per 1,000 (synthetic faults, validation years)",
      cols: [3000, 1170, 1170, 1230, 1230, 1226],
      head: ["Variant", "PR-AUC", "Recall", "Event recall", "False / 1,000", "Protected flagged"],
      rows: [
        ["Rules + fault head (logistic)", "0.691", "0.635", "0.619", "1.27", "0.6%"],
        ["Rules + fault head (boosted)", "0.682", "0.629", "0.573", "0.73", "2.7%"],
        ["Rules + fault + clean heads (boosted)", "0.693", "0.636", "0.608", "1.24", "1.9%"],
        ["Rules + four STNet heads (boosted)", "0.707", "0.644", "0.637", "1.38", "2.3%"],
      ],
    } },
    { p: "A paired comparison with a longer-memory encoder, resampled over whole validation years, improved recall by 3.4 points and PR-AUC by 2.1 points, better in 5 of 5 years, with the largest gains on stuck-gauge faults (recall 0.770 to 0.860) and zeroed faults (event recall 0.282 to 0.366). Strong faults, with a change of 5 mm or more and a wide footprint, are caught with a recall of 0.778 at the budget." },
    { h2: "7.2 Conclusion" },
    { p: "A rigorous input contract, an explainable catalogue of checks with truthful not-run reporting, stored and exportable runs, an explainer seam, a live gauge feed, a station-network view, and a reviewer loop are all features that DataMend offers as part of its comprehensive, reproducible rainfall validation platform. These features are all validated by 569 automated tests. With an AUC ranging from 0.888 to 0.999, its trained layer, STNet, separates six fault families, is small, trains in 2.5 hours on a single GPU, and operates at a declared false-alarm budget while safeguarding real extremes. The contribution of the work is the integration, specifically the layered validation, the separation of extremes from faults, the evidence supporting each flag, and a frozen, honest evaluation." },
    { h2: "7.3 Future Enhancements" },
    { bullets: [
      "Connect the trained score to the platform's score-provider seam and score live gauges against grid neighbours.",
      "Evaluate on expert-reviewed labels for Indian stations as they become available, and add three-seed training.",
      "Connect the AI narrator through the documented contract and add PDF export, Parquet input and per-user accounts.",
      "Add a replay of NOAA ISD India history to the platform and an IMD sub-division lookup.",
      "Add alerting and notifications for operational use.",
    ] },
  ],
});

const references = [
  "V. Chandola, A. Banerjee and V. Kumar, \"Anomaly detection: A survey,\" ACM Computing Surveys, vol. 41, no. 3, art. 15, 2009.",
  "I. Durre, M. J. Menne, B. E. Gleason, T. G. Houston and R. S. Vose, \"Comprehensive automated quality assurance of daily surface observations,\" J. Applied Meteorology and Climatology, vol. 49, no. 8, pp. 1615-1633, 2010.",
  "Y. Sha, D. J. Gagne, G. West and R. Stull, \"Deep-learning-based precipitation observation quality control,\" J. Atmospheric and Oceanic Technology, vol. 38, no. 5, pp. 1075-1091, 2021.",
  "D. S. Pai et al., \"Development of a new high spatial resolution (0.25 x 0.25 degree) long period (1901-2010) daily gridded rainfall data set over India,\" MAUSAM, vol. 65, no. 1, pp. 1-18, 2014.",
  "S. Hochreiter and J. Schmidhuber, \"Long short-term memory,\" Neural Computation, vol. 9, no. 8, pp. 1735-1780, 1997.",
  "K. Cho et al., \"Learning phrase representations using RNN encoder-decoder for statistical machine translation,\" in Proc. EMNLP, 2014, pp. 1724-1734.",
  "United Nations General Assembly, \"Transforming our world: the 2030 Agenda for Sustainable Development,\" A/RES/70/1, 2015.",
  "Weather Union, \"Weather Union API documentation,\" https://www.weatherunion.com/dashboard/, accessed 19 Nov 2026.",
  "NOAA National Centers for Environmental Information, \"Integrated Surface Database (ISD) readme,\" https://www.ncei.noaa.gov/pub/data/noaa/readme.txt.",
  "X. Shi, Z. Chen, H. Wang, D.-Y. Yeung, W.-K. Wong and W.-C. Woo, \"Convolutional LSTM network: A machine learning approach for precipitation nowcasting,\" in Proc. NeurIPS, 2015, pp. 802-810.",
];

module.exports = { TITLE, STUDENTS, GUIDE, GUIDE_DESIG, abstract, keywords, glossary, chapters, references };
