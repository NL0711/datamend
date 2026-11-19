// Text content of the seminar report. Every claim about the project is taken from docs/qc-system-spec.md,
// docs/qc-evaluation-protocol.md, CONTEXT.md and the code; nothing here reports a result that was not produced.
// Markup: **bold**. Block types: p, bullets, table, figure, eq, h2, h3.

const TITLE = "Weather Anomaly Detection Using Federated Learning";
const STUDENT = "Nathasha Lewis";
const ROLL = "10257";
const GUIDE = "Prof. Jagruti N.";
const GUIDE_DESIG = ""; // not provided; the cover omits the line when empty

const abstract = [
  "Automatic weather stations and gridded rainfall products feed forecasting, flood warning, agriculture and climate research, yet they contain faulty values: stuck sensors, spikes, scaling errors, phantom rain and drifting gauges. Detecting such errors is called quality control (QC). A model that learns what normal weather looks like can flag faulty values, but weather is different in every region, and the observations of different agencies or regions often cannot be pooled in one place. Federated learning (FL) trains one model across several data holders by exchanging model parameters instead of raw data, and personalised variants let each holder keep part of the model local.",
  "This seminar studies weather anomaly detection with federated learning. It surveys conventional quality-control practice, deep-learning-based detectors and the federated methods FedAvg, FedProx and FedPer, and it compares published work on federated fault detection for sensors and federated learning for meteorological data. The survey shows that federated learning has been applied to sensor-fault detection and to weather forecasting, but that, in the sources checked, federated or personalised learning for rainfall quality control has not been reported.",
  "As a case study the report describes DataMend, a rainfall QC system for the 0.25-degree IMD daily rainfall grid over India. It treats eight groups of whole IMD meteorological sub-divisions as federated clients, combines four evidence components (spatial, temporal, slow-baseline and rules) through a logistic fusion layer, protects spatially coherent heavy rain from being flagged, and compares four federated variants (FedPer, FedAvg, FedAvg with fine-tuning and local-only) against centralised training, including on two regions never seen in training. The report is explicit about status: the system is implemented and unit-tested on generated data, the federated training is a simulation on one machine that makes no privacy claim, and no result on real data has been produced yet. The report closes with applications, ethical and sustainability aspects and future work.",
];

const keywords = "Anomaly detection, quality control, federated learning, personalisation, rainfall, automatic weather station, IMD.";

const glossary = [
  ["AWS", "Automatic Weather Station."],
  ["ARG", "Automatic Rain Gauge."],
  ["Client", "In this report, a fixed group of grid cells (whole IMD sub-divisions) that trains locally."],
  ["FedAvg", "Federated Averaging: the server averages client model parameters, weighted by data size."],
  ["FedPer", "Federated learning with personalisation layers: shared body, private head."],
  ["FedProx", "FedAvg with a proximal term that limits how far local training drifts from the global model."],
  ["FL", "Federated Learning."],
  ["GRU", "Gated Recurrent Unit, a recurrent neural network."],
  ["IMD", "India Meteorological Department."],
  ["LSTM", "Long Short-Term Memory network."],
  ["MAD", "Median Absolute Deviation, a robust measure of spread."],
  ["Non-IID", "Data that are not independent and identically distributed across clients."],
  ["Protected extreme", "A connected group of cells all above their own heavy-rain threshold, treated as plausible and never corrupted in the benchmark."],
  ["QC", "Quality Control."],
  ["RF25", "IMD's 0.25-degree gridded daily rainfall data set for India."],
  ["SDG", "Sustainable Development Goal."],
  ["WMO", "World Meteorological Organization."],
];

// ---------------------------------------------------------------------------------------------- chapters
const chapters = [];

