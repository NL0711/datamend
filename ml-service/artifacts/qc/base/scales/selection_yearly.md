### Scale selection: yearly

SYNTHETIC faults, validation years only. Validation years 2013-2017; thresholds from [2016, 2017]. Intervals resample whole years (none below 5).

| candidate | complexity | recall at 1.0 | recall at 5.0 | false per 1,000 (out of sample) at 1.0 | event recall at 1.0 | PR-AUC | seeds |
|---|---|---|---|---|---|---|---|
| gamma_zero | 0 | 0.057 | 0.060 | 1.131 | 0.057 | 0.394 | 1 |
| loo_median | 1 | 0.035 | 0.045 | 1.690 | 0.035 | 0.410 | 1 |
| loo_kriging | 2 | 0.005 | 0.017 | 1.126 | 0.005 | 0.383 | 1 |
| gbm_neighbour | 3 | 0.035 | 0.049 | 2.065 | 0.035 | 0.420 | 1 |
| mlp_neighbour | 4 | 0.002 | 0.023 | 1.502 | 0.002 | 0.403 | 1 |

Chosen: **gamma_zero**. simplest candidate with recall >= 0.053 (best gamma_zero at 0.057 minus 1.0 standard error).
