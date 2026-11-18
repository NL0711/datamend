# Multi-resolution rainfall QC pipeline: build spec

Status: PROPOSED, updated 2026-11-18 with the owner's decisions and `docs/research/multires-models-evaluation-live-source.md` (agent-written, not reviewed line by line). Only the resolution data layer (`ml-service/qc/resolution.py`) and the run tooling (`ml-service/scripts/fetch_rf25.py`, `run_qc.py`) exist. Everything else below is NOT BUILT. Nothing has run on real RF25.

Rule from the owner (2026-11-18): build the complete pipeline first, so that all real training is done once, on the architecture the evidence supports. While the architecture is not final, web-app work is limited to improvements; the temperature/pressure/humidity removal is decided but waits (`docs/PROJECT_OVERVIEW_WEBAPP.md`, section 8a).

## 0. Decisions made by the owner (2026-11-18)

1. **Live daily input: IMD's own near-real-time merged grid** (see section 7). Subject to confirming access terms and archive depth.
2. **Regional output: IMD's regional units**, the 36 meteorological sub-divisions and the 4 homogeneous regions (section 6b).
3. **Monthly/seasonal scale: confirmed**, together with the yearly scale. Candidate models per section 4.
4. **Accepted as stated, with the labels kept in the docs:** leave-one-out neighbour kriging with a ratio cut of 3 (El Hachem et al. 2022) is a single-paper proposal; gamma plus a zero-probability term is documented practice; pooled gradient-boosted regression and daily scores as features have no precedent found and stay experiments; the block bootstrap is this project's own choice.
5. Validation on synthetic faults is acceptable for a first estimate, always labelled synthetic.

## 1. Principle: choose the architecture by validation, not by assumption

Each time scale has baselines and candidate models behind one interface. All are trained and scored on the same frozen synthetic benchmark, validation years only. The simplest candidate that is not clearly worse than the best is kept. The choice is logged before any test year is scored. Test years are scored once, for the chosen architecture only.

## 2. Pipeline

```
RF25 files (Kaggle dataset, 125 files, 1901-2025)         scripts/fetch_rf25.py            BUILT
  -> data contract, splits, client map, leakage audit      qc prepare                       BUILT (generated worlds only)
  -> resolution layer: daily, monthly, seasonal, yearly    qc/resolution.py                 BUILT (11 unit tests)
  -> frozen synthetic benchmark per scale                   daily BUILT; period-level NOT BUILT
  -> scorers per scale (baselines + candidates)             daily BUILT; others NOT BUILT
  -> selection on validation, logged                        NOT BUILT
  -> cross-scale fusion + false-alarm budgets               daily fusion BUILT; cross-scale NOT BUILT
  -> single test pass (chosen architecture only)            BUILT for daily
  -> score export (schema 1) + regional aggregation         NOT BUILT
  -> live daily input (IMD merged grid) via a bridge check  NOT BUILT
  -> web app reads exported scores                          NOT BUILT (docs/LOCATIONS_MODEL_SCORES_PLAN.md)
```

## 3. Scorer interface (the seam)

- `fit(train_periods, stats, rng) -> artifact` uses training years only.
- `score(periods, artifact) -> (P, n_land)`; higher means more suspicious; NaN where the period is not valid.
- Inputs it may use: the target cell's own history and its neighbours' values with the target and a hidden radius removed, climatology, season. Never the target period's own value, never a later period.
- Outputs are standardised on clean threshold years, as the daily components are.

Seam placement: between the resolution layer and the scorers, and between the scorers and fusion. Each scale has a baseline and at least one candidate, so the seam is real.

## 4. Baselines and candidates per scale

| Scale | Baselines (no training) | Candidates | Evidence |
|---|---|---|---|
| Daily | rules, slow, neighbour average | spatial net, temporal GRU (built); LSTM and Mamba-style temporal as optional candidates, kept only if they beat the GRU at equal tuning | existing code |
| Monthly / seasonal | (a) gamma-with-zero standardised total per calendar month: a zero-probability term plus a fitted gamma, instead of a plain z-score; (b) leave-one-out neighbour residual: predict the cell from its neighbours by kriging with the target left out, flag when residual over kriging spread exceeds 3 on Box-Cox values | pooled gradient-boosted neighbour regression (target hidden); small masked-neighbour net with a zero-inflated Gamma head | (a) documented practice, WMO 30-year minimum; (b) one paper, one network; pooled regression: no rainfall QC precedent found, experiment only |
| Yearly | same two baselines at yearly totals | pooled gradient-boosted or quantile regression with the target hidden; the same plus aggregated daily and monthly scores as features | features from daily scores are not independent of the daily model (same neighbours): keep only if they beat the baselines on validation, and say so |
| Decadal | none | pairwise ratio change-point tests (SNHT-style, Pettitt, CUSUM); thresholds set by simulation | tests, not models; results confounded by gauge-network changes in RF25: label hits "network or sensor change, not distinguishable" |

About 62 usable training years at the yearly scale means small models only. Basis for all rows: `docs/research/rainfall-qc-without-labels.md`, `docs/research/multires-models-evaluation-live-source.md`.

## 5. Selection protocol (validation only)

