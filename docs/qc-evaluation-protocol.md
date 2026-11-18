# QC evaluation protocol: standing rules

Rules that must hold for any reported result. Decisions behind them are on the wayfinder map (issue #10).

## Fusion false-alarm budgets are fixed on validation data only

- The two operating points (final flag, review flag) are false-alarm budgets chosen from validation-year curves only (2013-2017; the fusion is fitted on 2013-2015 and thresholds are chosen on clean 2016-2017 data).
- They are fixed **before any 2018-or-later data is scored**, and are not changed afterwards.

**Status (2026-11-16): not yet fixed.** No validation curves exist yet and no test-year data has been scored by the QC system. When the budgets are chosen, fill in the log below in the same commit, before the first test run.

| date | budgets chosen (final / review, per 1000 clean cell-days) | commit of the validation curves | confirmed no 2018+ data scored before this commit |
|---|---|---|---|
| | | | |

## Bridge check of a live daily product: acceptance rule (frozen 2026-11-18, before any run)

Applies to `qc/bridge.py` and the `bridge:` block of `ml-service/qc/configs/base.yaml`. Confirmed by the owner on 2026-11-18 and to be committed before the check is run. No product data has been compared with RF25 yet.

- Pass/fail at a rain threshold of **0.5 mm/day**; the same agreement scores at **2.5 mm/day** are reported only.
- Pass limits: Peirce skill score >= 0.5; false alarm ratio <= 0.5; |mean bias| <= 20%; percentage RMSE <= 150%; cell-level pooled correlation >= 0.8 (the all-India area-mean correlation is reported beside it).
- Model shift: if the p99 of the daily-model scores on the product divided by the p99 on RF25 lies outside 0.8 to 1.25 it is a **warning**, not a failure: recalibrate the standardisation reference on the product's clean days before using it.
- Years: **2016 and 2017 only**. Late 2015 (a partial year) and every test year (2018 onward) are refused by the code.
- The day lag (-1, 0, +1) is chosen on these years, written here, and then frozen.

| date | rule frozen | commit | lag chosen (after the run) | result |
|---|---|---|---|---|
| 2026-11-18 | as above | | | not run |

## Normalization must not squash protected heavy rain

- The existing transform (`ml-service/training/transform.py`) is `log1p(mm) / scale`, with `scale` taken from the 99.9th percentile of training wet days. It rescales but does **not** truncate, so values above that percentile keep their order and size.
- Any new per-client normalization must keep this property: no clipping or quantile truncation of the input (as in Q99 truncation normalization), or protected extremes would be flattened before any component sees them. The build adds a test for this.
