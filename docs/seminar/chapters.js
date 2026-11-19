// Condensed chapters 1-8 of the seminar report (target: about 15-16 pages from Chapter 1).
// Same facts as the longer draft in content.js; every project claim comes from docs/qc-system-spec.md, docs/qc-evaluation-protocol.md,
// CONTEXT.md and the code. Nothing here reports a result that was not produced.
const chapters = [];

chapters.push({
  title: "Introduction",
  blocks: [
    { h2: "1.1 Background and Overview of the Topic" },
    { p: "Weather and climate decisions rest on observations. Rain gauges, automatic weather stations (AWS) and gridded products built from them are used by forecasters, hydrologists, farmers and disaster managers. Observations are not always right: a gauge can jam and repeat one value for weeks, a transmission error can multiply a value by ten, and an interpolation scheme can spread one bad gauge over its neighbours. Finding such errors is **quality control (QC)**, and finding values that do not fit expected behaviour is the wider problem of **anomaly detection** [5]." },
    { p: "An unusual value is not necessarily a wrong one. A very heavy rainfall total may be a real storm, and QC that removes every extreme would erase the events that matter most for flood warning. A useful detector must separate faults from genuine extremes and say how sure it is." },
    { p: "Machine learning can learn normal behaviour from history, but it needs data from many places, and weather data are held by different agencies and regions. Some cannot be redistributed: NOAA's Integrated Surface Database documentation states that non-US data are subject to WMO Resolution 40 restrictions [17]. **Federated learning (FL)** sends the model to the data holders (clients), each trains on its own data, and only parameters are returned and combined [1], [4]. **Personalised** variants keep part of the model on the client, which helps when clients differ [3]." },
    { h2: "1.2 Need and Significance of the Topic" },
    { bullets: [
      "**Data quality limits every downstream use.** Operational QA of daily surface data relies on many fixed rules and manual review [6].",
      "**Weather is regionally heterogeneous.** India spans arid plains, the wet north-east and monsoon coasts, which is the non-IID setting federated methods find difficult [2], [14].",
      "**Data are distributed and sometimes restricted**, so learning has to move to the data.",
      "**False alarms are costly.** Each flag may need human review, so a detector must work at a low, fixed false-alarm rate.",
    ] },
    { h2: "1.3 Applications and Scope" },
    { p: "Federated anomaly detection is relevant to national meteorological services, flood-warning authorities, agricultural advisories and climate archives that need flagged-but-unaltered records. The scope here is limited: the variable studied in detail is **daily rainfall**; the work is a **survey and comparison** with one **case study**, not a new federated algorithm; and the case study is a **simulation** on one machine that makes no privacy claim and reports no result on real data." },
    { h2: "1.4 Motivation" },
    { p: "Most published learning-based QC uses one station, one variable or centralised training, so regional differences are rarely tested. Federated learning has been applied to sensor-fault detection [7] and weather forecasting [8], but not, in the sources checked, to rainfall QC on a gridded national product. India offers a well-documented gridded data set [11], defined meteorological sub-divisions and sharp climate contrasts, so whole regions can be held out to ask whether a detector trained elsewhere works in a region it has never seen." },
    { h2: "1.5 Objectives of the Seminar" },
    { bullets: [
      "Explain weather anomaly detection and federated learning, and why they are combined.",
      "Review conventional, learning-based and federated methods (FedAvg, FedProx, FedPer) and compare published federated approaches.",
      "Identify the research gap and state the problem.",
      "Describe and critically evaluate one framework (DataMend), including its protocol and present status.",
      "Discuss applications and societal, ethical and environmental aspects including the SDGs.",
    ] },
  ],
});

