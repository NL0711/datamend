# DataMend model overview: rainfall quality control

Written 2026-11-18. Scope: the model and ML side only. The web app (backend, frontend, Locations) is covered elsewhere.
Every claim names the file it comes from. Where docs and code disagree, this file follows the code and says so (section 9).

**Read this first.** Nothing has been run on real RF25 or MIDAS data. Every result so far comes from small generated
worlds (`ml-service/qc/README.md`, `docs/qc-system-spec.md` header and section 15). No budget has been chosen, no model
has been trained at full size, and no performance number in this repo is a real result.

---

## 1. Goal

The project is rainfall only. Its question is: for each grid cell and each day of IMD's RF25 gridded daily rainfall for
India, is this value probably contaminated by a fault, or is it genuine rain, including genuine heavy rain? The system
scores every cell-day, turns the score into a flag at a fixed false-alarm rate, and does not overwrite any value
(`docs/qc-system-spec.md` section 1; `ml-service/qc/__init__.py`).
RF25 has no quality flags, so there are no real labels for India. The system is tested against deliberately corrupted
copies of clean data, called synthetic faults (`docs/qc-system-spec.md` sections 2 and 4; `CONTEXT.md`).

The older temperature, pressure and humidity work was removed on 2026-11-18 (`TODO.md`, QC section).

## 2. Impact

Who might benefit, if the system works on real data (this is not shown yet):
- People who build or use gridded rainfall products and need a ranked list of suspect cell-days to review, instead of
  checking all of them. RF25 itself documents only one sentence of QC (`docs/research/operational-rainfall-qc-primary-sources.md`).
- Researchers on extreme rainfall, who need real heavy rain kept in the data. Keeping protected extremes is a headline
  metric (`docs/qc-system-spec.md` sections 4 and 9).

What it does not claim (`docs/qc-system-spec.md` section 1; `docs/qc-paper-methods-outline.md` sections 1 and 10):
- No part is claimed as new. Rules, neighbour checks, learned forecasts, ensembles and federated training all exist already.
  The study is the combination, a comparison of its parts, and a protected-extreme test.
- Recall means recall of injected faults. It says nothing about recall of real IMD errors.
- The federated simulation runs on one machine and makes no privacy claim.
- Calibration is against the synthetic fault rate only (`ml-service/qc/metrics.py`, `calibration`).
- Repair is out of scope. The system detects and never corrects.

Research notes say what looks open in the literature: event-coherence evidence, calibrated false-alarm budgets with
held-out regions, personalised federated QC. They are absence in a limited search, and most sources are marked
unverified (`docs/research/qc-novelty-research.md`, sections 1 and 5).

## 3. Data and splits

| item | value | source |
|---|---|---|
| Main data | RF25, IMD 0.25 degree daily rainfall, variable `RAINFALL`, mm, fill -999 read as missing | `docs/qc-system-spec.md` s2; `ml-service/qc/configs/base.yaml` |
| Grid | 129 x 135, 4,964 land cells; a contract check fails loudly on any mismatch | `qc/grid.py`; `base.yaml` |
| Years in the files | 1901-2025, one file per year (125 files) | `base.yaml`; `docs/qc-system-spec.md` s2 |
| Train | 1951-2012 | `base.yaml` |
| Validation | 2013-2017. Fusion fitted on 2013-2015. Budgets set on clean 2016-2017 | `base.yaml`; `docs/qc-evaluation-protocol.md` |
| Test | 2018-2025, scored once | `base.yaml`; `qc/testscore.py` |
| Stress | 1901-1950, evaluation only, outside the headline tables | `base.yaml`; `docs/qc-system-spec.md` s3 |
| Clients | 8 groups of whole IMD sub-divisions (k-means blobs re-cut on 2026-11-18 so no sub-division is split; fixed map in `qc/assets/client_map.json`, composition in `client_subdivisions.json`). Clients 3 (north-east: Arunachal, Assam & Meghalaya, N M M T, SHWB & Sikkim) and 6 (west-central, includes Konkan & Goa and Mumbai) are held out, behind a 6-cell buffer | `qc/clients.py`; `qc/splits.py`; `base.yaml` |
| Normalisation | per client, training years only: `log1p(mm) / scale`, scale from the 99.9th percentile of training wet days. It rescales and never clips | `qc/stats.py`; `docs/qc-evaluation-protocol.md` |
| Second study | UK MIDAS Open daily rain, real hand corrections as labels. Separate, never pooled with India | `docs/qc-system-spec.md` s12; `qc/uk/` |

