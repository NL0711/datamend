### Scale selection: monthly

SYNTHETIC faults, validation years only. Validation years 2013-2017; thresholds from [2016, 2017]. Intervals resample whole years (none below 5).

| candidate | complexity | recall at 1.0 | recall at 5.0 | false per 1,000 (out of sample) at 1.0 | event recall at 1.0 | PR-AUC | seeds |
|---|---|---|---|---|---|---|---|
| gamma_zero | 0 | 0.064 | 0.153 | 6.375 | 0.064 | 0.202 | 1 |
| loo_median | 1 | 0.039 | 0.057 | 1.706 | 0.043 | 0.149 | 1 |
| loo_kriging | 2 | 0.032 | 0.048 | 1.560 | 0.037 | 0.123 | 1 |
| gbm_neighbour | 3 | 0.036 | 0.055 | 1.382 | 0.041 | 0.145 | 1 |
| mlp_neighbour | 4 | 0.037 | 0.059 | 1.420 | 0.042 | 0.149 | 1 |

Chosen: **loo_median**. simplest candidate with recall >= 0.036 (best loo_median at 0.039 minus 1.0 standard error).