chapters.push({
  title: "Literature Review",
  blocks: [
    { h2: "2.1 Overview of Existing Techniques and Approaches" },
    { p: "Work on weather anomaly detection falls into four families: **rule-based checks** against physical limits, the station's own past and its neighbours; **statistical methods** with robust statistics; **learning-based detectors** that flag large residuals or reconstruction errors; and **federated approaches** that train such detectors across data holders without pooling raw data." },
    { h2: "2.2 Review of Conventional Approaches" },
    { p: "The standard reference for operational QC of daily surface observations is the system applied to GHCN-Daily by Durre and colleagues [6]. It tests duplicates and impossible values, outliers against the station's climatology, internal consistency, persistence of repeated values, spatial comparison with neighbours and checks across elements, validated manually. It flags 0.24 percent of more than 1.5 billion values, as stated in the paper's abstract. Such rules are transparent and cheap, but thresholds are set by hand, a physically consistent wrong pattern can pass, and simple distance-from-the-mean tests suit rainfall poorly because it is zero most of the time and extremely skewed otherwise. A zero-inflated Gamma distribution describes it better, as used in Chapter 4." },
    { p: "The spatial or buddy check compares a station with its neighbours. It catches isolated faults but can mistake genuinely local convective rain for an error, so a disagreement is better treated as a reason for caution than as proof." },
    { h2: "2.3 Review of Recent Techniques and Developments" },
    { p: "Chandola, Banerjee and Kumar [5] organise anomaly detection by data type and learning setting. Recurrent networks such as LSTM [12] and GRU [13] model sequences. Sha and co-authors [10] applied convolutional networks to gridded precipitation and elevation to quality-control gauge data against human labels and reported an AUC of 0.927; spatial context helps, but the study covers one region with centralised training." },
    { p: "McMahan and colleagues introduced Federated Averaging (FedAvg) [1]: clients run local gradient steps and the server averages their parameters, weighted by local data size. With non-IID data, local updates diverge and convergence degrades [4], [14]. **FedProx** [2] adds a proximal term limiting drift from the global model. **FedPer** [3] shares the base layers and keeps the final layers private, which lets a shared representation coexist with region-specific behaviour." },
    { p: "Khan, Saeed and Koo proposed FedLSTM [7] for sensor fault detection, simulating six fault types on temperature data and comparing against federated MLP and 1D-CNN baselines; the faults are synthetic, the variable is not rainfall and there is no spatial context. Chen and colleagues [8] trained a federated transformer with small prompt parameters for weather forecasting across heterogeneous sensors, which shows feasibility but addresses forecasting, not error detection. Liu and colleagues' FedTADBench [9] evaluates five time-series anomaly detectors under four federated methods and shows results depend on the detector and the data distribution." },
    { h2: "2.4 Comparative Analysis of Existing Approaches" },
    { table: {
      caption: "Table 2.1: Comparison of representative approaches (as reported by the cited sources)",
      cols: [1700, 2000, 1700, 1800, 1826],
      head: ["Work", "Task and data", "Method", "Federated?", "Main limitation"],
      rows: [
        ["Durre et al. [6]", "QC of daily surface observations", "Fixed tests, manual validation", "No", "Hand-set thresholds"],
        ["Sha et al. [10]", "Precipitation gauge QC, British Columbia", "CNN ensemble on gridded context", "No", "One region; centralised"],
        ["Khan et al. [7]", "Sensor faults, temperature (synthetic)", "Federated LSTM", "Yes", "Synthetic faults; no spatial context"],
        ["Chen et al. [8]", "Weather forecasting", "Federated transformer, prompts", "Yes", "Forecasting, not detection"],
        ["Liu et al. [9]", "Time-series anomaly benchmark", "5 detectors x 4 FL methods", "Yes", "General series"],
        ["Case study (Ch. 4)", "Gridded rainfall QC, India", "4 components + fusion; 4 FL variants", "Yes (simulated)", "No real-data result yet"],
      ],
    } },
    { h2: "2.5 Summary of Literature Review" },
    { p: "Conventional QC is transparent but hand-tuned; learning-based detectors improve on it with context; federated learning works for sensor faults and forecasting, and personalisation exists for non-IID clients. What the sources checked do not show is federated or personalised learning applied to rainfall QC, evaluated on held-out regions, with explicit protection of genuine extremes. A literature search cannot prove absence, so this is limited to the sources consulted." },
  ],
});