chapters.push({
  title: "Introduction",
  blocks: [
    { h2: "1.1 Background and Overview of the Topic" },
    { p: "Weather and climate decisions rest on observations. Rain gauges, automatic weather stations (AWS) and gridded products built from them tell forecasters, hydrologists, farmers and disaster managers how much rain has fallen and where. Observations are not always right. A gauge can jam and report the same value for weeks, a transmission error can multiply a value by ten, a logger can write zeros during a fault, and an interpolation scheme can spread one bad gauge over its neighbours. Detecting such errors before the data are used is the task of **quality control (QC)**, and detecting values that do not fit the expected behaviour of the weather is the more general problem of **anomaly detection** [5]." },
    { p: "The difficulty is that an unusual value is not necessarily a wrong value. A very heavy rainfall total may be a real storm. Quality control that removes every extreme would erase exactly the events that matter most for flood warning and climate records. A useful detector therefore has to separate sensor and data faults from genuine meteorological extremes, and it has to say how sure it is." },
    { p: "Machine learning can model what normal behaviour looks like from history, for example by predicting a value from its neighbours or from its own past and flagging large disagreements. Learning such a model needs data from many places. In practice, weather data are held by different agencies, networks and regions. Some of the data cannot be redistributed: the documentation of NOAA's Integrated Surface Database, for example, states that non-US data are subject to WMO Resolution 40 restrictions and cannot be redistributed to other users [17]. Climate also differs strongly between regions, so a model fitted in one place does not transfer cleanly to another." },
    { p: "**Federated learning (FL)** addresses the first problem. Instead of collecting data in one location, a coordinating server sends a model to the data holders (the clients), each client trains it on its own data, and only model parameters are sent back and combined [1], [4]. **Personalised** variants keep part of the model on the client, which helps when the clients' data differ [3]. This seminar examines how these ideas apply to weather anomaly detection." },
    { h2: "1.2 Need and Significance of the Topic" },
    { bullets: [
      "**Data quality limits every downstream use.** Forecast verification, flood models and climate trend studies inherit the errors of the observations they use. The main operational quality-assurance systems for daily surface data rely on a long list of fixed rules and manual review [6].",
      "**Weather is regionally heterogeneous.** India spans arid western plains, the heavy-rain north-east and the monsoon coasts. The statistics of rain in each region differ, which is the situation federated methods call non-IID data [2], [14].",
      "**Data are distributed and sometimes restricted.** Observations are collected by different agencies and networks. Where data cannot be pooled, learning has to move to the data.",
      "**False alarms are costly.** Every flag may need human review. A detector that raises too many alerts will be ignored, and one that removes genuine extremes damages the record.",
    ] },
    { h2: "1.3 Applications and Scope" },
    { p: "Federated anomaly detection for weather data is relevant to national meteorological services checking station networks, to river-basin and flood-warning authorities, to agricultural advisories that use gridded rainfall, and to climate data archives that need flagged-but-not-altered records. The scope of this seminar is limited in the following ways." },
    { bullets: [
      "The variable studied in detail is **daily rainfall**. Temperature, pressure and humidity detectors exist in the literature and are mentioned for comparison only.",
      "The study is a **survey and comparison** of published work together with a **case study** of one implemented system. It is not a new federated algorithm.",
      "The case-study system is a **simulation** of federated training on one machine. It makes no privacy claim, and no result on real data is reported.",
    ] },
    { h2: "1.4 Motivation" },
    { p: "Three observations motivate the topic. First, most published learning-based QC work uses a single station, a single variable or centralised training, so the effect of region-to-region differences is rarely tested. Second, federated learning has been applied to sensor fault detection [7] and to weather forecasting [8], which suggests the idea is feasible for meteorological data, but those works do not address rainfall QC on a gridded national product. Third, India's rainfall record is a natural testbed: it has a well-documented gridded data set [11], clearly defined meteorological sub-divisions and sharp climatic contrasts. Holding out whole regions makes it possible to ask a direct question: does a detector trained elsewhere work in a region it has never seen?" },
    { h2: "1.5 Objectives of the Seminar" },
    { bullets: [
      "To explain weather anomaly detection and federated learning, and why the two are combined.",
      "To review conventional and learning-based quality control, and the main federated methods (FedAvg, FedProx, FedPer).",
      "To compare published federated approaches for sensor faults and meteorological data.",
      "To identify the research gap and state a precise problem.",
      "To describe and critically evaluate a concrete framework (DataMend) for federated rainfall anomaly detection, including its evaluation protocol and its present status.",
      "To discuss applications, limitations, and societal, ethical and environmental aspects including the Sustainable Development Goals.",
    ] },
  ],
});

chapters.push({
  title: "Literature Review",
  blocks: [
    { h2: "2.1 Overview of Existing Techniques and Approaches" },
    { p: "Work on weather anomaly detection can be grouped into four families. **Rule-based checks** compare each value with physical limits, with its own recent past and with neighbouring stations. **Statistical methods** model the normal range of a value, often with robust statistics. **Learning-based detectors** train a neural or tree-based model on normal behaviour and flag large residuals or reconstruction errors. **Federated approaches** train such detectors across several data holders without pooling the raw data. The sections below follow this order." },
    { h2: "2.2 Review of Conventional Approaches" },
    { p: "The standard reference for operational QC of daily surface observations is the automated quality-assurance system applied to the Global Historical Climatology Network-Daily data set by Durre and colleagues [6]. It applies a sequence of tests to daily temperature, precipitation, snowfall and snow depth: duplicate and impossible values, outliers against the station's own climatology, internal consistency between related elements, temporal persistence of repeated values, spatial comparison with neighbouring stations, and checks across elements. The authors validated the checks manually, and the system flags a very small share of all values (0.24 percent of more than 1.5 billion values, as reported in the paper's abstract)." },
    { p: "Such rule-based systems have strong advantages. They are transparent, each flag has a stated reason, and they run cheaply. Their weaknesses are that thresholds are set by hand, that a single rule cannot recognise a physically consistent but wrong pattern, and that setting thresholds usually relies on manual review of false positives rather than on a calibrated false-alarm rate. For rainfall, which is zero most of the time and extremely skewed when it is not, simple distance-from-the-mean tests are especially weak. Rainfall is better described by a zero-inflated distribution such as a Gamma distribution with a point mass at zero, which is the approach adopted in the case study of Chapter 4." },
    { p: "Another conventional ingredient is the spatial or buddy check, which compares a station with its neighbours. It is effective against isolated faults, but it can mistake genuinely local convective rain for an error. Consequently a disagreement with neighbours is better treated as a reason for caution than as proof of a fault." },
    { h2: "2.3 Review of Recent Techniques and Developments" },
    { h3: "2.3.1 Learning-based anomaly detection" },
    { p: "Chandola, Banerjee and Kumar's survey [5] organises anomaly detection by the nature of the data and the learning setting. The setting relevant here is one in which only normal data, or data with few labels, are available. Recurrent networks such as LSTM [12] and GRU [13] model sequences and are used both to predict the next value and to reconstruct a window. Sha and co-authors [10] applied convolutional neural networks to gridded precipitation and elevation fields to quality-control gauge observations against human QC labels, and reported an area under the ROC curve of 0.927 for their ensemble. Their work shows that spatial context from a gridded product helps, but it is a single-region study with centralised training." },
    { h3: "2.3.2 Federated learning" },
    { p: "McMahan and co-authors introduced Federated Averaging (FedAvg) [1]. In each round the server selects clients, each client runs several steps of stochastic gradient descent on its local data, and the server replaces the global parameters with the average of the clients' parameters, weighted by the number of local examples. FedAvg works well when client data are similar, but when they are not (non-IID data), local updates pull in different directions and convergence slows or degrades; this problem is documented in the surveys of Li and colleagues [14] and of Kairouz and colleagues [4]." },
    { p: "**FedProx** [2] adds a proximal term to the local objective, penalising the distance between the local and the global parameters, and tolerates different amounts of local work on different clients. **FedPer** [3] takes a different route: the network is split into base layers, which are shared and averaged, and personalisation layers, which stay private on each client and are trained only on local data. For weather data, where each region has its own statistics, keeping a local final layer lets a shared representation coexist with region-specific behaviour." },
    { h3: "2.3.3 Federated learning for sensor faults and weather" },
    { p: "Khan, Saeed and Koo proposed FedLSTM [7], a federated LSTM framework for sensor fault detection in wireless sensor networks. Because no public data set contains labelled sensor faults, they simulated six fault types (bias, drift, spike, erratic, stuck and data loss) on temperature data, and compared the federated LSTM against federated MLP and one-dimensional CNN baselines, also varying client participation and local epochs. Their result supports the feasibility of federated fault detection, but the faults are synthetic, the data are temperature rather than rainfall, and there is no gridded or spatial context." },
    { p: "Chen and colleagues proposed prompt federated learning for weather forecasting [8], in which a transformer-based model is trained across sensors holding multivariate meteorological series and low-resource sensors exchange only small prompt parameters to reduce communication. This shows that federated training across heterogeneous meteorological sensors is workable, but the task is forecasting, not error detection." },
    { p: "Liu and colleagues released FedTADBench [9], a benchmark that evaluates five time-series anomaly detection algorithms under four federated learning methods. It documents that federated detectors can approach centralised ones but that results depend on the algorithm and on how data are distributed among clients." },
    { h2: "2.4 Comparative Analysis of Existing Approaches" },
    { table: {
      caption: "Table 2.1: Comparison of representative approaches (as reported by the cited sources)",
      cols: [1700, 2000, 1700, 1800, 1826],
      head: ["Work", "Task and data", "Method", "Federated?", "Main limitation"],
      rows: [
        ["Durre et al. [6]", "QC of daily surface observations (GHCN-Daily)", "Large set of fixed tests, manual validation", "No", "Hand-set thresholds; rules only"],
        ["Sha et al. [10]", "Precipitation gauge QC, British Columbia", "CNN ensemble on gridded precipitation and elevation", "No", "One region; human labels; centralised"],
        ["Khan et al. [7]", "Sensor fault detection, temperature (synthetic faults)", "Federated LSTM vs MLP, 1D-CNN", "Yes", "Synthetic faults; no spatial context; not rainfall"],
        ["Chen et al. [8]", "Weather forecasting, multivariate sensors", "Federated transformer with prompts", "Yes", "Forecasting, not error detection"],
        ["Liu et al. [9]", "Benchmark of time-series anomaly detection", "5 detectors x 4 FL methods", "Yes", "General time series, not weather QC"],
        ["Case study (Ch. 4)", "Gridded daily rainfall QC, India", "Four components + fusion; FedPer, FedAvg, FedFT, local", "Yes (simulated)", "No real-data result yet"],
      ],
    } },
    { h2: "2.5 Summary of Literature Review" },
    { p: "Conventional QC is transparent but relies on hand-set rules. Learning-based detectors improve on it when spatial or temporal context is used. Federated learning has been shown to work for sensor fault detection and for weather forecasting, and personalisation methods exist for non-IID clients. What the surveyed sources do not show, as far as the sources checked for this report go, is federated or personalised learning applied to rainfall quality control, evaluated on regions that were held out of training, with protection for genuine extremes. A search of the literature can never prove absence, so this statement is limited to the sources consulted." },
  ],
});