Cell roles: `train`, `buffer` (a training client's cell within 6 cells of a held-out cell, never a target) and `heldout`
(never read in training) (`qc/splits.py`).
RF25 is an inverse-distance interpolation of 1 to 4 gauges within 1.5 degrees, so neighbouring cells share gauges and
are not independent (`docs/research/operational-rainfall-qc-primary-sources.md`; `docs/research/rainfall-qc-without-labels.md` s5).

## 4. Model architecture

### 4.1 Overview

Locked system: `ml-service/qc/`. Plain words for the terms used below:
- **module**: a Python file or package with one job.
- **interface**: what a module accepts and returns.
- **seam**: a place where one part can be swapped without changing its neighbours.
- **adapter**: a module that makes something with a different shape fit a seam.

```
RF25 year files (mm, 129x135)                         UK MIDAS station files (separate study)
        |                                                      |  qc/uk: grid to RF25-format files (adapter)
        v                                                      v
 qc/grid  (contract check, field (T,H,W) and series (T,n_land))
        |
 qc/prepare + splits + stats   splits, per-client scale, climatology, heavy-rain threshold, leakage audit
        |
 qc/faults + extremes + benchmark   frozen, hashed faults for val/test/stress years; protected and ambiguous extremes
        |
        v   each component is a function  Block -> (days, n_land) scores  (qc/scoring.py)
 +-----------+  +-----------+  +--------------+  +-----------+
 | rules     |  | slow      |  | spatial      |  | temporal  |      baselines (not components):
 | untrained |  | untrained |  | CNN, trained |  | GRU,      |      neighbour average, plain GRU
 |           |  |           |  | hidden disc  |  | trained   |
 +-----+-----+  +-----+-----+  +------+-------+  +-----+-----+
       \              \               |               /
        +---- ScoreStore: scores saved per name, split, year (qc/scoring.py) ----+
                                   |
                           qc/fusion  (logistic main; mean, or, boosted, per_client)
                                   |
              qc/evaluate + fusion_eval: thresholds from clean-year false-alarm budgets
                                   |
                    final flag and review flag; testscore (single use); paper tables

 federated.py trains spatial and temporal in 4 variants; offline.py scores the older models as a non-causal comparison
```

Vocabulary: a component is one independent source of evidence. There are four. An offline comparison model is not a
component (`CONTEXT.md`).

### 4.2 Modules

All paths below are under `ml-service/qc/` unless stated.

**Data and splits (`grid`, `clients`, `splits`, `stats`, `prepare`).**
- Purpose: read RF25, fix the client map and cell roles, fit training-only statistics, audit for leakage.
- May see: training years only for anything fitted. Held-out clients get their own normalisation and climatology from
  their own training-year data, with no labels and no training (`stats.py`).
- Output: `split_manifest.json` and `train_stats.npz`. Later stages refuse to run if the manifest does not match the config.
- Interface: `Prepared` object via `load_prepared(cfg)`. Seam: `Grid` is the only reader of RF25 files. The UK study
  writes RF25-format NetCDF files, so the rest of the pipeline reads UK data unchanged. That is an adapter at the data seam (`uk/build.py`).

**Benchmark (`faults`, `extremes`, `benchmark`).**
- Purpose: build the only populated label tier, synthetic faults, and the groups used in metrics.
- Faults: nine kinds (spike, stuck, scale, phantom_rain, zeroed, repeat, drift, edge, combination), point or footprint
  (radius 1.5 to 6 cells), blended as `original + weight * (faulty - original)` (`faults.py`).
- Test-only settings: kinds repeat and edge, radii above 4, strengths below 0.25, and the test seeds (`base.yaml`).
- Extremes: protected = at least 4 connected cells (8-neighbour) all above their own 99th percentile of wet days.
  Never corrupted. Labelled plausible, unverified. Ambiguous = an isolated heavy cell, reported alone (`extremes.py`).
- Output: one file per year, hashed. A scoring run refuses a different hash (`benchmark.py`).

**Rules (`untrained.py`, reusing `ensemble/branches.py`, `ensemble/statbaseline.py`).**
- Purpose: fixed physical checks.
- May see: the day and earlier days. Reference statistics from training years only.
- Output: maximum of four severities: negative or implausibly large value (ramp 300 to 1000 mm/day), run of 5 or more
  identical non-zero values, value above the cell's climatological upper bound, and a day-to-day step rule.
- Interface: function from a `Block` to scores.

**Slow (`untrained.py`).**
- Purpose: slow drift and bias in totals.
- May see: trailing 30- and 90-day totals, compared with the cell's own training-year totals (robust z, median and MAD)
  and with surrounding cells outside the hidden disc. Score is the larger of the two.
- Untrained. Same interface as rules.

**Spatial component (`models.SpatialNet`, `batches.py`, `trained.py`).**
- Purpose: predict a cell's rainfall from the same day's surroundings, then score how surprising the observed value is.
- May see: one day, a 13 x 13 patch (radius 6), plus season, climatology and the cell's heavy-rain threshold.
  May not see: the target cell and every cell within 2 cells of it. They are multiplied by zero inside `forward`, so
  no caller can leak them. The patch radius must not exceed the buffer (6 cells) (`models.py`; `base.yaml`).
- Output: zero-inflated Gamma (probability of rain, shape, scale). Score is minus log of the two-sided tail
  probability (`models.surprise`).
- Training: inputs corrupted on the fly with seen fault settings, targets stay clean, targets are `train` cells only.
  Three seeds (`trained.py`; `base.yaml`).

**Temporal component (`models.TemporalGRU`).**
- Purpose: predict a cell's rainfall from its own past.
- May see: the cell's previous 30 days (one-direction GRU), plus season, climatology and heavy threshold.
  May not see: the scored day, any later day, or any neighbour.
- Output and training: as for spatial.

**Baselines (`untrained.py`, `models.PlainGRU`).**
- Neighbour average: residual of `log1p(value)` from the mean of cells outside the hidden disc, over their spread.
- Plain GRU: a point forecast from the cell's previous 30 days. Neither is a component. They exist so gains can be measured.

**Fusion (`fusion.py`, `fusion_eval.py`, `ablate.py`, `calibration.py`).** See section 5.

**Federated simulation (`federated.py`).**
- Purpose: train spatial and temporal in a federated way, in sequence on one machine.
- Variants: `fedpers` (main; body averaged, each client keeps its own final layer), `fedavg`, `fedft` (fedavg then
  per-client fine-tune), `local` (no communication). FedProx is a switch, off by default.
- Other clients' cells are NaN in a client's inputs. Held-out clients get the averaged model, except in `local`, where
  they are left unscored (NOT AVAILABLE).
- Interface: same score files as the central components, so the fusion can be fitted on them (`fusion --on fedpers`).

**Offline comparison (`offline.py`).**
- Purpose: score the older `training` models (rainnet, scalenet, msnet, lstm_ae) on the same benchmark, as a reference.
- They are non-causal (they read days on both sides), trained on all cells. So a model whose years overlap any scored
  year is refused, and held-out cells are unscored. Their own threshold is not used.
- This is the adapter between the older line and the locked system. No real artifact is in the repo. Its test uses
  random-weight artifacts, so it checks the adapter, not a model.

**Test scoring and paper (`testscore.py`, `paper.py`).** See section 6.

**UK study (`uk/`).** Reads MIDAS files, grids originals and corrections with the RF25 method (inverse distance, 1 to 4
gauges), labels a cell-day bad only if a manual correction after a failed neighbour check fed it. Everything else that
changed is excluded and counted. The reader is UNVERIFIED against real files (`uk/midas.py` docstring).

### 4.3 Where the seams are

- Component seam: any function `Block -> (days, n_land)` float scores (higher = more anomalous, NaN = cannot score)
  can be run with `compute_scores` and saved in the `ScoreStore` under a name (`scoring.py`, `evaluate.py`).
  A new component then needs only a name in the fusion input list (`fusion.component_names`).
- Fusion seam: `VARIANTS = logistic, mean, or, boosted, per_client`, all fitted on the same rows (`fusion.py`).
- Source seam: `fusion --on central|fedpers|fedavg|fedft` picks which spatial and temporal scores are fused.
- Data seam: `Grid` and RF25-format files. The UK adapter uses it.
- Older line: `training/__init__.py` names its own seams (`RainfallArchive`, `LocalTrainer`, `partition_cells`,
  `inject`). `LocalTrainer` is described as the federated seam but is not used by `qc/federated.py`, which has its own loop.
  Two modules of the older line are reused by `qc`: `ensemble.statbaseline` and `ensemble.branches.daily_rule_severity`,
  plus `training.data`, `training.paths`, `training.climatology`, `training.transform`.

### 4.4 Current line and older line

| line | where | what | state |
|---|---|---|---|
| Current, locked | `ml-service/qc/` | the four-component system above | built, tested on generated worlds |
| Older | `ml-service/training/`, `ensemble/`, `detectors/`, `evaluation/`, `validation/` | per-cell window models (lstm_ae, rainnet, msnet, scalenet; BiLSTM and attention, zero-inflated Gamma head, supervised head), label-free ensemble (rank normalisation; mean_rank, max, prob_avg, owa), cross-scale rules | built, unit-tested, never trained at full size |

Evidence that `qc` is current: `ml-service/README.md` line 3, `docs/qc-system-spec.md`, and `qc` imports the older code
but not the other way round. The older line splits years by "latest 4 test, 3 before it validation" (`training/splits.py`),
which is not the QC split. `SETUP.md` says so.

## 5. Fusion, budgets, thresholds

- **Inputs:** four scores per cell-day: rules, slow, spatial, temporal. Each is mapped with `log1p` and standardised on
  the fit rows. A missing score becomes 0 after standardising, never a fault signal (`fusion.py`).
- **Fit data:** synthetic faults in 2013-2015, training-client cells only. Positives are fault cell-days. Negatives are
  all other scored cell-days including protected extremes, so the fusion learns that agreement among components, not a
  large value, signals a fault. Ambiguous extremes are left out (`fusion.py`).
- **Main fusion:** one shared logistic regression. Comparisons: plain mean, OR of component tail probabilities, boosted
  trees, one logistic per client. A federated-averaged logistic is also built (`federated.fusion_rounds`) (`base.yaml`;
  `docs/qc-system-spec.md` s7 and s8).
- **Output per alert:** the four component scores, the fused score and the flag. No cause prediction in this version
  (`docs/qc-system-spec.md` s7). The logistic probability is calibrated to the synthetic fault rate only.
- **Budgets:** two operating points, a final flag and a review flag, each a number of false alerts per 1,000 clean
  cell-days. Clean means no fault, not protected, not ambiguous. The threshold is the score quantile on clean 2016-2017
  data of training clients (`evaluate.thresholds_for`, `metrics.py`).
- **Status of budgets:** NOT CHOSEN. `qc set-budgets` is the only place a budget becomes final. It refuses if any test or
  stress year was already scored, and logs the choice in `docs/qc-evaluation-protocol.md` (`fusion_eval.py`).
  The log table there is empty.
- **How well a budget holds:** `qc calibrate` checks it out of sample in time, by client, with block-bootstrap
  intervals, comparing one global threshold with per-client thresholds. No formal guarantee is claimed, because
  cell-days depend on each other (`calibration.py`). Held-out clients use the global threshold.
- **Event-coherence context:** `nbr_wet` and `nbr_heavy` (share of ring neighbours that are wet or heavy, same day only,
  outside the hidden disc) exist as extra score inputs for the learned fusions. They are wired into the validation-only
  ablation (`qc ablate`), not into the main four-input fusion (`context.py`; `ablate.py`; `fusion.py` `BASE`).
  They follow research angle (a) in `docs/research/qc-novelty-research.md`.
- **Candidate budgets** on the validation curves: 0.1 to 50 per 1,000 (`base.yaml`). The README example uses
  `--final 1 --review 5` only as an example of the command.

## 6. Evaluation

**Metrics** (`docs/qc-system-spec.md` s9; `qc/metrics.py`):
- Headline: recall at the fixed budget, per fault kind and overall.
- Also: PR-AUC, false alerts per 1,000 clean cell-days and per daily field, event recall, footprint overlap (IoU),
  detection delay (median and 90th percentile for stuck, repeat, drift), reliability plot with expected calibration error,
  protected-extreme false removal by client, season and event size.
- ROC-AUC is not a headline number. Three seeds per model, reported as mean and range. Intervals come from resampling
  whole years with the regions fixed (`base.yaml`: 200 resamples; none for fewer than 5 years; see `docs/research/bootstrap-unit-check.md`).

**Synthetic faults against real labels:**
- India: synthetic faults only. Expert-reviewed and historical-flag tiers are reported as "not available". Results are
  never pooled across label tiers (`CONTEXT.md`; spec s4).
- UK: real hand corrections, but they come from a neighbour check, so the spatial component is partly scored against
  the rule that made the labels. The table carries that caveat and the neighbour baseline beside it. The data in hand is
  a Devon subset of station-years where QC changed something (spec s12).
- A real-fault check is the stated answer to the risk that the fusion learns the injection recipe. Held-out kinds,
  radii and strengths in the test years limit that risk but do not remove it (`docs/research/qc-novelty-research.md` s4).

**Leakage rules** (`docs/qc-system-spec.md` s3; `qc/splits.py`; `qc/stats.py`; `ml-service/README.md` leakage section):
- Everything fitted uses training years only: scale, climatology, heavy threshold, upper bound.
- Fusion is fitted on 2013-2015 and thresholds on 2016-2017. Test years fit nothing.
- No held-out year, held-out client cell or buffer cell enters training inputs, statistics or thresholds. Tests audit this.
- History before 1951 is NaN for training. The first year of the archive gets NaN history (`scoring.py`).
- Spatial: the hidden disc is zeroed inside `forward`. Temporal: no same-day or future value.
- If a fault is wider than the hidden disc, the spatial component partly sees it (`CONTEXT.md`).

**Test-pass discipline:**
- Budgets must be fixed first. `test-score` checks the budgets, the benchmark hash (recorded; the pin was removed on 2026-11-18, so it is no longer enforced) and that every model exists for
  every seed, then writes `test_scoring.lock.json`.
- A finished lock makes any later test scoring refuse to run. Only the owner deleting the lock file starts over. An
  unfinished lock can be resumed with `--resume`. The stress split has no lock (`testscore.py`).
- `qc paper` computes tables and figures only from saved outputs. A missing input is reported as NOT RUN, never filled.
  Claim bars (`BARS`: at most 10% of protected cell-days flagged; federated recall within 0.05 of centralised) are the
  check's own judgement calls (`paper.py`; spec s15).
- Not yet done: the Kerala August 2018 case-study values are unverified and must be checked against a source first.

## 7. Status

| item | built and unit-tested (generated worlds) | run on real data | not built |
|---|---|---|---|
| Data contract, client map, splits, leakage audit | yes | no | |
| Fault library, extremes, frozen benchmark | yes | no | |
| Rules, slow, neighbour baseline, metrics | yes (toy field) | no | |
| Spatial, temporal, plain GRU (3 seeds) | yes (tiny CPU run) | no | |
| Fusion variants, validation curves, ablation, calibrate | yes | no | |
| Budgets chosen | | no, NOT CHOSEN | |
| Federated variants (fedpers, fedavg, fedft, local, FedProx switch) | yes (tiny run) | no | local-only on unseen clients: NOT AVAILABLE |
| Fusion fitted on federated components | yes (tiny run) | no | |
| Offline comparison of older models | adapter only, random-weight artifacts | no | no real artifact in repo |
| Single-use test pass, stress pass | yes | no | |
| UK MIDAS study | yes, on generated files | no | reader UNVERIFIED on real files; counties, grid, radius OPEN |
| Paper tables, figures, claim check | yes (tiny run) | no | no real tables |
| Timing run and compute caps | | NOT RUN | |
| Kaggle notebook | tested as a script locally | not run on Kaggle (per `SETUP.md`) | |
| Older line (`training`, `ensemble`) | yes; cross-scale rules, metrics on toy arrays | no | multi-teacher distillation; real station branch (a stub); elevation file not shipped |
| Cause or fault-type prediction, repair of values | | | NOT IMPLEMENTED (out of scope, spec s1 and s7) |
| Multi-resolution extension (section 8) | | | PROPOSED, NOT BUILT |

Sources: `docs/qc-system-spec.md` s14 and s15; `ml-service/qc/README.md`; `TODO.md`; `ml-service/README.md`.
Test functions counted by `def test_` in the tree: qc 124, training 51, ensemble 13, evaluation 10, validation 9.
I did not run them.

Not part of the rainfall model: `backend/app/ml/` (legacy tiers and a 6-stage pipeline for temperature, pressure and
humidity, trained on 5,760 simulated rows) belongs to the web app side and is scheduled for removal. Its old evaluation
report (`docs/evaluation_report.md`, removed 2026-11-19, still in git history) did not describe the rainfall model.

## 8. PROPOSED, NOT BUILT: multi-resolution extension

**Everything in this section is a proposal. None of it is built, trained or tested.** The monthly/seasonal item is not
confirmed by the owner. The reasoning comes from `docs/research/rainfall-qc-without-labels.md`, which is a partial,
subagent-written note not reviewed line by line.

Idea: one model per time scale, because different faults show at different scales. The daily scale exists already.

| scale | proposed model | status |
|---|---|---|
| Daily | the existing `qc` components (rules, slow, spatial, temporal) and fusion | built |
| Monthly or seasonal | a small pooled net | PROPOSED, NOT BUILT; not confirmed by the owner |
| Yearly | a pooled gradient-boosted or quantile model with the target hidden, plus aggregated daily scores | PROPOSED, NOT BUILT |
| Decadal | pairwise change-point tests, no training | PROPOSED, NOT BUILT |

Reasons given in the research note:
- Operational archives (GHCN, CHIRPS, GPCC, IMD) use rules and neighbour checks and need no labels. Rain needs special
  handling of zeros.
- For long records, relative (pairwise or reference) tests are standard. For rain they work better on yearly than
  monthly corrections (Venema et al. 2012; Menne and Williams 2009 for the pairwise method).
- With about 125 yearly values per cell, the note argues for change-point tests with thresholds set by simulation, not
  deep nets. This is stated as the note's opinion, not established practice.
- RF25 neighbours share gauges, so independence assumptions in these tests are weaker. This is untested.
- Synthetic injection should be reported as a unit test. Its realism is untested for India.

Open questions: what a yearly or decadal fault looks like in RF25 (station-network change, interpolation change) and how
it would be evaluated without labels. No design for either exists in the repo.

## 9. Known gaps and conflicts between docs

Docs against code or against each other. Code wins.

1. **Test years and file count.** `ml-service/qc/configs/base.yaml` says test 2018-2025 and 125 files. Stale text says
   2018-2023 or 123 files: `qc/testscore.py` docstring, `qc/kaggle_data.py` (lines 84, 123),
   `ml-service/notebooks/datamend_qc_kaggle.ipynb` (intro and cell 13), `ml-service/SETUP.md` (section 4 expects
   `years=1901-2023`), `ml-service/data/README.md` (says 123 files in one place and 125 in another). A kaggle_data
   check set to 123 files would accept a dataset missing 2024 and 2025.
2. **Stale local artifacts.** Ignored folders under `ml-service/data/` and `ml-service/artifacts/qc/base/` hold a
   frozen benchmark `v1` (hash `3558013881231b2c`), a split manifest with test 2018-2023, untrained validation
   scores (commit `ede7e72...+dirty`, 2026-11-17) and a 62-year land cache. The config pinned hash `442851b03d5f95a4` until the owner removed the pin on 2026-11-18 (the hash is
   now recorded, not enforced); a fresh machine builds its own benchmark. Whether these files came from real or generated data is not recorded;
   the owner says nothing ran on real data.
3. **Project identity.** Resolved 2026-11-19: `AGENTS.md`, `ARCHITECTURE.md`, `README.md` and `TODO.md` were rewritten for the
   rainfall validation platform, and the old `GOAL.md`, `PROJECT.md` and `docs/evaluation_report.md` (AWS temperature, pressure
   and humidity) were removed (still in git history). The rainfall components predict rain internally, but only to score
   surprise, which is not forecasting.
4. **Commands.** `docs/qc-system-spec.md` s11 says runs launch with `python -m qc run <config>`. No such command exists
   (`qc/__main__.py`); `qc/README.md` and `SETUP.md` say so. `qc calibrate` is in the code and the `ablate` command is in the
   README, but neither is in the `__main__.py` docstring, and `calibrate` is absent from the README run table.
5. **Fusion inputs.** The spec and `fusion.py` `BASE` name four inputs. The code also accepts `neighbour_baseline`,
   `nbr_wet` and `nbr_heavy` as fusion inputs, used only in `qc ablate`. The spec does not describe the context features.
6. **Component inputs.** Spec s6 lists the spatial input as "a patch of about 6 cells". Config has patch radius 6
   (13 x 13, as the paper outline says). Spec lists season and climatology for the temporal component. `models.py`
   gives both networks four static inputs: sin and cos of day of year, climatology and the heavy threshold.
7. **Budget log empty.** `docs/qc-evaluation-protocol.md` status line is dated 2026-11-16 and its table is empty.
   Spec s7 and s14 agree budgets are not chosen. Consistent, but the protocol and README examples show 1 and 5 as the
   only numbers, which are examples.
8. **Test counts.** `ml-service/README.md` says 89 tests, `SETUP.md` says 57 for `training`. The tree has far more test
   functions (section 7). `qc/README.md` says the qc tests take about 10 minutes.
9. **Data README status.** `ml-service/data/README.md` says `splits/` and `benchmarks/` are "not built yet" and that `rf25/` is
   used by `training` today and the QC build later. Both are out of date.
10. **Research notes.** `docs/research/qc-novelty-research.md` quotes measured numbers (spatial recall, share of protected
    extremes flagged) with no run recorded in the repo, and cites `docs/research/era5-methodology-verification-20261117.md`,
    which was deleted. IMD's page gives 1901-2024 for RF25, the spec gives 1901-2025. Pai et al. gauge count appears as
    6995 and 6955 (`operational-rainfall-qc-primary-sources.md`). Most research notes are marked UNVERIFIED and
    subagent-written. Do not cite them without checking the source.
11. **Two training stacks.** `ml-service/README.md` still opens its long section with the older label-free ensemble as
    "Goal" and describes `scalenet`; the locked system is `qc`. A new reader can confuse them.
12. **Unverified or open items.** UK reader on real files; UK counties, grid spacing, search radius, client count;
    Kerala 2018 values; `affiliation` metric not cross-checked against the reference package (`evaluation/rainfall_metrics.py`);
    paper bars; timing and compute caps (spec s10: `max_hours_total`, `session_hours`, `parallel_experiments` are not read by code).
13. **Method gaps.** Heavy-rain thresholds and protected extremes come from the same percentile the models may use, so
    they can look better than they are (`qc-novelty-research.md` s4). Synthetic fault realism is untested for India.

## 10. How to run

Commands are copied from the READMEs. Not run for this file. All from `ml-service/`.

Setup (`qc/README.md`):
```bash
cd ml-service
uv venv --python 3.11 .venv
uv pip install -r requirements-train.txt pytest
python -m pytest qc -q            # about 10 minutes on CPU, no RF25 needed
```
`SETUP.md` gives a `pip` route and says install PyTorch first for your hardware. RF25 files go in `data/rf25/`, or set
`DATAMEND_DATA_DIR`. RF25 is not downloaded by any script.

Run order on a machine with RF25 (`qc/README.md`; add `--config qc/configs/base.yaml`, optionally `--profile kaggle|single-gpu`):
```bash
python -m qc client-map
python -m qc prepare
python -m qc benchmark
python -m qc untrained
python -m qc train
python -m qc federated --variants fedpers fedavg fedft local
python -m qc fusion               # also: --on fedpers|fedavg|fedft
python -m qc ablate               # optional, validation only
python -m qc calibrate            # in the code; not in the README table
python -m qc set-budgets --final F --review R    # once, before any test scoring
python -m qc test-score           # single use; --splits test scores the test years only
python -m qc paper
```
Kaggle: `notebooks/datamend_qc_kaggle.ipynb`, phase 1 to the fusion step, you choose budgets, phase 2 runs the single test
pass (`qc/README.md`). Start with `SMOKE = True`.
UK study: `qc/configs/uk.yaml` header gives the order (`download_midas.py`, `uk-grid`, `client-map`, `prepare`, `uk-labels`,
then untrained, train, fusion). The token goes in `ml-service/.env` (not read here); template `ml-service/.env.example`.

Older line (`ml-service/README.md`, `SETUP.md`):
```bash
python -m pytest training -q
python -m training train --preset base --epochs 1 --max-train-years 1 --out artifacts/smoke
python -m training ensemble --preset smoke --fusion owa --seeds 0 --epochs 1 --max-train-years 2 --out artifacts/smoke-ensemble
```
Sample data: none for RF25. Tests use generated worlds. Sample config: `qc/configs/base.yaml`.