chapters.push({
  title: "Problem Identification and Research Gap",
  blocks: [
    { h2: "3.1 Existing Challenges and Limitations" },
    { bullets: [
      "**No real error labels.** For gridded rainfall over India no expert-reviewed labels or usable historical flags were found, and the product carries no QC flags, so testing relies on deliberate corruption that must be reported as synthetic.",
      "**Heterogeneous regions.** A single model may fit the average climate and fail in extreme regions.",
      "**Genuine versus faulty extremes.** A detector must not learn to treat heavy rain as noise.",
      "**Distributed, restricted data**, with federated costs of communication and client drift.",
    ] },
    { h2: "3.2 Drawbacks of Existing Approaches" },
    { p: "Rule-based systems [6] cannot learn regional behaviour. Centralised learning-based QC [10] assumes data can be pooled and is usually evaluated in one region. Federated fault detection [7] has been shown on temperature with synthetic faults and no spatial context, and federated meteorological work [8] addresses forecasting. Evaluations often report accuracy or AUC, not false alarms per thousand clean observations, detection delay, calibration or the fate of genuine extremes." },
    { h2: "3.3 Identified Research Gaps" },
    { numbered: [
      "Federated and personalised learning for rainfall QC, in the sources consulted.",
      "Evaluation on held-out regions, which tests generalisation to unseen places and not only unseen days.",
      "Explicit protection of genuine extremes, with their false-flag rate as a headline result.",
      "A fixed false-alarm budget chosen on validation data before any test data are scored.",
    ] },
    { h2: "3.4 Problem Statement" },
    { p: "Given daily rainfall fields on a 0.25-degree grid over India, partitioned into regional clients whose raw data stay local, design and evaluate a detector that scores each cell-day for contamination, flags structured faults at a fixed false-alarm budget, does not flag spatially coherent heavy rain, and compare federated, personalised federated, local-only and centralised training, including on regions never seen in training." },
  ],
});