chapters.push({
  title: "Problem Identification and Research Gap",
  blocks: [
    { h2: "3.1 Existing Challenges and Limitations" },
    { bullets: [
      "**No real error labels.** For gridded rainfall over India no expert-reviewed error labels or usable historical flags were found. The IMD gridded product itself carries no QC flags. Detectors can only be tested on deliberately corrupted data, which must always be reported as synthetic.",
      "**Heterogeneous regions.** One global model may fit the average climate and fail in extreme regions. A model trained everywhere cannot show whether it generalises to a new region.",
      "**Genuine versus faulty extremes.** Heavy rain is rare and valuable. A detector must not learn to treat it as noise.",
      "**Distributed and restricted data.** Pooling data may be legally or practically impossible, and federated learning introduces its own cost: communication rounds and client drift.",
      "**Operating cost of false alarms.** A detector must be evaluated at a fixed, low false-alarm rate, not by accuracy.",
    ] },
    { h2: "3.2 Drawbacks of Existing Approaches" },
    { bullets: [
      "Rule-based systems [6] use fixed thresholds and cannot learn regional behaviour.",
      "Centralised learning-based QC [10] assumes all data can be pooled and is usually evaluated in one region.",
      "Federated fault detection [7] has been shown on temperature with synthetic faults, without spatial context.",
      "Federated meteorological work [8] addresses forecasting rather than error detection.",
      "Reported evaluations often give accuracy or AUC and do not report false alarms per thousand clean observations, detection delay, calibration or the fate of genuine extremes.",
    ] },
    { h2: "3.3 Identified Research Gaps" },
    { numbered: [
      "Federated and personalised learning for **rainfall** quality control, in the sources consulted.",
      "Evaluation on **held-out regions**, which tests generalisation to places unseen in training rather than only to unseen days.",
      "**Explicit protection of genuine extremes**, with their false-flag rate reported as a headline result.",
      "A **fixed false-alarm budget** chosen on validation data before any test data are scored, so that reported recall is an operating-point result.",
    ] },
    { h2: "3.4 Problem Statement" },
    { p: "Given daily rainfall fields on a 0.25-degree grid over India, partitioned into regional clients whose raw data stay local, design and evaluate a detector that assigns each cell-day a calibrated score of contamination, flags structured faults at a fixed false-alarm budget, does not flag spatially coherent heavy rain, and compare federated, personalised federated, local-only and centralised training, including on regions never seen in training." },
  ],
});