1. Frozen synthetic benchmark per scale: aggregated daily faults (`aggregate_labels`, `visible` labels) plus period-level faults (`corrupt_periods`). Hashed and pinned like the daily benchmark.
2. Train every candidate and baseline for at least 3 seeds. Same data, same budget.
3. Metrics: PR-AUC, recall at the final and review budgets, false alarms per 1,000 clean periods, and **range-based event recall and false alarms** (an event is a run of flagged periods). **Point-adjusted F1 is not used.**
4. Intervals: block bootstrap. **The resampling unit is whole years crossed with the 8 client regions** (resampling cells would overstate certainty, because neighbouring cells share gauges). This is the project's own choice; no QC paper found uses it.
5. Keep the simplest candidate whose recall at the budget is within one standard error of the best. Record the choice and evidence in `docs/qc-evaluation-protocol.md` and commit it.
6. Genuine-extreme check: a spatially coherent heavy period must not be flagged above the budget.
7. Budgets are already picked (final 1.0, review 5.0 per 1,000 clean cell-days). They are logged with `run_qc.py budgets` and the protocol file is committed before the single test pass.

## 6. Cross-scale fusion and regional output

**Fusion.** Default is fixed and label-free: standardise each scale's score on clean threshold years and combine by maximum or noisy-OR, after aligning the scales (a daily score maps to its month and year). A learned fusion (logistic on scale scores, fitted on 2013-2015 synthetic faults only) is a challenger and must beat the fixed rule on 2016-2017. A coherent-extreme rule lowers confidence when neighbours and several scales agree. Output keeps two meanings apart: "unusual weather" and "suspect data".

**6b. Regional output (IMD units).** Aggregate by the **36 meteorological sub-divisions** and the **4 homogeneous regions**, the units IMD uses for regional rainfall summaries (IMD SOP; district rainfall is a mean of stations, sub-division and region values are area-weighted). For each unit and period report: the area-weighted share of suspect cells at the review and final flags, the number of review items, and the strongest scale. IMD's departure-from-normal bands may be shown beside it for weather context only. The suspect-data output must **not** reuse IMD's category names, because it measures data quality, not rainfall. Open: the sub-division boundary file is not in the repo and must be sourced from IMD.

## 7. Live input (daily scale only): IMD merged grid

Chosen: the IMD/NCMRWF near-real-time daily GPM-merged 0.25 degree grid, `https://imdpune.gov.in/cmpg/Realtimedata/gpm/Rain_Download.html` (algorithm paper: https://link.springer.com/article/10.1007/s12040-025-02550-0). I opened the page: it offers a binary daily file picked by date with a sample control file and a map-grid file (241 x 281), and states no day definition, latency, period or usage terms. The research agent, from the paper, reports: IMERG Late corrected with about 2,600 IMD gauges, a 03 UTC day, about 1-day latency, running since October 2015, validated only for July 2014 against RF25. I have not read the paper myself.

Known issues, all to be handled before any live score is shown:
- **Not independent of RF25.** It is tuned with IMD gauges, so agreement with RF25 is partly built in. Say so wherever a bridge result is shown.
- **Access terms and archive depth unconfirmed**, and whether scripted download is allowed. Ask IMD before automating.
- **Day alignment.** IMD's day is 08:30 IST to 08:30 IST (03 UTC to 03 UTC). Which date RF25 gives an 08:30 reading is undocumented, so measure it (lags -1, 0, +1 day against all-India and sub-division daily means) on 2016-2017 and freeze the result.
- **Overlap with validation years is short:** the product exists from October 2015, so only about 2016-2017 can be used for the bridge check. Never the test years 2018-2025. A pre-written acceptance rule is needed before looking (agreement metrics: rain/no-rain at 0.5 mm per day with false alarm ratio, equitable threat score, Peirce skill score, percentage RMSE, mean bias, by region and season).
- **Model shift step:** score the product with the RF25-trained daily models on 2016-2017 and compare the score distribution with RF25's. A large shift means the daily models are not valid on this product without recalibration.

Fallbacks, in order: IMERG Late V07 rebuilt from half-hourly slices to end at 03 UTC (a UTC-day file overlaps IMD's day by only 3 hours), IMERG Early (about 4 hours), GSMaP near-real-time (registration and redistribution terms). CHIRPS preliminary is not used at daily scale: its daily values are pentad totals spread with IMERG Late's shape, and the owner discourages them for daily extremes. Open-Meteo is display only.

## 8. Build order

1. Scorer interface; baselines (gamma-with-zero, leave-one-out residual); period-level benchmark with a pinned hash.
2. Candidates: pooled regressors and the masked-neighbour net (monthly, yearly); decadal change-point tests.
3. Selection harness and its protocol-log entry.
4. Cross-scale fusion and the coherent-extreme rule.
5. Score export, sub-division boundary source, regional aggregation (6b).
6. Bridge check for the IMD merged grid (day alignment, acceptance rule, model-shift step), then the live daily path.
7. Only after the architecture is fixed: full training, budgets log, single test pass.

## 9. Open items

- Confirm IMD's access terms and the archive depth of the merged grid.
- Source the 36 sub-division and 4 region boundaries.
- Whether LSTM and Mamba-style candidates are worth adding to the daily temporal slot.