chapters.push({
  title: "Proposed Approach and Conceptual Framework",
  blocks: [
    { h2: "4.1 Overview of the Proposed Approach" },
    { p: "The framework studied is **DataMend**, a rainfall QC system developed as a software project. It scores every cell-day of the IMD gridded daily rainfall (RF25 in the project) for contamination. Four independent components each produce a score, a fusion layer combines them, and two components are neural networks trained in a federated simulation. Statements below describe the design and the code; where something has not run on real data, the text says so." },
    { h2: "4.2 Working Principle and Architecture" },
    { p: "**Data.** RF25 gives daily rainfall from 1901 to 2025 on a 129 by 135 grid at 0.25 degree, 4,964 cells of which are land [11]. It is an inverse-distance interpolation of one to four gauges within 1.5 degrees and carries no QC flags." },
    { p: "**Clients.** Land cells form eight clients, each a union of whole IMD meteorological sub-divisions of 493 to 665 cells, so no sub-division is shared between a trained and an unseen client. Clients 3 (wet north-east) and 6 (west-central) are held out entirely behind a six-cell buffer (Figure 4.1)." },
    { figure: { file: "fig_client_map.png", w: 330, h: 341, caption: "Figure 4.1: The eight federated clients (from the project's saved client map; dashed outlines are held-out clients 3 and 6)" } },
    { figure: { file: "fig_pipeline.png", w: 520, h: 248, caption: "Figure 4.2: The four evidence components and the fusion layer" } },
    { h2: "4.3 Major Components and Modules" },
    { table: {
      caption: "Table 4.1: Components of the DataMend scorer (from the project specification)",
      cols: [1300, 4300, 1900, 1526],
      head: ["Component", "Input", "Output", "Trained?"],
      rows: [
        ["Spatial", "Same-day patch of about six cells, with a hidden disc of radius two cells removed", "Zero-inflated Gamma prediction", "Yes (federated)"],
        ["Temporal", "The cell's own previous 30 days plus season; one-direction GRU; no neighbours", "Zero-inflated Gamma prediction", "Yes (federated)"],
        ["Slow", "Trailing 30- and 90-day totals against the cell's climatology and neighbours (robust z-score)", "Score", "No"],
        ["Rules", "Physical bounds, step checks and existing rule branches", "Score", "No"],
      ],
    } },
    { p: "The hidden disc matters: because the spatial component never sees the target cell or any cell within two cells of it, it cannot copy the value it is meant to check. The temporal component sees only earlier days of the same cell, so no same-day or future information can leak in. Project tests check both properties." },
    { h2: "4.4 Algorithms, Techniques and Modern Tools" },
    { p: "**Rainfall model.** Each trained component predicts a distribution, not a number: the probability of a dry day and, if wet, Gamma parameters. A cell-day whose observed value is very unlikely under it scores high. Rainfall is normalised per client as log(1 + mm) over a scale fitted on that client's training years only, without clipping heavy rain." },
    { p: "**Federated variants.** Each round, the six training clients in a seeded order run one local epoch and the server averages the parameters, weighted by cells, as in FedAvg [1]. The variants are in Table 4.2 and Figure 4.3; FedProx [2] is available as a switch. Rounds are set so total gradient steps equal the centralised run. Each client trains with every other client's cells masked and with targets only from its own cells, which tests verify, together with the rule that held-out years, clients and buffer cells never enter training inputs, statistics or thresholds." },
    { table: {
      caption: "Table 4.2: Federated variants implemented in the project",
      cols: [1700, 3300, 4026],
      head: ["Variant", "What is averaged across clients", "Treatment of an unseen client"],
      rows: [
        ["FedPer (main)", "The body every round; each client keeps its own head and normalisation", "Body plus cell-weighted mean of the heads"],
        ["FedAvg", "All parameters; one global model", "Uses the global model"],
        ["FedAvg + fine-tune", "As FedAvg, then local fine-tuning", "Uses the global model"],
        ["Local-only", "Nothing", "No model: cells left unscored"],
        ["Centralised", "Not federated: all training data pooled", "Reference for comparison"],
      ],
    } },
    { figure: { file: "fig_federated.png", w: 520, h: 285, caption: "Figure 4.3: One federated round of the FedPer variant (simulated sequentially on one machine)" } },
    { p: "**Fusion.** The four scores are standardised and combined by one shared logistic regression, fitted by federated averaging on synthetic faults from 2013 to 2015. Two thresholds are fixed as false-alarm budgets on clean 2016 and 2017 data: a final flag at 1.0 false alarms per 1,000 clean cell-days and a review flag at 5.0, chosen before any test year (2018 to 2025) is scored. The log of the final choice is still to be committed, so these are intended operating points, not results." },
    { p: "**Corruption benchmark.** With no real labels, clean data are deliberately corrupted with nine fault kinds (spike, stuck, scale, phantom rain, zeroed, repeat, drift, edge artefact, combination), each with a single-cell or patch footprint. About one percent of cell-days are corrupted in validation and test benchmarks that are generated once, saved and hashed; some settings appear only in test. Every fault records its mask, kind, strength, footprint and seed." },
    { p: "**Protected and ambiguous extremes.** A protected extreme is a connected group of at least four cells, each above its own heavy-rain threshold (by default the 99th percentile of wet days in training years). It is plausible but unverified, never corrupted, and the share of it that is flagged is a headline metric. An ambiguous extreme is an isolated heavy value, reported separately. **Tools:** Python with PyTorch, xarray and NumPy; YAML configs; each run stores its config, seed, code revision, hashes, metrics and checkpoints." },
    { h2: "4.5 Workflow and Operational Methodology" },
    { numbered: [
      "Validate RF25 against the data contract, then build the client map and time splits (train 1951 to 2012, validation 2013 to 2017, test 2018 to 2025; 1901 to 1950 as an evaluation-only stress test).",
      "Generate and freeze the benchmarks, then compute the untrained scores and metrics.",
      "Train the components, centralised first and then the federated variants; fit the fusion and fix the two budgets.",
      "Score the test years once, including the two unseen clients, and report all metrics with intervals.",
    ] },
    { p: "The headline metric is **recall at the fixed false-alarm budget**. The protocol also reports precision-recall area, false alerts per 1,000 clean cell-days, event recall, footprint overlap, detection delay, calibration and the false-removal rate of protected extremes. ROC AUC is not a headline number, since false alarms matter more than rank statistics when faults are rare. Models run with three seeds, and intervals come from resampling whole years with regions fixed." },
    { h2: "4.6 Operational Prototype with a Live Rain-Gauge Feed" },
    { p: "The project also includes a small real-time path on station data. It reads a public rain-gauge API (Weather Union: 580 catalogued stations in 30 cities, 267 of them rain gauges), polls a cluster of stations within the service's limit of 1,000 calls per day, builds daily totals on the 03 to 03 UTC rain day used by IMD, and scores readings with rules and a neighbour check. This scorer is **not a trained model**, because the grid-trained spatial component needs neighbouring cells a single gauge lacks. The provider does not document the units or reset period of its accumulation field, so raw values are kept and totals are marked unconfirmed [16]. It is tested with a mocked service and has not yet run through a rain event." },
    { h2: "4.7 Expected Advantages" },
    { p: "Regional knowledge stays in local heads and normalisation while the shared body learns common structure; a fixed budget makes alerts manageable; four kinds of evidence reduce blind spots; held-out regions give an honest estimate for places without training data; and raw rainfall need not be pooled, which in the present simulation is a design property only (Section 6.2)." },
  ],
});