chapters.push({
  title: "Proposed Approach and Conceptual Framework",
  blocks: [
    { h2: "4.1 Overview of the Proposed Approach" },
    { p: "The framework studied here is **DataMend**, a rainfall QC system developed as a software project. It scores every cell-day of the IMD gridded daily rainfall (called RF25 in the project) for contamination. Four independent sources of evidence, called components, each produce a score, and a fusion layer combines them. Two of the components are neural networks trained in a federated simulation. The approach is built around the gap identified in Chapter 3: regional clients, held-out regions, protected extremes and fixed false-alarm budgets." },
    { p: "Throughout this chapter and the next, statements about what the system does describe the design and the code. Where something has not been run on real data, the text says so." },
    { h2: "4.2 Working Principle and Architecture" },
    { p: "**Data.** RF25 provides daily rainfall from 1901 to 2025 on a grid of 129 by 135 cells at 0.25 degree, of which 4,964 are land cells [11]. The product is an inverse-distance interpolation of one to four gauges within 1.5 degrees, and carries no QC flags." },
    { p: "**Clients.** The land cells are divided into eight clients. Each client is a union of whole IMD meteorological sub-divisions, between 493 and 665 cells in size, so that no sub-division is shared between a trained and an unseen client. Two clients are held out entirely: client 3 (the wet north-east) and client 6 (west-central India), separated from the rest by a six-cell buffer. Figure 4.1 shows the saved map." },
    { figure: { file: "fig_client_map.png", w: 400, h: 413, caption: "Figure 4.1: The eight federated clients over India (from the project's saved client map; dashed outlines are the held-out clients 3 and 6)" } },
    { p: "**Components.** Figure 4.2 shows the four components." },
    { figure: { file: "fig_pipeline.png", w: 560, h: 267, caption: "Figure 4.2: The four evidence components and the fusion layer" } },
    { h2: "4.3 Major Components and Modules" },
    { table: {
      caption: "Table 4.1: Components of the DataMend scorer (from the project specification)",
      cols: [1500, 2900, 2300, 2326],
      head: ["Component", "Input", "Output", "Trained?"],
      rows: [
        ["Spatial", "Same-day patch of about six cells around the target, with a hidden disc of radius two cells removed", "Zero-inflated Gamma prediction for the cell", "Yes (federated)"],
        ["Temporal", "The cell's own previous 30 days plus season and climatology; one-direction GRU; no neighbours", "Zero-inflated Gamma prediction", "Yes (federated)"],
        ["Slow", "Trailing 30- and 90-day totals against the cell's own climatology and surrounding cells (robust z-score)", "Score", "No"],
        ["Rules", "Physical bounds, step checks and existing rule branches", "Score", "No"],
      ],
    } },
    { p: "The hidden disc is essential. Because the spatial component never sees the target cell or any cell within two cells of it, its prediction cannot copy the value it is meant to check, and a fault wider than the disc is only partly visible to it. The temporal component sees only earlier days of the same cell, so no same-day or future information can leak into its prediction. Tests in the project check both properties." },
    { h2: "4.4 Algorithms, Techniques and Modern Tools" },
    { h3: "4.4.1 Zero-inflated Gamma model of rainfall" },
    { p: "Daily rainfall is zero on many days and strongly skewed on the others. Each trained component therefore predicts a distribution rather than a single number: the probability that the day is dry, and, if wet, the parameters of a Gamma distribution. A cell-day whose observed value is very unlikely under this predicted distribution receives a high score. Rainfall is normalised per client as log(1 + mm) divided by a scale fitted on that client's training years only, and the transform does not clip heavy rain." },
    { h3: "4.4.2 Federated training variants" },
    { p: "The server and clients follow the round structure of FedAvg [1]. In round t each of the six training clients, in a seeded order, runs one local epoch, and the server forms the new parameters as a weighted average of the client parameters, with weights proportional to the client's number of cells. The project compares four variants, with FedProx [2] available as a switch." },
    { table: {
      caption: "Table 4.2: Federated variants implemented in the project",
      cols: [1500, 3300, 4226],
      head: ["Variant", "What is averaged across clients", "Treatment of an unseen client"],
      rows: [
        ["FedPer (main)", "The body of the network every round; each client keeps its own final layer (head) and its own normalisation", "Receives the body and the cell-weighted mean of the clients' heads"],
        ["FedAvg", "All parameters every round; one global model", "Uses the global model"],
        ["FedAvg + fine-tune", "As FedAvg, then each training client fine-tunes the global model for a few steps on its own cells", "Uses the global model"],
        ["Local-only", "Nothing; each client trains alone", "No model: its cells are left unscored rather than given another client's model"],
        ["Centralised", "Not federated: one model on all training clients' data", "Used as the reference for the comparison"],
      ],
    } },
    { figure: { file: "fig_federated.png", w: 560, h: 307, caption: "Figure 4.3: One federated round of the FedPer variant (simulated sequentially on one machine)" } },
    { p: "The number of rounds is set so that the total number of gradient steps equals that of the centralised run, which keeps the comparison fair. Each client trains with every other client's cells masked as missing in the input, and with targets only from its own cells. This masking is verified by tests, which assert that exactly one client is readable in each local step and that held-out years, held-out clients and buffer cells never enter training inputs, statistics or thresholds." },
    { h3: "4.4.3 Fusion layer" },
    { p: "The four scores are standardised and combined by a single shared logistic regression, fitted by federated averaging on synthetic faults from the validation years 2013 to 2015. Two thresholds are then fixed as **false-alarm budgets** on clean data from 2016 and 2017: a final flag at 1.0 false alarms per 1,000 clean cell-days and a review flag at 5.0. These operating points were chosen before any test-year data (2018 to 2025) is scored, and the project records them in its evaluation protocol; the log of the final choice is still to be committed, so the figures are the intended operating points, not reported results." },
    { h3: "4.4.4 Corruption benchmark" },
    { p: "Because real labels do not exist for India, evaluation uses a benchmark in which clean data are deliberately corrupted. Nine fault kinds are generated: spike, stuck, scale, phantom rain, zeroed, repeat, drift or bias, edge artefact, and combinations. A footprint is chosen independently of the kind: either a single cell or a patch of 1.5 to 6 cells radius, roughly half each. About one percent of cell-days are corrupted in the frozen validation and test benchmarks, which are generated once, saved and hashed so that every run scores the same data. Some settings (the repeat and edge kinds, the largest footprints, the weakest strengths and the test seeds) appear only in the test benchmark. Every fault records its exact mask, kind, strength, footprint and seed." },
    { h3: "4.4.5 Protected and ambiguous extremes" },
    { p: "A **protected extreme** is a connected group of at least four cells, using eight-neighbour connectivity, in which every cell exceeds its own heavy-rain threshold (by default the cell's 99th percentile of wet days in the training years). It is labelled plausible but unverified and is never corrupted. The share of protected cell-days that the detector flags is a headline metric. An **ambiguous extreme** is a heavy value at one isolated cell with ordinary rain around it. It is neither protected nor an error, and is reported on its own." },
    { h3: "4.4.6 Tools" },
    { p: "The system is written in Python with PyTorch for the neural networks, xarray and NumPy for the gridded data, and YAML configurations that fix splits, seeds and benchmark. Each run stores its configuration, seed, code revision, split and client-map hashes, metrics and checkpoints, and can resume from the last checkpoint. Two compute profiles are provided, for a two-GPU notebook environment and for a single GPU." },
    { h2: "4.5 Workflow and Operational Methodology" },
    { numbered: [
      "Read and validate RF25 against the data contract (grid, units, fill value).",
      "Build the client map from whole IMD sub-divisions and the time splits: train 1951 to 2012, validation 2013 to 2017, test 2018 to 2025, with 1901 to 1950 kept only as an evaluation stress test for an older and sparser network.",
      "Generate and freeze the corruption benchmarks.",
      "Compute the untrained scores (rules, slow component, neighbour-average baseline) and the metrics.",
      "Train the spatial and temporal components, centralised first, then the federated variants.",
      "Fit the fusion, draw validation curves and fix the two false-alarm budgets.",
      "Score the test years once with the fixed budgets, including the two unseen clients, and report all metrics with intervals.",
    ] },
    { h2: "4.6 Evaluation Protocol" },
    { p: "To avoid the usual leakage in temporal data, training uses only earlier years, validation later years and testing the latest years. The headline metric is **recall at the fixed false-alarm budget**, the share of fault cell-days that carry a final flag. The protocol also reports the area under the precision-recall curve, false alerts per 1,000 clean cell-days, event recall, footprint overlap (intersection over union), detection delay for stuck, repeat and drift faults, calibration (reliability plot and expected calibration error) and the false-removal rate of protected extremes. ROC AUC is deliberately not a headline number, since false alarms matter more than rank statistics when faults are rare. Each trained model is run with three seeds and reported as mean and range, and confidence intervals come from resampling whole years with the regions fixed." },
    { h2: "4.7 Operational Prototype with a Live Rain-Gauge Feed" },
    { p: "Besides the gridded study, the project includes a small operational path to show real-time operation on station data. It reads a public rain-gauge API (Weather Union, a free service with 580 catalogued stations in 30 cities of which 267 are rain gauges), polls a cluster of stations in one city within the service's limit of 1,000 calls per day, builds daily totals on the 03 UTC to 03 UTC rain day used by IMD, and scores each reading using rules and a neighbour check. This scorer is **not a trained model**, and is labelled as such, because the grid-trained spatial component needs a field of neighbouring cells that a single gauge does not provide. The provider's documentation does not state the units or reset period of its accumulation field, so the prototype keeps raw values, treats the accumulation mode as an explicit setting and marks all totals as unconfirmed [16]. The prototype is covered by automated tests that use a mocked service; it has not yet been run through a rain event." },
    { h2: "4.8 Expected Advantages" },
    { bullets: [
      "Regional knowledge is kept in local heads and normalisation, while the shared body learns common structure.",
      "A fixed false-alarm budget makes alerts operationally manageable.",
      "Four different kinds of evidence reduce the chance that one blind spot passes a fault.",
      "Held-out regions give an honest estimate of how the method would behave in a region without training data.",
      "Raw rainfall never needs to be pooled for training, which is the property federated learning is chosen for; in the present simulation this is a design property only (see Section 6.2).",
    ] },
  ],
});

