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

## Normalization must not squash protected heavy rain

- The existing transform (`ml-service/training/transform.py`) is `log1p(mm) / scale`, with `scale` taken from the 99.9th percentile of training wet days. It rescales but does **not** truncate, so values above that percentile keep their order and size.
- Any new per-client normalization must keep this property: no clipping or quantile truncation of the input (as in Q99 truncation normalization), or protected extremes would be flattened before any component sees them. The build adds a test for this.