chapters.push({
  title: "Comparative Analysis and Discussion",
  blocks: [
    { h2: "5.1 Comparison with Existing Techniques" },
    { table: {
      caption: "Table 5.1: Design comparison of the case study with the surveyed approaches (not a performance comparison)",
      cols: [2300, 1300, 1300, 1300, 1400, 1426],
      head: ["Property", "Rule-based [6]", "CNN QC [10]", "FedLSTM [7]", "MetePFL [8]", "Case study"],
      rows: [
        ["Learns regional behaviour", "No", "Partly", "Partly", "Yes", "Yes (local heads)"],
        ["Raw data pooled", "Yes", "Yes", "No", "No", "No (simulated)"],
        ["Spatial context", "Buddy check", "Yes", "No", "No", "Yes (hidden disc)"],
        ["Held-out regions tested", "No", "No", "No", "Not reported", "Yes (clients 3, 6)"],
        ["Genuine extremes protected", "Partly", "Not reported", "No", "n/a", "Yes (headline)"],
        ["Fixed false-alarm budget", "No", "No", "No", "n/a", "Yes"],
      ],
    } },
    { p: "The works compared use different data, faults and metrics, and the case study has no real-data result yet, so the table shows design differences only." },
    { h2: "5.2 Comparison of the Federated Variants" },
    { table: {
      caption: "Table 5.2: Expected behaviour of the variants (hypotheses from the literature, to be tested; not results)",
      cols: [1500, 2600, 2600, 2326],
      head: ["Variant", "Expected strength", "Expected weakness", "Basis"],
      rows: [
        ["FedPer", "Shared structure plus regional head; should cope with non-IID regions", "Unseen clients get an averaged head", "[3]"],
        ["FedAvg", "Simple; strong if clients are similar", "Client drift when regions differ", "[1], [14]"],
        ["FedAvg + fine-tune", "Adapts the global model per region", "Unseen clients get no adaptation", "[1], [4]"],
        ["Local-only", "Fully adapted; no communication", "Less data per model; no model for unseen regions", "[4]"],
        ["Centralised", "Upper reference", "Pooling may be impossible", "[4]"],
      ],
    } },
    { p: "These are the **hypotheses** the experiments are designed to test. The project's rule is that a claim is made only if its supporting table exists, and none has yet been produced from real data." },
    { h2: "5.3 Implementation Status and Verification Evidence" },
    { table: {
      caption: "Table 5.3: Build status of the case study (from the project specification)",
      cols: [3600, 3600, 1826],
      head: ["Stage", "Status", "Real-data result?"],
      rows: [
        ["Data contract, client map, splits, leakage audit", "Built and tested", "No"],
        ["Corruption benchmark and protected extremes", "Built and tested", "No"],
        ["Spatial and temporal components, fusion", "Built; tiny CPU runs; budget log not yet committed", "No"],
        ["Federated variants", "Built; masking and aggregation tests pass", "No"],
        ["Test scoring, unseen clients, UK real-label study", "Built; generated data only", "No"],
      ],
    } },
    { p: "All QC tests use a small generated rainfall world. On 19 November 2026 the 14 tests of the federated-variant module (aggregation, client masking, matched gradient steps, resume and benchmark-hash checks) passed on a CPU in under three minutes, and the 27 tests of the live-gauge prototype passed with a mocked service. They show the code behaves as specified, not that the method detects real faults, and the report makes no such claim. Still to do on a training machine: a timing run, three-seed training, the budget choice, one test-scoring pass and the paper tables." },
    { h2: "5.4 Performance Parameters and Discussion of Design Choices" },
    { p: "The performance parameters are those of Section 4.5, with recall at the fixed budget as the headline. Four design choices deserve comment. **Whole sub-divisions as clients:** an earlier k-means map split 17 of the 34 sub-divisions across clients, so clients were nested inside sub-divisions to match how meteorologists read regional output. **Hidden disc:** without it a spatial model can copy a neighbour carrying the same interpolated fault. **No novelty claim for the parts:** LSTM or GRU, spatial QC, ensembles, federated learning and personalisation exist already, and the contribution is the combination, the benchmark and the protocol. **Synthetic labels in their own tier:** they are never pooled with results from expert labels, which do not exist for India." },
  ],
});