chapters.push({
  title: "Comparative Analysis and Discussion",
  blocks: [
    { h2: "5.1 Comparison with Existing Techniques" },
    { table: {
      caption: "Table 5.1: Design comparison of the case study with the surveyed approaches",
      cols: [2300, 1300, 1300, 1300, 1400, 1426],
      head: ["Property", "Rule-based QC [6]", "CNN QC [10]", "FedLSTM [7]", "MetePFL [8]", "Case study"],
      rows: [
        ["Learns regional behaviour", "No", "Partly", "Partly", "Yes", "Yes (local heads)"],
        ["Raw data pooled", "Yes", "Yes", "No", "No", "No (simulated)"],
        ["Spatial context", "Buddy check", "Yes", "No", "No", "Yes (hidden disc)"],
        ["Held-out regions tested", "No", "No", "No", "Not reported here", "Yes (clients 3, 6)"],
        ["Genuine extremes protected explicitly", "Partly", "Not reported", "No", "n/a", "Yes (headline metric)"],
        ["Fixed false-alarm budget", "No", "No", "No", "n/a", "Yes"],
        ["Task", "QC", "QC", "Fault detection", "Forecasting", "QC"],
      ],
    } },
    { p: "The comparison shows design differences only. It is not a performance comparison: the compared works use different data, faults and metrics, and the case study has no real-data result yet." },
    { h2: "5.2 Comparison of the Federated Variants" },
    { table: {
      caption: "Table 5.2: Expected behaviour of the variants (hypotheses from the literature, to be tested; not results)",
      cols: [1500, 2500, 2500, 2526],
      head: ["Variant", "Expected strength", "Expected weakness", "Basis"],
      rows: [
        ["FedPer", "Shared structure plus regional head; should cope with non-IID regions and unseen clients", "Unseen clients get an averaged head, which may not fit their climate", "[3]"],
        ["FedAvg", "Simple, one model for all; strong if clients are similar", "Client drift when regions differ strongly", "[1], [14]"],
        ["FedAvg + fine-tune", "Adapts the global model to each training region", "Extra local training; unseen clients get no adaptation", "[1], [4]"],
        ["Local-only", "Fully adapted to its own region; needs no communication", "Less data per model; no model for unseen regions", "[4]"],
        ["Centralised", "Upper reference when pooling is possible", "Pooling may be impossible in practice", "[4]"],
      ],
    } },
    { p: "These expectations come from the cited literature and are the **hypotheses** the experiments are designed to test. The project's own rule is that a claim is made only if the table that supports it exists. At the time of writing, none of these tables has been produced from real data." },
    { h2: "5.3 Performance Parameters and Evaluation Metrics" },
    { table: {
      caption: "Table 5.3: Metrics of the evaluation protocol",
      cols: [2300, 4300, 2426],
      head: ["Metric", "Definition", "Denominator"],
      rows: [
        ["Recall at fixed budget (headline)", "Share of fault cell-days that carry a final flag", "Fault cell-days, per fault kind and overall"],
        ["Precision-recall area", "Area under the precision-recall curve of the fused score", "All scored cell-days"],
        ["False alerts", "Final flags on clean cell-days", "Per 1,000 clean cell-days, and per daily field"],
        ["Event recall", "A fault is detected if any of its cell-days is flagged", "Fault events"],
        ["Footprint overlap", "Intersection over union of flagged and true fault cells", "Detected events, single-cell and patch faults separate"],
        ["Detection delay", "Days from fault start to first flag (median, 90th percentile)", "Detected stuck, repeat and drift events"],
        ["Calibration", "Reliability plot and expected calibration error", "Validation and test synthetic faults"],
        ["Protected-extreme false removal", "Share of protected cell-days and events that are flagged", "By client, season and event size"],
      ],
    } },
    { h2: "5.4 Implementation Status and Verification Evidence" },
    { p: "This section states plainly what exists and what has been checked. The project was built in nine gated stages, each of which must pass its own tests before the next begins." },
    { table: {
      caption: "Table 5.4: Build status of the case study (from the project specification)",
      cols: [2800, 3400, 2826],
      head: ["Stage", "Status", "Real-data result?"],
      rows: [
        ["Data contract, client map, splits, leakage audit", "Built and tested", "No"],
        ["Corruption benchmark and protected extremes", "Built and tested", "No"],
        ["Untrained scores and metrics", "Built; tested on a toy field", "No"],
        ["Centralised spatial and temporal components", "Built; tested on a tiny CPU run", "No"],
        ["Fusion and false-alarm budgets", "Built; final budget log not yet committed", "No"],
        ["Federated variants", "Built; masking and aggregation tests pass; tiny CPU run", "No"],
        ["Test-year scoring, unseen clients", "Built and tested on tiny runs", "No"],
        ["UK study with real hand-corrected labels", "Built; tested on generated files; reader unverified on real data", "No"],
        ["Paper tables and figures", "Built; tested on a tiny run", "No"],
      ],
    } },
    { p: "All tests of the QC code use a small generated rainfall world, not real RF25 data. They show that the code behaves as specified, for example that masking and aggregation are correct and that no held-out year can reach training. As an example, on 19 November 2026 the 14 tests of the federated-variant module (aggregation, client masking, matched gradient steps, resume and benchmark-hash checks) were run on a CPU and all passed in under three minutes, and the 27 tests of the live-gauge prototype passed using a mocked service. These runs show that the code behaves as specified. They do not show that the method detects real faults, and the report makes no such claim. The steps still to be done on a training machine are a timing run, three-seed training, the budget choice, a single test-scoring pass and generation of the paper tables." },
    { h2: "5.5 Discussion of Design Choices" },
    { bullets: [
      "**Whole sub-divisions as clients.** An earlier map cut the country into k-means blocks, which split 17 of the 34 sub-divisions across several clients. The final map nests the blocks inside sub-divisions so that regional output, which meteorologists read by sub-division, and training clients agree.",
      "**Hidden disc.** Without it, a spatial model can learn to copy a neighbour that shares the same interpolated fault, which would make faults invisible to it.",
      "**No claim that the components are individually novel.** LSTM or GRU models, spatial QC, ensembles, federated learning and personalisation each exist already. The project's contribution is the specific combination, the corruption benchmark and the evaluation protocol.",
      "**Synthetic labels kept in their own tier.** Results from corrupted data are never pooled with results that would come from expert labels, which do not exist for India.",
    ] },
  ],
});

