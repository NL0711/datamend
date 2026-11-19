### Cross-scale fusion (validation, SYNTHETIC faults, held-out threshold years only)

Evaluation years [2016, 2017]; fixed `max` rule; coherent-extreme factor 0.5. the daily fusion is fitted on the fusion-fit years, so only the threshold years are held out thresholds come from the clean version of the same years (as in the existing validation curves) 2 evaluation years: no confidence interval (fewer than 5 years)

| combination | budget per 1,000 | recall | event recall | false per 1,000 clean | protected extremes flagged | PR-AUC |
|---|---|---|---|---|---|---|
| daily only | 0.5 | 0.359 | 0.515 | 0.506 | 0.057 | 0.459 |
| daily only | 1 | 0.436 | 0.573 | 1.052 | 0.108 | 0.459 |
| daily only | 2 | 0.445 | 0.634 | 2.054 | 0.164 | 0.459 |
| daily only | 5 | 0.462 | 0.741 | 5.015 | 0.226 | 0.459 |
| daily only | 10 | 0.487 | 0.834 | 9.965 | 0.285 | 0.459 |
| daily + monthly | 0.5 | 0.360 | 0.529 | 1.720 | 0.031 | 0.413 |
| daily + monthly | 1 | 0.439 | 0.573 | 4.778 | 0.047 | 0.413 |
| daily + monthly | 2 | 0.479 | 0.610 | 7.889 | 0.064 | 0.413 |
| daily + monthly | 5 | 0.490 | 0.634 | 12.756 | 0.079 | 0.413 |
| daily + monthly | 10 | 0.510 | 0.660 | 19.294 | 0.091 | 0.413 |
| daily + monthly (learned) | 0.5 | 0.358 | 0.512 | 0.531 | 0.010 | 0.473 |
| daily + monthly (learned) | 1 | 0.436 | 0.573 | 1.061 | 0.039 | 0.473 |
| daily + monthly (learned) | 2 | 0.450 | 0.640 | 2.103 | 0.084 | 0.473 |
| daily + monthly (learned) | 5 | 0.488 | 0.759 | 6.720 | 0.134 | 0.473 |
| daily + monthly (learned) | 10 | 0.530 | 0.846 | 14.019 | 0.170 | 0.473 |
| daily + yearly | 0.5 | 0.365 | 0.517 | 2.109 | 0.031 | 0.367 |
| daily + yearly | 1 | 0.421 | 0.547 | 3.678 | 0.044 | 0.367 |
| daily + yearly | 2 | 0.451 | 0.578 | 5.578 | 0.064 | 0.367 |
| daily + yearly | 5 | 0.461 | 0.631 | 16.446 | 0.080 | 0.367 |
| daily + yearly | 10 | 0.464 | 0.640 | 22.387 | 0.080 | 0.367 |
| daily + yearly (learned) | 0.5 | 0.359 | 0.515 | 0.506 | 0.011 | 0.466 |
| daily + yearly (learned) | 1 | 0.436 | 0.573 | 1.052 | 0.041 | 0.466 |
| daily + yearly (learned) | 2 | 0.445 | 0.634 | 2.054 | 0.087 | 0.466 |
| daily + yearly (learned) | 5 | 0.462 | 0.741 | 5.015 | 0.139 | 0.466 |
| daily + yearly (learned) | 10 | 0.487 | 0.834 | 9.965 | 0.183 | 0.466 |
| daily + monthly + yearly | 0.5 | 0.365 | 0.532 | 3.281 | 0.031 | 0.367 |
| daily + monthly + yearly | 1 | 0.433 | 0.567 | 6.868 | 0.043 | 0.367 |
| daily + monthly + yearly | 2 | 0.476 | 0.599 | 10.027 | 0.057 | 0.367 |
| daily + monthly + yearly | 5 | 0.497 | 0.651 | 22.590 | 0.071 | 0.367 |
| daily + monthly + yearly | 10 | 0.505 | 0.666 | 29.429 | 0.080 | 0.367 |
| daily + monthly + yearly (learned) | 0.5 | 0.358 | 0.512 | 0.531 | 0.010 | 0.473 |
| daily + monthly + yearly (learned) | 1 | 0.436 | 0.573 | 1.061 | 0.039 | 0.473 |
| daily + monthly + yearly (learned) | 2 | 0.450 | 0.640 | 2.103 | 0.084 | 0.473 |
| daily + monthly + yearly (learned) | 5 | 0.488 | 0.759 | 6.720 | 0.134 | 0.473 |
| daily + monthly + yearly (learned) | 10 | 0.530 | 0.846 | 14.018 | 0.170 | 0.473 |