chapters.push({
  title: "Advantages, Limitations and Discussion of Findings",
  blocks: [
    { h2: "6.1 Advantages" },
    { bullets: [
      "Clients follow actual meteorological sub-divisions, and leakage is guarded by spatial leave-out, time-ordered splits, held-out regions and an automated audit.",
      "Protection of genuine extremes is a measured outcome, and decisions that could bias results (budgets, benchmark, test years) are fixed before test data are scored.",
      "Untrained components (slow and rules) give a transparent fallback and explain flags in physical terms.",
    ] },
    { h2: "6.2 Limitations" },
    { bullets: [
      "**The federated training is a simulation.** All clients run sequentially on one machine, so the system makes no privacy claim; a real deployment raises communication, secure-aggregation and differential-privacy questions [4].",
      "**Synthetic faults only.** Real faults may look different. A separate study with real hand-corrected UK labels is built but not yet run, and its labels come from a neighbour check, so it would carry a circularity caveat.",
      "**RF25 is itself interpolated**, so faults spread across cells and clean-looking fields may hide errors.",
      "**No real-data result exists yet**, so the comparison of the variants is a set of hypotheses.",
      "**The live-gauge prototype is not a trained model**, its provider leaves units and accumulation semantics open, and it has not run through a rain event. The research gap is limited to the sources checked.",
    ] },
    { h2: "6.3 Discussion of Findings from the Literature" },
    { p: "Three points follow. Federated learning is feasible for meteorological sensors, for fault detection [7] and forecasting [8], and benchmarks suggest federated detectors can approach centralised ones in some settings [9]. Non-IID data are the central difficulty [2], [4], [14] and personalisation [3] is the established response, which is why the case study makes it the main variant. And weather-QC literature rarely reports false alarms per thousand clean observations or the fate of genuine extremes, so a protocol that makes them headline metrics is a contribution to evaluation regardless of how the models turn out." },
  ],
});