chapters.push({
  title: "Advantages, Limitations and Discussion of Findings",
  blocks: [
    { h2: "6.1 Advantages" },
    { bullets: [
      "A realistic structure for a federated study: clients follow actual meteorological sub-divisions.",
      "A strong guard against leakage: spatial leave-out, time-ordered splits, held-out regions and an automated audit.",
      "Protection of genuine extremes is a measured outcome, not an afterthought.",
      "Decisions that could bias results (budgets, benchmark, test years) are fixed before the test data are scored.",
      "Components that need no training (slow and rules) provide a transparent fallback and explain flags in physical terms.",
    ] },
    { h2: "6.2 Limitations" },
    { bullets: [
      "**The federated training is a simulation.** All clients run sequentially on one machine and all data sit on that machine. The system therefore makes no privacy claim. Real federated deployment would raise further questions about communication, secure aggregation and differential privacy that the study does not address [4].",
      "**Synthetic faults only.** Labels come from deliberate corruption. Real faults may look different, and a detector tuned to the benchmark may not find them. A separate study with real hand-corrected labels from UK station data is built but not yet run, and its labels come from a neighbour check, so its results would carry a circularity caveat.",
      "**RF25 is itself interpolated.** The product smooths gauge information over about 1.5 degrees, so faults are spread across cells and clean-looking fields may contain unseen errors.",
      "**No real-data result exists yet.** Every result in a report of this kind must come from a run that has not yet happened. The comparison of the federated variants is therefore a set of hypotheses.",
      "**The live-gauge prototype is not a trained model**, its provider documentation leaves units and accumulation semantics open, and it has not been tested through a rain event.",
      "**Literature coverage.** The statement of the research gap is limited to the sources checked.",
    ] },
    { h2: "6.3 Discussion of Findings from the Literature" },
    { p: "Three points follow from the surveyed work. First, federated learning is technically feasible for meteorological sensors, both for fault detection [7] and for forecasting [8], and benchmarks suggest federated anomaly detectors can approach centralised accuracy in some settings [9]. Second, non-IID data are the central difficulty of federated learning [2], [4], [14], and personalisation [3] is the established response, which is why the case study makes personalisation the main variant. Third, the literature on weather QC rarely reports the quantities that matter operationally, namely false alarms per thousand clean observations and the fate of genuine extremes, so a protocol that makes them headline metrics is a meaningful contribution to the evaluation side of the field, independent of how the models turn out." },
  ],
});

