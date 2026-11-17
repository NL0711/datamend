# Precipitation QC system: build spec

Status: design locked 2026-11-17. Gates 0-9 are built and tested on small synthetic worlds (see section 14). **Nothing has been run on real RF25 or MIDAS data yet**; no real result exists. Each section links the ticket that holds the full decision; where this document and a ticket disagree, the ticket wins and this document is fixed.

Map: [Wayfinder map: precipitation QC system spec](https://github.com/NL0711/datamend/issues/10). Vocabulary: `CONTEXT.md`. Standing evaluation rules: `docs/qc-evaluation-protocol.md`.

## 1. Goal and positioning

- **Goal:** a quality-control system for RF25 gridded daily rainfall that scores every cell-day for contamination and does not flag genuine, spatially coherent heavy rain.
- **Hypothesis:** spatial, short-term temporal and slow-baseline evidence, combined by a calibrated fusion layer, detects structured faults while keeping protected extremes.
- **Not claimed:** that LSTM/GRU, spatial QC, ensembles, federated learning or personalization are individually novel. The contribution is the specific method, the corruption benchmark and the evaluation.
- **Hard rules:**
  - Detection never overwrites observations. Repair is out of scope.
  - No fabricated metrics. Synthetic labels are never presented as real ground truth.
  - The federated simulation makes no privacy claim.
  - No Kaggle-only paths, tokens or personal paths in code or configs.

## 2. Data

- **RF25** (IMD, Pai et al. 2014): files `RF25_ind<year>_rfp25.nc`, 1901-2023, one per year. Variable `RAINFALL`, dimensions `(TIME, LATITUDE, LONGITUDE)`, mm, fill value -999 read as missing. Grid 129 x 135 at 0.25 degree; 4,964 land cells.
- RF25 is an inverse-distance interpolation of 1-4 gauges within 1.5 degrees and carries **no QC flags**.
- The data-contract check asserts exactly these facts and fails loudly otherwise ([Kaggle schema](https://github.com/NL0711/datamend/issues/13)).
- Data and output locations follow `ml-service/training/paths.py`.

## 3. Clients and splits

- **Clients:** 8 geographic blobs from k-means on latitude/longitude over the land mask. The seed is fixed and the map is saved and hashed ([clients](https://github.com/NL0711/datamend/issues/14)).
- **Time:** train 1951-2012, validation 2013-2017, test 2018-2023 ([splits](https://github.com/NL0711/datamend/issues/16)).
- **Unseen clients:** client 3 (northeast, wettest) and client 6 (west-central) are held out, behind a 6-cell buffer.
- In federated and local-only training, other clients' cells are masked as missing.
- **Normalization:** per client, fitted on that client's training years only. It is `log1p(mm) / scale` and must not clip or truncate heavy rain.
- **Leakage audit:** tests prove that no held-out year, held-out client cell or buffer cell enters training inputs, statistics or thresholds.
- **1901-1950:** evaluation-only stress test for an older, sparser network; outside the headline tables ([experiments](https://github.com/NL0711/datamend/issues/27)).

## 4. Labels

Full decision: [label tiers and protected extremes](https://github.com/NL0711/datamend/issues/15).

| tier | India (RF25) | status |
|---|---|---|
| expert-reviewed real labels | none found | reported as "not available" |
| historical or weak flags | none usable (GHCN-Daily has almost no Indian data after 1970) | reported as "not available" |
| synthetic faults | the corruption benchmark | the only populated tier |

- **Protected extreme:** a connected group (default at least 4 cells, 8-neighbour) in which every cell is above its own heavy-rain threshold (default: the cell's 99th percentile of wet days in training years). Labelled "plausible, unverified". Never corrupted.
- **Ambiguous extreme:** an isolated extreme cell. Reported in its own row; in neither the fault nor the clean denominator.
- **Case studies:** named events, starting with Kerala August 2018. The event's dates and values must be checked against a source before use.

## 5. Corruption benchmark

Full decision: [corruption benchmark](https://github.com/NL0711/datamend/issues/17).

- **Nine fault kinds:** spike, stuck, scale, phantom rain, zeroed, repeat, drift/bias, edge artifact, combination.
- **Footprint** is a separate setting from kind: radius 0 (single cell) or 1.5-6 cells, about half of faults each. Faults are applied to whole daily fields.
- **Test-only:** the repeat and edge kinds, radii above 4, the weakest strengths, and the test seeds.
- **Frozen files:** validation and test benchmarks are generated once at about 1% of cell-days, saved and hashed. Training corrupts on the fly.
- Every fault records its exact mask, kind, strength, footprint and seed.

## 6. Components and baselines

Full decision: [components](https://github.com/NL0711/datamend/issues/18). New code lives in `ml-service/qc/`.

| component | input | output |
|---|---|---|
| spatial | same-day patch of about 6 cells, with a hidden disc of radius 2 around the target | zero-inflated Gamma prediction, one per cell |
| temporal | the cell's own previous 30 days, plus season and climatology; one-direction GRU; no neighbours | zero-inflated Gamma prediction |
| slow | trailing 30- and 90-day totals against the cell's own climatology and surrounding cells (robust z); untrained | score |
| rules | existing rules in `ensemble/branches.py`, the bound in `ensemble/statbaseline.py`, and a new step rule | score |

- **Baselines:** leave-out-disc neighbour-average residual, and a plain one-direction GRU.
- **Offline comparison:** the existing rainnet, scalenet, msnet and lstm_ae models, labelled as non-causal. Implemented in `qc/offline.py`: artifacts are set under `offline.artifacts` in the config; a model trained or tuned on any scored year is refused (named in the report); held-out cells are left unscored because these models were trained on all cells; their own threshold is not used.
- **Tests:** the target cell and its hidden disc cannot reach the spatial prediction; the temporal component sees no same-day or future value.

## 7. Fusion

Full decision: [fusion](https://github.com/NL0711/datamend/issues/19).

- One shared logistic regression on the four standardized scores.
- Fitted on 2013-2015 synthetic faults. Thresholds are false-alarm budgets set on clean 2016-2017 data: a final flag and a review flag.
- **The budgets are not chosen yet.** They are chosen from the first validation curves, logged in `docs/qc-evaluation-protocol.md`, and fixed before any 2018-or-later data is scored.
- Comparisons: boosted trees, plain average, OR of component flags, and a per-client fusion row.
- Each alert stores the four component scores, the fused score and the flag. No cause prediction in this version.

## 8. Federated simulation

Full decision: [federated setup](https://github.com/NL0711/datamend/issues/20).

- Sequential simulation on one machine. No privacy claim.
- **Main variant:** shared body; local head and normalization.
- **Comparisons:** FedAvg, FedAvg plus fine-tune, local-only, centralized. FedProx sits behind a switch.
- **Unseen clients** fit only their own local statistics and receive averaged heads.
- The shared fusion is fitted by federated averaging. A fusion can also be fitted on a federated variant's spatial and temporal scores (`python -m qc fusion --on fedpers|fedavg|fedft`; not local-only, which leaves unseen cells unscored); it is stored and scored as `fusion_<variant>@<source>`.
- One local epoch per client per round; six training clients in a fixed seeded order; rounds set so total gradient steps match the centralized run.

## 9. Metrics

Full decision: [metrics](https://github.com/NL0711/datamend/issues/26).

| metric | definition | denominator |
|---|---|---|
| **recall at the fixed budget** (headline) | share of fault cell-days with a final flag | fault cell-days, per kind and overall |
| precision-recall area | area under the precision-recall curve of the fused score | all scored cell-days |
| false alerts | final flags on clean cell-days | per 1,000 clean cell-days; also per daily field |
| event recall | a fault counts as detected if any of its cell-days is flagged | fault events |
| footprint overlap | intersection over union of flagged and true fault cells per fault day | detected events; single-cell and footprint faults separate |
| detection delay | days from fault start to first flag; median and 90th percentile | detected stuck, repeat and drift events |
| calibration | reliability plot and expected calibration error | validation and test synthetic faults |
| protected-extreme false removal | share of protected cell-days, and of protected events, that are flagged | protected cell-days and events; by client, season and event size |

- ROC AUC is not a headline number.
- Protected-extreme cell-days are excluded from the clean denominator used for the budget.
- Three seeds per trained model, reported as mean and range. Intervals come from resampling whole years and whole fault events.

## 10. Experiments and compute

Full decision: [experiments](https://github.com/NL0711/datamend/issues/27).

Priority order; drop from the bottom if time runs out, and list anything dropped as not run:

1. Rules, slow component, neighbour-average baseline.
2. Centralized spatial and temporal components; plain GRU baseline.
3. Main federated variant.
4. FedAvg, FedAvg plus fine-tune, local-only.
5. Fusion comparisons and the per-client fusion row.
6. Offline-comparison models.
7. FedProx.

**Compute profile is a config setting**, with two shipped profiles:

| profile | hardware | behaviour |
|---|---|---|
| `kaggle` | two T4 GPUs | two experiments at once, one per GPU; resume across session limits |
| `single-gpu` | one GPU on one machine | experiments one after another |

- Budget caps, devices, parallel experiment count, batch size and worker count are config values. The same experiment config gives the same splits, seeds and benchmark under either profile.
- No run has been timed. Caps are set from a timing run on the target machine. Provisional only: 2 GPU-hours per training run, 60 GPU-hours in total.

## 11. Runs and configuration

Full decision: [run recording](https://github.com/NL0711/datamend/issues/28).

- One YAML per experiment in `ml-service/qc/configs/`; launched with `python -m qc run <config>`; any value can be overridden on the command line.
- Each run folder holds: resolved config, seed, git commit, split manifest and client map with hashes, normalization state, metrics (JSON), per-alert records (Parquet), checkpoints.
- Runs resume from the last checkpoint.
- A run refuses to score against a benchmark whose hash differs from the one in its config.

## 12. UK MIDAS real-label study (second, separate study)

Full decisions: [labelled region](https://github.com/NL0711/datamend/issues/23), [study setup](https://github.com/NL0711/datamend/issues/25), [flags and counts](https://github.com/NL0711/datamend/issues/24). Facts: `docs/research/uk-midas-open-daily-rain-qc-flags-and-counts.md`.

- **Role:** a separate study with real "original versus hand-corrected" labels. Reported in its own table; never pooled with India. It is not evidence that the method finds real errors in RF25.
- **Data:** UK Met Office MIDAS Open daily rainfall (CEDA, Open Government Licence). Downloaded with `ml-service/scripts/download_midas.py`, which reads a CEDA access token from the `CEDA_TOKEN` environment variable or `ml-service/.env` (template: `ml-service/.env.example`).
- **Gridding:** grid the original station values with the same inverse-distance method as RF25. A cell-day is bad if a hand-corrected station value fed it.
- **Errors:** only manual corrections after a failed neighbour check. Automatic estimates, split multi-day totals, flag-only changes and unmatched originals are excluded from scoring and counted separately.
- **Circularity:** the labels come from a neighbour check, so the spatial component's score is reported with that caveat and beside the neighbour-average baseline.
- **Scope:** Devon plus two or three adjoining counties; train on UK 1975-2012; thresholds on clean 2013-2017; test 2018-2023.
- **Data in hand is a subset:** Devon only, and only station-years where QC changed something. Every count must be labelled so. The full files for the chosen counties are not yet downloaded.
- **Open in the build:** the exact counties, the UK grid spacing and search radius, and how multi-day totals are treated when gridding originals.

## 13. Paper outputs

Full decision: [paper outputs](https://github.com/NL0711/datamend/issues/29).

- **Tables:** main results per fault kind; component ablation; federated variants with unseen clients; protected-extreme false removals; the UK study.
- **Figures:** client map with held-out regions; example faults; recall against false-alarm budget; reliability plot; Kerala August 2018 case study.
- **Claims, each tied to one table:** combined components beat any single one (ablation); protected extremes are kept (protected-extremes table); the personalized federated variant holds up against centralized training and on unseen regions (federated table). A claim is made only if its table supports it.
- Notes in `docs/research/` that are marked unverified must be checked against the source before they are cited.

## 14. Build gates

Each gate ends with its tests passing and a short report of what ran. A later gate does not start before the earlier one passes.

| gate | work | exit check | status |
|---|---|---|---|
| 0. Setup | Create `ml-service/qc/`, the config loader and the two compute profiles. (The uncommitted footprint-injector edit in `ml-service/training/` was discarded on 2026-11-17 by the owner's decision; field-level faults replace it.) Run the timing run and set the budget caps. | Existing training tests pass; timing numbers recorded. | built; timing run NOT RUN |
| 1. Data and splits | Data-contract check, client map, split manifest, per-client normalization, leakage audit. | Contract and leakage tests pass; map and manifest hashed. | built, tested |
| 2. Benchmark | Fault library, protected and ambiguous extremes, frozen validation and test files. | Faults reproduce from seed; no protected cell is corrupted; test-only settings absent from training and validation. | built, tested |
| 3. Untrained scores and metrics | Rules, slow component, neighbour-average baseline, the metrics module. | Metrics match hand-computed values on a toy field; first validation numbers reported. | built, tested (toy field) |
| 4. Centralized components | Spatial and temporal components and the plain GRU baseline, three seeds. | Hidden-disc and causality tests pass; validation scores saved. | built, tested (tiny CPU run) |
| 5. Fusion and budgets | Fit the fusion, draw validation curves, choose and log the two budgets. | Budgets logged in the protocol **before any test-year scoring**. | built, tested; budgets NOT CHOSEN |
| 6. Federated variants | Main variant, then the comparisons, in priority order. | Masking and aggregation tests pass; same benchmark hash in every run. | built, tested (tiny CPU run) |
| 7. Test scoring | Score 2018-2023 once with fixed budgets; unseen clients; 1901-1950 stress test; offline comparison. | All headline metrics with intervals; anything not run is listed. | built, tested; offline comparison and fusion on federated components built and tested on tiny runs, not run on real data |
| 8. UK study | Download, grid, label, train, score. | Subset and circularity caveats printed with the table. | built, tested on generated files; reader UNVERIFIED on real MIDAS |
| 9. Paper outputs | Tables, figures, methods outline, claim check. | Each claim checked against its table. | built, tested on a tiny run; no real tables |

## 15. Known gaps at the time of writing

- No gate has been run on real data; every test uses a generated world. The training-machine steps (timing run, three-seed training, budget choice, single test-scoring pass, `python -m qc paper`) are all still to do.
- Offline comparison and fusion on federated components are implemented but have only been run on tiny generated worlds (the offline test uses random-weight artifacts: it checks the adapter, not a model). No real old-format artifact is in the repo. Local-only on unseen clients: NOT AVAILABLE.
- The UK reader is written from the documented layout and untested on real files; counties, grid spacing, search radius and client count are OPEN choices in `configs/uk.yaml`.
- Paper-check bars (`BARS` in `qc/paper.py`) are the check's own judgement calls.

- The fusion budgets are not chosen.
- No run has been timed on any machine.
- The Kerala August 2018 case-study values are unverified.
- Research notes extracted by subagents are unverified.
- The UK counts cover a Devon subset only.
- Held-out client numbers (3 and 6) refer to the saved client map; they are meaningless if the map is regenerated with a different seed.

## 16. ERA5 temperature, humidity and pressure (extension)

Separate from the rainfall system: `qc/era5.py` (data) and `qc/multivar.py` (experts, faults, validation). The rainfall pipeline stays rain-specific.

**Built and tested (small generated data, plus one real month: the January 2016 GRIB sample reads, converts and passes range checks):**
- **Reader (built for manual CDS downloads):** GRIB (`cfgrib` + `eccodes`, in `requirements-train.txt`) or NetCDF, any file names, any number of months or years per file. The converter reads the timestamps inside each file, so names do not matter; it reads one chunk of hours at a time; hours present in two files are counted once; a larger download area is cut down to the RF25 grid, a smaller one is refused with the area to use (N 38.5, W 66.5, S 6.5, E 100.0). Zip files are not read (choose "Unarchived" on the form). `python -m qc era5-inventory` shows what the files cover before converting. `scripts/download_era5.py` is optional.
- **Daily conversion:** per hour, temperature in degC, pressure in hPa, relative humidity from temperature and dewpoint (Magnus over water, constants 17.625 and 243.04, clipped to 100 %); then daily mean, min and max. Output `ERA5D_<year>.nc`. A day is complete only if every cell has 24 hourly values; otherwise it is NaN and listed, never filled.
- **Day alignment:** `era5.label_offset_hours`. 0 = UTC calendar day (default). 21 = the 24 h ending 03:00 UTC (08:30 IST) labelled with the end date. **UNVERIFIED** which one matches the IMD rain day; the offset is recorded in every output file. The hour-boundary convention at the day edge is also unchecked.
- **Which daily statistics to keep:** OPEN (`era5.stats`); all three are kept by default.
- **Volume:** one pass per year over the files that cover it; no hourly data is rewritten. A hourly file is deleted only with `--delete-hourly`, and only when every label year its hours fall in has a complete daily file (so with the 21 h alignment a December file stays until the next year is built). Default: keep everything.
- **Per-variable experts:** anomaly, step, physical-bound and stuck-run rules per variable, each divided by a reference from clean threshold years (bound and stuck use fixed references 1 and 2).
- **Cross-variable consistency expert:** Mahalanobis distance of the day's standardized anomaly vector (covariance fitted on training years, pooled over cells).
- **Fusion:** logistic regression on the four expert scores, fitted on synthetic faults of the fusion-fit years.
- **Synthetic faults for continuous variables:** spike, stuck, drift, amplitude error; single cell, one variable at a time; clipped to the physical range.
- **Validation:** `python -m qc era5-daily --years A B`, then `python -m qc era5-validate`: recall per variable and fault kind at false-alarm budgets, written with the limits below.

**NOT IMPLEMENTED:** learned per-variable heads (Gaussian or neural spatial and temporal experts), spatial footprint faults, protection of genuine extremes (heat waves, cold spells: the rain "protected extreme" idea has no counterpart yet), federated variants, a frozen hashed benchmark, a single-use test pass, and the paper tables and figures for these variables. The rainfall splits, client map and models are not reused.

**Honest limit:** ERA5 is a reanalysis (modelled), not a measurement. It is smooth and spatially consistent by construction, so injected faults are easier to detect than real sensor faults. Every ERA5 number must carry this.

**Volume:** one month of the three hourly variables is about 78 MB, so 1951-2023 would be about 68 GB if the hourly files were kept. Use `--delete-hourly` once a year is verified.
