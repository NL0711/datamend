# QC evaluation protocol: standing rules

Rules that must hold for any reported result. Decisions behind them are on the wayfinder map (issue #10).

## Fusion false-alarm budgets are fixed on validation data only

- The two operating points (final flag, review flag) are false-alarm budgets chosen from validation-year curves only (2013-2017; the fusion is fitted on 2013-2015 and thresholds are chosen on clean 2016-2017 data).
- They are fixed **before any 2018-or-later data is scored**, and are not changed afterwards.

**Status (2026-11-16): not yet fixed.** No validation curves exist yet and no test-year data has been scored by the QC system. When the budgets are chosen, fill in the log below in the same commit, before the first test run.

| date | budgets chosen (final / review, per 1000 clean cell-days) | commit of the validation curves | confirmed no 2018+ data scored before this commit |
|---|---|---|---|
| | | | |

## Architecture decision rule (frozen 2026-11-18, before any run)

Applies to `python -m qc choose-architecture`, which reads `cross_scale_validation.json` (`python -m qc cross-scale`) and writes `architecture_choice.json`. All numbers are on SYNTHETIC faults, validation years only (the held-out threshold years).

- The combinations compared are: daily only; daily plus each scale; daily plus all scales, each with the fixed `max` rule, and each also with the learned challenger described below.
- A combination replaces **daily only** only if, at the final budget (1.0 false alarms per 1,000 clean cell-days): its recall is at least **0.02 higher in absolute terms** than daily-only; its false alarms per 1,000 clean cell-days do not exceed the budget; and the share of protected extremes it flags is not higher than daily-only's. If several qualify the simplest wins (fewest scales; fixed rule before learned), and among equals the higher recall. If none qualifies the architecture is **daily only**.
- The learned fusion challenger (non-negative logistic weights fitted on the fusion-fit years 2013-2015) is just another row in the table: it replaces the fixed rule only by passing the same test against the fixed-rule row of the same scales (recall at least 0.02 higher, same two guards).
- The choice is written once with the commit and cannot be rewritten (the command refuses if the file exists). It is frozen before any test year is scored.
- The budgets (final 1.0, review 5.0) apply to whichever fused score is chosen. `set-budgets` is given the chosen component and logs its name.
- The single test pass scores the chosen architecture, the daily-only baseline and the untrained baselines, all named in the choice file before the pass starts; nothing else is scored on test. The stress years (1901-1950) are scored for evaluation only.
- The decadal scale is not part of the test pass or the fused score: it delivers a power curve on injected steps and a descriptive list of breaks in the real yearly series, labelled "network or sensor change, not distinguishable".

| date | rule frozen | commit | choice made (after the run) | commit of the choice |
|---|---|---|---|---|
| 2026-11-18 | as above | | not made | |

## STNet candidate decision rule (frozen 2026-11-19, before any test year is scored)

Applies to `python -m qc choose-stnet`, which writes `stnet_choice.json` once. SYNTHETIC faults, held-out threshold years of the validation benchmark only. It decides whether the fused score of the untrained rules and the STNet fault head replaces the best old daily fusion (`fusion_logistic`, `fusion_boosted`).

- **Provenance, stated plainly.** STNet was designed and its validation results were seen (2026-11-19) before this rule was written. The first three criteria are the cross-scale rule unchanged. The fourth was added after seeing that the unseen north-east client (3) had out-of-sample false alarms of 3.1 to 4.8 per 1,000 at a budget of 1.0. It is declared here, before any test year is scored.
- At the final budget (1.0) the candidate replaces the old daily fusion only if all four hold: recall at least **0.02 higher** (absolute) than the better old fusion; false alarms per 1,000 clean cell-days not above the budget; protected extremes flagged not higher; and **every client's** out-of-sample false-alarm rate, held-out clients included, **not above 2.0 times the budget** (`qc/calibration.py`: calibrate on one threshold year, check on the other).
- Candidates: `boosted` and `logistic` fusion of (rules, STNet fault head), each plain (one global threshold, guard checked with the `global` rule) and calibrated (each client's scores mapped through the distribution of its own clean cell-days in the threshold years, guard checked with the `regional` rule). No label is used in the calibration. If a calibrated candidate is chosen, a new region must be calibrated on its own clean history before its flags are used. The plain candidate wins over the calibrated one, then the higher recall. If none qualifies the choice is the old daily pipeline.
- **The reference needs no retraining of the old components (owner decision, 2026-11-19).** If the old daily fusions are not in the score store, the reference is read from the committed `artifacts/qc/base/ablation/ablation_s42.json` (the four-component logistic and boosted rows at budget 1.0 on the held-out threshold years), and the choice refuses unless this run's benchmark hash equals the one that file was scored on (`c37de7e3cf2be90e`). The choice file records the source and the file's hash. Cost: the old pipeline has no test-year numbers next to STNet, so the final report can compare STNet with the old pipeline on validation only.
- The fusion, the regional tables and the STNet checkpoint are frozen with the choice. The budgets (final 1.0, review 5.0) are logged from the candidate's own validation curves (`stnet/stnet_curves_s<seed>.json`, written by `stnet-fuse`). The single test pass (`python -m qc stnet-test`, own lock `stnet_test.lock.json`, after the choice and the budgets are committed) scores only the chosen candidate, the untrained baselines and, if the daily test pass was done, the old daily fusions. The old daily components are not required. Nothing is refitted on a test year.
- Not tested by this rule, and not claimed: generalisation to fault kinds the generator never produced (the held-out-kinds run has not been done), and real RF25 data. Report recall on strong cell-days and event recall next to the cell-day recall; this is a reporting choice made after the results were seen, so it carries no weight in the decision.

| date | rule frozen | commit | choice made (after the run) | commit of the choice |
|---|---|---|---|---|
| 2026-11-19 | as above | | not made | |

## Benchmark hash (changed 2026-11-18)

The pin on the frozen daily benchmark (`benchmark.expected_hash`, previously 442851b03d5f95a4) was removed by the owner. The hash is still computed and written into the benchmark manifest, the budgets log and the test report, so a changed benchmark is visible in every result, but scoring no longer refuses a different one. The check that the benchmark was built for the same split manifest still applies. Say which benchmark hash a result used whenever a result is reported.

## Bridge check of a live daily product: acceptance rule (frozen 2026-11-18, before any run)

Applies to `qc/bridge.py` and the `bridge:` block of `ml-service/qc/configs/base.yaml`. Confirmed by the owner on 2026-11-18 and to be committed before the check is run. No product data has been compared with RF25 yet.

- Pass/fail at a rain threshold of **0.5 mm/day**; the same agreement scores at **2.5 mm/day** are reported only.
- Pass limits: Peirce skill score >= 0.5; false alarm ratio <= 0.5; |mean bias| <= 20%; percentage RMSE <= 150%; cell-level pooled correlation >= 0.8 (the all-India area-mean correlation is reported beside it).
- Model shift: if the p99 of the daily-model scores on the product divided by the p99 on RF25 lies outside 0.8 to 1.25 it is a **warning**, not a failure: recalibrate the standardisation reference on the product's clean days before using it.
- Years: **the validation years 2013 to 2017, never a test year**. This was first frozen as 2016 and 2017 only (the IMD merged grid exists from October 2015); on 2026-11-18, before any run, it was widened because NASA IMERG Late V07, then the chosen live source, covers all five years. IMERG was dropped the same day, so no gridded product is bridged at present and this rule is unused unless one is added. Every year outside 2013-2017, and every test year (2018 onward), is refused by the code. A product that covers fewer years is simply given fewer.
- The day lag (-1, 0, +1) is chosen on these years, written here, and then frozen.

| date | rule frozen | commit | lag chosen (after the run) | result |
|---|---|---|---|---|
| 2026-11-18 | as above | | | not run |

## STNet long-memory test (exploratory, rule written 2026-11-20 before any run)

Applies to notebook E (`ml-service/notebooks/kaggle/stnet_E_longmemory.ipynb`) and `python -m qc paired`. SYNTHETIC faults, validation years 2013 to 2017 only; no test or stress year is read. One seed.

- **What is varied.** Only the long-memory LSTM (stage 2) is retrained, from a finished stage-1 encoder (`--init-from`), at two lengths with the same width: 8 epochs x 300 steps and 30 x 600. The baseline is the stage-1 run itself, which had 3 x 30 (17 s). Session 2 repeats this from the hold run, whose encoder never saw zeroed, scale and drift.
- **Hypothesis.** Drift only: a 21 to 60 day ramp, longer than the 16-day window of the encoder. Scale and zeroed last 1 to 7 days, inside that window, so they are controls and should not move.
- **Rule.** Long memory helped if drift gains at least 0.05 PR-AUC (mean over the validation years) and 0.05 event recall at the 1-per-1,000 false-alarm budget, with false alerts per 1,000 clean cell-days no more than 0.1 above the baseline. The 0.05 is a decision, not a measured noise level. If a control moves by 0.05 or more the cause is not memory alone. If the rule is not met the wording is "no gain on this encoder", never "long memory is useless": the LSTM only sees the features of a frozen 16-day encoder.
- **Intervals.** Paired resample of whole years with regions fixed (all resamples enumerated with 5 years), per `docs/research/bootstrap-unit-check.md`. With 5 years it undercovers; it is a rough guide. The per-year differences and the number of years each side wins are reported next to it.
- **Overfitting.** Stage 2 sees only 3 years of weather. A validation-year loss is logged per long-memory epoch and the best epoch is kept as `_best.pt`; the final (last) epoch is the one scored.
- **Limits.** The faults come from the generator the LSTM trains on, so a gain shows in-distribution detection of synthetic faults only; unseen-kind behaviour is checked only by session 2. Nothing here says anything about real faults.

| date | rule frozen | commit | run | result |
|---|---|---|---|---|
| 2026-11-20 | as above | 02fd028 | session 1 (main run encoder, Kaggle, 2 x T4): run 2026-11-20. Session 2 (hold run encoder): not run | **Rule not met for either length; "no gain on this encoder".** Drift PR-AUC 0.011 (baseline) to 0.012 (lmb) and 0.008 (lmc); drift event recall 0.242 to 0.311 (lmb) and 0.250 (lmc). lmb's +0.068 event recall does not count: the control `zeroed` rose by +0.084 event recall, so the cause is not memory alone, and lmb's false alerts rose from 1.60 to 2.09 per 1,000 (limit +0.1). lmc: no drift gain and false alerts 1.90. Validation loss of lmc moved between 0.033 and 0.044 for 30 epochs without a trend. The frozen encoder's linear probe separates drift (AUC 0.895) yet the fault head recalls about 3% of drift cell-days at the budget, so the limit is not the LSTM length. Gains elsewhere were small: `stuck` recall +0.07 to +0.09 in 5 of 5 years, `spike` and `phantom_rain` PR-AUC lower. The final weights of both runs are not used. SYNTHETIC faults, validation years, one seed. |

## Drift check (CUSUM): rule written 2026-11-20 before any run

Applies to `python -m qc drift-check` and the component `drift_cusum` (`qc/drift.py`). SYNTHETIC faults, validation years 2013 to 2017 only; thresholds from the clean threshold years 2016 and 2017 as for every component; no test or stress year is read. One seed (the check itself has no training).

- **Why.** The long-memory test showed the STNet fault head recalls about 3% of drift cell-days (event recall 0.24) at the 1-per-1,000 budget, and the untrained `slow` component 1.5% of drift events. 77% of the synthetic drift cell-days change the rain value by under 1 mm, so a per-day check cannot see most of them; an accumulating check might.
- **What it is.** Untrained and causal. Per cell and day, the residual of log1p(rain) from the median of the neighbours outside the hidden disc, divided by a robust spread of the block's wet-day residuals, clipped to plus or minus 3; a two-sided leaky CUSUM over the 90 history days and the scored year, updated only on days when the cell or its neighbours are wet. Score = the larger of the two sums. The clip limits one day's weight inside this score only; no input of any other component is clipped.
- **Parameters, fixed now and not tuned on validation data:** clip 3, reference k = 0.5 (in units of the spread), leak 0.97 per wet day, wet = above 0.3 mm, spread floor 0.1. Changing any of them after seeing the result is a new rule row with a new run, not a retune.
- **Comparison.** `drift_cusum` against the STNet fault head of the main run (`stnet_fault_s42`) on the drift kind, at the 1-per-1,000 budget, with the paired whole-year interval (`qc/paired.py`), per `docs/research/bootstrap-unit-check.md`.
- **Rule.** The check helps with drift if all four hold: drift event recall is at least **0.40** and at least **0.10** above the STNet fault head; drift PR-AUC (mean over the validation years) is at least **0.05** above it; false alerts per 1,000 clean cell-days are not above **2.0**; and the share of protected extremes flagged is not above **2%**. The numbers are decisions, not measured noise levels. Median detection delay of drift events is reported and does not decide.
- **Controls reported, not decisive.** The other kinds are listed. If the check flags many non-drift faults, the wording is "it flags changes, not drift in particular".
- **If met:** drift becomes a candidate evidence channel. Adding it to a fused score needs a new fusion and a new selection rule frozen before any test year. **If not met:** "no gain from this check", recorded here, and drift stays a documented gap.
- **Limits.** The drift generator is ours (a ramp that scales the value by 1.3 to 2.5 or adds 1 to 10 mm on wet days), so a pass shows detection of synthetic ramps only. Nothing here says anything about real sensor drift or gradual network changes.

| date | rule frozen | commit | run | result |
|---|---|---|---|---|
| 2026-11-20 | as above | | not run | |

## Normalization must not squash protected heavy rain

- The existing transform (`ml-service/training/transform.py`) is `log1p(mm) / scale`, with `scale` taken from the 99.9th percentile of training wet days. It rescales but does **not** truncate, so values above that percentile keep their order and size.
- Any new per-client normalization must keep this property: no clipping or quantile truncation of the input (as in Q99 truncation normalization), or protected extremes would be flattened before any component sees them. The build adds a test for this.