chapters.push({
  title: "Applications, Challenges and Future Scope",
  blocks: [
    { h2: "7.1 Real-World Applications" },
    { bullets: [
      "Routine screening of national rainfall grids and station networks, with human review of the alerts.",
      "Pre-processing for flood forecasting, drought monitoring and crop advisories, where undetected phantom or zeroed rainfall biases the outcome.",
      "Collaboration between agencies or states that hold observations they cannot share, where only model parameters are exchanged.",
      "Near-real-time monitoring of low-cost or crowd-supported gauge networks, as in the operational prototype of Section 4.7.",
    ] },
    { h2: "7.2 Technical and Practical Challenges" },
    { bullets: [
      "Absence of labelled errors, which forces reliance on synthetic corruption.",
      "Non-IID client data and client drift [14].",
      "Communication cost and unreliable clients in a real deployment.",
      "Distribution shift as climate changes and networks are modernised: older and newer years have different gauge densities.",
      "Distinguishing a real record-breaking storm from a fault, which a detector alone cannot settle.",
      "Access and licensing of data: some meteorological data may not be redistributed [17].",
    ] },
    { h2: "7.3 Societal, Ethical and Environmental Impact, including the SDGs" },
    { p: "**Societal value.** Reliable rainfall data support early warning, agriculture and water management. Errors that pass unnoticed can lead to wrong warnings or poor planning, while a detector that wrongly removes a genuine extreme could hide a dangerous event. For this reason the framework is built to flag for review and never to overwrite observations." },
    { p: "**Ethics.** Four points matter. (i) *Privacy and data sovereignty:* federated learning lets data stay with its owner, but exchanged parameters can still leak information, so a privacy claim needs formal mechanisms that the study does not include and therefore does not make. (ii) *Fairness between regions:* a model trained mainly on data-rich regions may serve sparse regions poorly, which is why held-out regions are evaluated separately. (iii) *Transparency:* every flag in the framework carries the scores of its components, and results from synthetic labels are always labelled as such. (iv) *Responsibility for errors:* a missed fault and a false alarm have different costs, so the false-alarm budget is explicit and chosen in advance." },
    { p: "**Environmental impact.** Training neural networks consumes electricity. The framework keeps the networks small (a GRU and a small spatial network), uses untrained components where they suffice, and caps the training time per run, which limits the footprint. Federated learning can also reduce data transfer, although the repeated parameter exchange has its own cost." },
    { p: "**Sustainable Development Goals.** The work supports several goals of the 2030 Agenda [15]." },
    { table: {
      caption: "Table 7.1: Relation to the Sustainable Development Goals",
      cols: [2300, 6726],
      head: ["Goal", "How the topic relates"],
      rows: [
        ["SDG 13: Climate Action", "Trustworthy observations underpin climate monitoring, early warning of extreme rainfall and adaptation planning."],
        ["SDG 9: Industry, Innovation and Infrastructure", "Improves the reliability of observation infrastructure and applies a recent machine learning approach to it."],
        ["SDG 11: Sustainable Cities and Communities", "Better rainfall data improve urban flood warning and drainage planning."],
        ["SDG 2: Zero Hunger", "Agricultural advisories depend on correct rainfall records."],
        ["SDG 17: Partnerships for the Goals", "Federated learning is a way for institutions to collaborate without handing over raw data."],
      ],
    } },
    { h2: "7.4 Emerging Trends" },
    { bullets: [
      "Federated foundation models for meteorological data, with parameter-efficient prompts or adapters [8].",
      "Personalised federated learning and federated benchmarks for time-series anomaly detection [3], [9].",
      "Calibrated alerts with formal false-alarm control, including federated conformal methods.",
      "Combining gauges, radar and satellite estimates as additional evidence.",
    ] },
    { h2: "7.5 Future Research Directions" },
    { numbered: [
      "Run the pipeline on real RF25 data and produce the planned tables, then report which of the hypotheses of Table 5.2 hold.",
      "Run the study with real hand-corrected labels from UK station data and report it separately from the India study.",
      "Move from simulation to a real distributed setting and quantify communication cost, with secure aggregation if privacy is to be claimed.",
      "Extend the live-gauge prototype with verified units, a longer history per station and an evaluation on recorded rain events.",
      "Add a feedback loop in which reviewer decisions update thresholds and models, with a monitored shadow period.",
    ] },
  ],
});