chapters.push({
  title: "Applications, Challenges and Future Scope",
  blocks: [
    { h2: "7.1 Real-World Applications" },
    { p: "Screening national rainfall grids and station networks with human review of alerts; pre-processing for flood, drought and crop models, where undetected phantom or zeroed rainfall biases outcomes; collaboration between agencies that cannot share observations; and near-real-time monitoring of low-cost gauge networks, as in Section 4.6." },
    { h2: "7.2 Technical and Practical Challenges" },
    { p: "Absence of labelled errors; non-IID clients and client drift [14]; communication cost and unreliable clients in a real deployment; distribution shift as networks are modernised and gauge density changes; telling a record-breaking storm from a fault; and data licensing, since some meteorological data may not be redistributed [17]." },
    { h2: "7.3 Societal, Ethical and Environmental Impact, including the SDGs" },
    { p: "**Society.** Reliable rainfall data support early warning, agriculture and water management. Unnoticed errors can cause wrong warnings, while wrongly removing a genuine extreme could hide a dangerous event, so the framework flags for review and never overwrites observations." },
    { p: "**Ethics.** (i) *Privacy:* federated learning keeps data with its owner, but exchanged parameters can still leak information, so a privacy claim needs formal mechanisms that this study does not include and does not make. (ii) *Fairness:* a model trained mainly on data-rich regions may serve sparse regions poorly, hence the separate evaluation of held-out regions. (iii) *Transparency:* every flag carries its component scores and synthetic results are labelled as such. (iv) *Responsibility:* missed faults and false alarms have different costs, so the budget is explicit and chosen in advance." },
    { p: "**Environment.** Training consumes electricity. The framework uses small networks, untrained components where they suffice and a cap on training time per run. Federated learning can reduce data transfer, though repeated parameter exchange has its own cost. The work relates to the Sustainable Development Goals [15] as shown in Table 7.1." },
    { table: {
      caption: "Table 7.1: Relation to the Sustainable Development Goals",
      cols: [2700, 6326],
      head: ["Goal", "How the topic relates"],
      rows: [
        ["SDG 13: Climate Action", "Trustworthy observations underpin climate monitoring, early warning of extreme rainfall and adaptation planning."],
        ["SDG 9: Industry, Innovation and Infrastructure", "More reliable observation infrastructure, using a recent machine learning approach."],
        ["SDG 11: Sustainable Cities and Communities", "Better rainfall data improve urban flood warning and drainage planning."],
        ["SDG 2: Zero Hunger", "Agricultural advisories depend on correct rainfall records."],
        ["SDG 17: Partnerships for the Goals", "Federated learning lets institutions collaborate without handing over raw data."],
      ],
    } },
    { h2: "7.4 Emerging Trends" },
    { p: "Federated foundation models for meteorological data with parameter-efficient prompts [8]; personalised federated learning and federated benchmarks for time-series anomaly detection [3], [9]; calibrated alerts with formal false-alarm control; and combining gauges, radar and satellite estimates as further evidence." },
    { h2: "7.5 Future Research Directions" },
    { numbered: [
      "Run the pipeline on real RF25 data, produce the planned tables and report which hypotheses of Table 5.2 hold.",
      "Run the real-label UK study and report it separately from the India study.",
      "Move from simulation to a real distributed setting, quantify communication cost and add secure aggregation if privacy is to be claimed.",
      "Verify the live-gauge units, build a longer history per station and evaluate on recorded rain events; add a reviewer feedback loop with a monitored shadow period.",
    ] },
  ],
});

chapters.push({
  title: "Conclusion",
  blocks: [
    { h2: "8.1 Summary of the Seminar" },
    { p: "The seminar examined weather anomaly detection with federated learning. Conventional QC is transparent but rule-bound; learning-based detectors exploit spatial and temporal context; federated learning with FedAvg, FedProx and FedPer lets data holders train a shared model without pooling raw data and, with personalisation, copes with regional differences. Published work covers federated sensor-fault detection and weather forecasting, but in the sources checked not federated or personalised rainfall QC with held-out regions and protection of genuine extremes. The case study, DataMend, turns that gap into a design: eight clients of whole IMD sub-divisions, four evidence components, a fused score at fixed false-alarm budgets, a corruption benchmark, protected extremes and four federated variants compared with centralised training, including on two unseen regions." },
    { h2: "8.2 Key Learnings and Observations" },
    { bullets: [
      "The evaluation protocol and leakage controls matter as much as the model.",
      "Heterogeneity between clients, not data volume, makes federated weather learning hard, and personalisation is the main tool against it.",
      "A detector is judged by its false alarms and its effect on genuine extremes, not by accuracy, and an honest statement of status is part of a defensible study.",
    ] },
    { h2: "8.3 Conclusion" },
    { p: "Federated learning is a suitable framework for weather anomaly detection where data are distributed and regions differ. The case study offers an implemented, tested design and a fixed evaluation protocol. Whether the personalised federated variant matches centralised training and holds up on unseen regions is what the run on real data must answer; until then the conclusions concern the design and the literature, not measured performance." },
  ],
});

module.exports = { chapters };
