# QC evaluation protocol: standing rules

Rules that must hold for any reported result. Decisions behind them are on the wayfinder map (issue #10).

## Fusion false-alarm budgets are fixed on validation data only

- The two operating points (final flag, review flag) are false-alarm budgets chosen from validation-year curves only (2013-2017; the fusion is fitted on 2013-2015 and thresholds are chosen on clean 2016-2017 data).
- They are fixed **before any 2018-or-later data is scored**, and are not changed afterwards.

**Status (2026-11-16): not yet fixed.** No validation curves exist yet and no test-year data has been scored by the QC system. When the budgets are chosen, fill in the log below in the same commit, before the first test run.

| date | budgets chosen (final / review, per 1000 clean cell-days) | commit of the validation curves | confirmed no 2018+ data scored before this commit |
|---|---|---|---|
| | | | |

## Normalization must not squash protected heavy rain

- The existing transform (`ml-service/training/transform.py`) is `log1p(mm) / scale`, with `scale` taken from the 99.9th percentile of training wet days. It rescales but does **not** truncate, so values above that percentile keep their order and size.
- Any new per-client normalization must keep this property: no clipping or quantile truncation of the input (as in Q99 truncation normalization), or protected extremes would be flattened before any component sees them. The build adds a test for this.