chapters.push({
  title: "Conclusion",
  blocks: [
    { h2: "8.1 Summary of the Seminar" },
    { p: "The seminar examined weather anomaly detection with federated learning. Conventional quality control is transparent but rule-bound. Learning-based detectors exploit spatial and temporal context. Federated learning, with FedAvg, FedProx and FedPer, lets several data holders train a shared model without pooling raw data and copes with regional differences when personalisation is used. Published work covers federated sensor-fault detection and federated weather forecasting; in the sources checked, federated or personalised rainfall quality control with held-out regions and protection of genuine extremes was not found." },
    { p: "The case study, DataMend, turns that gap into a concrete design: eight clients made of whole IMD sub-divisions, four evidence components, a fused score at fixed false-alarm budgets, a corruption benchmark, protected extremes and four federated variants compared with centralised training, including on two unseen regions." },
    { h2: "8.2 Key Learnings and Observations" },
    { bullets: [
      "Defining the evaluation protocol and the leakage controls is as important as choosing the model.",
      "Heterogeneity between clients, not data volume, is what makes federated weather learning hard, and personalisation is the main tool against it.",
      "An honest statement of status (simulation, synthetic labels, no real result yet) is part of a defensible study.",
      "A detector must be judged by its false alarms and by what it does to genuine extremes, not by accuracy.",
    ] },
    { h2: "8.3 Conclusion" },
    { p: "Federated learning is a suitable framework for weather anomaly detection where data are distributed and regions differ. The case study provides an implemented and tested design and a pre-registered evaluation protocol. Whether the personalised federated variant matches centralised training and holds up on unseen regions is the question the next stage, the run on real data, has to answer; until then the conclusions of this report concern the design and the literature, not measured performance." },
  ],
});

const references = [
  "B. McMahan, E. Moore, D. Ramage, S. Hampson and B. Aguera y Arcas, \"Communication-efficient learning of deep networks from decentralized data,\" in Proc. 20th Int. Conf. Artificial Intelligence and Statistics (AISTATS), PMLR vol. 54, 2017, pp. 1273-1282.",
  "T. Li, A. K. Sahu, M. Zaheer, M. Sanjabi, A. Talwalkar and V. Smith, \"Federated optimization in heterogeneous networks,\" in Proc. Machine Learning and Systems (MLSys), 2020. arXiv:1812.06127.",
  "M. G. Arivazhagan, V. Aggarwal, A. K. Singh and S. Choudhary, \"Federated learning with personalization layers,\" arXiv:1912.00818, 2019.",
  "P. Kairouz et al., \"Advances and open problems in federated learning,\" Foundations and Trends in Machine Learning, vol. 14, no. 1-2, pp. 1-210, 2021.",
  "V. Chandola, A. Banerjee and V. Kumar, \"Anomaly detection: A survey,\" ACM Computing Surveys, vol. 41, no. 3, art. 15, 2009.",
  "I. Durre, M. J. Menne, B. E. Gleason, T. G. Houston and R. S. Vose, \"Comprehensive automated quality assurance of daily surface observations,\" J. Applied Meteorology and Climatology, vol. 49, no. 8, pp. 1615-1633, 2010, doi:10.1175/2010JAMC2375.1.",
  "R. Khan, U. Saeed and I. Koo, \"FedLSTM: A federated learning framework for sensor fault detection in wireless sensor networks,\" Electronics, vol. 13, no. 24, art. 4907, 2024, doi:10.3390/electronics13244907.",
  "S. Chen, G. Long, T. Shen and J. Jiang, \"Prompt federated learning for weather forecasting: Toward foundation models on meteorological data,\" in Proc. 32nd Int. Joint Conf. Artificial Intelligence (IJCAI), 2023, pp. 3532-3540, doi:10.24963/ijcai.2023/393.",
  "F. Liu et al., \"FedTADBench: Federated time-series anomaly detection benchmark,\" arXiv:2212.09518, 2022.",
  "Y. Sha, D. J. Gagne, G. West and R. Stull, \"Deep-learning-based precipitation observation quality control,\" J. Atmospheric and Oceanic Technology, vol. 38, no. 5, pp. 1075-1091, 2021, doi:10.1175/JTECH-D-20-0081.1.",
  "D. S. Pai, L. Sridhar, M. Rajeevan, O. P. Sreejith, N. S. Satbhai and B. Mukhopadhyay, \"Development of a new high spatial resolution (0.25 x 0.25 degree) long period (1901-2010) daily gridded rainfall data set over India and its comparison with existing data sets over the region,\" MAUSAM, vol. 65, no. 1, pp. 1-18, 2014.",
  "S. Hochreiter and J. Schmidhuber, \"Long short-term memory,\" Neural Computation, vol. 9, no. 8, pp. 1735-1780, 1997.",
  "K. Cho et al., \"Learning phrase representations using RNN encoder-decoder for statistical machine translation,\" in Proc. Conf. Empirical Methods in Natural Language Processing (EMNLP), 2014, pp. 1724-1734.",
  "T. Li, A. K. Sahu, A. Talwalkar and V. Smith, \"Federated learning: Challenges, methods, and future directions,\" IEEE Signal Processing Magazine, vol. 37, no. 3, pp. 50-60, 2020.",
  "United Nations General Assembly, \"Transforming our world: the 2030 Agenda for Sustainable Development,\" Resolution A/RES/70/1, 2015.",
  "Weather Union (Zomato), \"Weather Union API documentation,\" https://www.weatherunion.com/dashboard/, accessed 19 Nov 2026.",
  "NOAA National Centers for Environmental Information, \"Integrated Surface Database (ISD) FTP access point readme,\" https://www.ncei.noaa.gov/pub/data/noaa/readme.txt.",
];

const appendix = [
  { h2: "A.1 Project Materials" },
  { p: "The case-study software is the DataMend repository. The federated training code is in ml-service/qc/federated.py, the components in ml-service/qc/, the evaluation protocol in docs/qc-evaluation-protocol.md and the system specification in docs/qc-system-spec.md. The live-gauge prototype is in backend/app/rainfall/." },
  { h2: "A.2 Status Statement" },
  { p: "No claim in this report depends on a result from real data. Tables 5.2 and 5.3 are, respectively, hypotheses and build status. Figures 4.1 to 4.3 are a saved client map and two diagrams, not experimental outputs." },
  { h2: "A.3 Publications and Certifications" },
  { p: "None to report." },
];

module.exports = { TITLE, STUDENT, ROLL, GUIDE, GUIDE_DESIG, abstract, keywords, glossary, chapters, references, appendix };
