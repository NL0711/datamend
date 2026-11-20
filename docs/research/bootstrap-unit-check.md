# Which unit should the QC confidence intervals resample? (simulation check, 2026-11-18)

Question: the pipeline spec proposed a block bootstrap that resamples whole years crossed with the 8 client regions. Is that suitable?

**STATUS: generated data only.** The simulation (`docs/research/bootstrap_unit_check.py`, seed 1, 1,200 repetitions, 400 resamples) uses invented variance components, not RF25 results. It shows how the interval methods rank, not what real intervals will be. Percentile bootstrap, nominal 95%.

## Setup

Detection probability of a fault event in year y, region r: `logistic(mu + a_y + b_r + c_yr)`, with `a_y` a year effect shared by all regions (a strong or weak monsoon), `b_r` a region effect, `c_yr` local noise; 200 events per year-region; recall = pooled detected / events. Eight regions, 5 years (validation 2013-2017) or 8 years (test 2018-2025). Two targets:

- **Same 8 regions, new years and new fault draws.** This is the claim made for the test years.
- **A population of regions** (what a claim about unseen regions needs).

## Result (coverage of the nominal 95% interval)

| method | same 8 regions, new years | population of regions |
|---|---|---|
| event-level iid (what `qc/metrics.py` does for recall) | 14-62% | 9-14% |
| whole years, regions fixed | 84-90% | 25-73% |
| whole regions, years fixed | 86-100% | 74-89% |
| years x regions crossed | 97-100% | 89-92% |

Intervals from the crossed bootstrap were about twice as wide as the year-only ones for the first target.

## What follows

1. **Event-level resampling is badly overconfident.** Events in the same year and region are not independent, so recall intervals from `qc/metrics.py` (`recall_ci`, `event_recall_ci`) are too narrow, in the simulation by a wide margin. The false-alert interval there resamples years, which is better but uses only the 2 threshold years (a total of 4 distinct resamples).
2. **Resampling regions is not wanted for the claim "on these 8 regions".** The regions are fixed; resampling them adds between-region spread that would not recur. It is the right move only for claims about regions that were not tested.
3. **Whole years with regions fixed is the right primary interval for the test-year claim**, but with 5 to 8 years it still undercovers (about 84-90% for a 95% interval). State that, or use a mixed model (beta-binomial with random year and region effects).
4. **Crossed years x regions is the safer choice for claims about unseen regions** (held-out clients 3 and 6), near but below nominal (about 90%) because there are only 8 regions.
5. Not in the simulation: correlation of the local noise between neighbouring regions, trends over years, and fault-placement variance from the frozen benchmark. These push real coverage lower than shown.

## Where it is used (2026-11-20)

`qc/paired.py` (`python -m qc paired`) follows this recommendation for comparing two stored runs: whole years resampled together, regions fixed, every resample enumerated with 5 years, no interval below 5 years. The event-level `recall_ci` and `event_recall_ci` in `qc/metrics.py` are NOT yet replaced.

## Recommendation (opinion)

Report per-region results as the primary table; interval for the overall number by whole-year resampling with regions fixed, with the stated undercoverage; crossed years x regions only for unseen-region claims. Replace the event-level recall interval in `qc/metrics.py`. Do not report any interval from fewer than 5 resampled years.
