# Multi-resolution rainfall QC pipeline: build spec

Status: updated 2026-11-18 with the owner's decisions and `docs/research/multires-models-evaluation-live-source.md` (agent-written, not reviewed line by line). The code for every stage below now exists and is unit-tested on generated arrays and a generated world (see the pipeline block). **Nothing has run on real RF25: no benchmark, scorer, selection or bridge result exists.** Items marked NOT IMPLEMENTED are listed in section 9.

Rule from the owner (2026-11-18): build the complete pipeline first, so that all real training is done once, on the architecture the evidence supports. While the architecture is not final, web-app work is limited to improvements; the temperature/pressure/humidity removal is decided but waits (`docs/PROJECT_OVERVIEW_WEBAPP.md`, section 8a).

## 0. Decisions made by the owner (2026-11-18)

1. **Live daily input: IMD's own near-real-time merged grid** (see section 7). Subject to confirming access terms and archive depth.
2. **Regional output: IMD's regional units**, the 36 meteorological sub-divisions and the 4 homogeneous regions (section 6b).
3. **Monthly/seasonal scale: confirmed**, together with the yearly scale. Candidate models per section 4.
4. **Accepted as stated, with the labels kept in the docs:** leave-one-out neighbour kriging with a ratio cut of 3 (El Hachem et al. 2022) is a single-paper proposal; gamma plus a zero-probability term is documented practice; pooled gradient-boosted regression and daily scores as features have no precedent found and stay experiments; the bootstrap unit is this project's own choice, revised after a simulation check (section 5, item 4).
5. Validation on synthetic faults is acceptable for a first estimate, always labelled synthetic.
6. **Regions (2026-11-18):** the first real run uses the 8 client regions as a labelled stand-in; IMD sub-divisions are added when sourced. A cell goes to the region with the largest share of its area (`assign_by_area_share`); the 4 homogeneous regions are unions of the 36 sub-divisions (`derive_regions`).
7. **Live path (2026-11-18):** parked until IMD's terms and file layout are confirmed; IMERG Late rebuilt to a 03 UTC day is the fallback if IMD declines. Nothing else depends on it.
8. **Bridge rule (2026-11-18):** frozen in `docs/qc-evaluation-protocol.md` and the `bridge:` config block: pass/fail at 0.5 mm/day with 2.5 mm reported only; PSS >= 0.5, FAR <= 0.5, |bias| <= 20%, percentage RMSE <= 150%, cell-level correlation >= 0.8 (area-mean reported beside it); a model shift outside 0.8 to 1.25 of the p99 ratio is a warning that triggers recalibration; years 2016 and 2017 only.
9. **Boundary and orientation (2026-11-18):** IMD's boundary file is used as published (no licence stated; fetched by script, not committed; checked as degrees by the known-place test); IMD's four regions are the file's own: CENTRAL INDIA, EAST AND NORTH EAST INDIA, NORTH WEST INDIA, SOUTH PENINSULA. Both the known-place test and the RF25 orientation check must pass before any regional or live-product output is shown. Contacting IMD was dropped as irrelevant while the live path is parked.

## 1. Principle: choose the architecture by validation, not by assumption

Each time scale has baselines and candidate models behind one interface. All are trained and scored on the same frozen synthetic benchmark, validation years only. The simplest candidate that is not clearly worse than the best is kept. The choice is logged before any test year is scored. Test years are scored once, for the chosen architecture only.

## 2. Pipeline

```
RF25 files (Kaggle dataset, 125 files, 1901-2025)         scripts/fetch_rf25.py            BUILT
  -> data contract, splits, client map, leakage audit      qc prepare                       BUILT (generated worlds only)
  -> resolution layer: daily, monthly, seasonal, yearly    qc/resolution.py                 BUILT (11 unit tests)
  -> frozen synthetic benchmark per scale                   qc/period_benchmark.py (`qc period-benchmark`)   BUILT, generated world only
  -> scorers per scale (baselines + candidates)             qc/scale_scorers.py                              BUILT, generated arrays only
  -> selection on validation, logged                        qc/scale_select.py (`qc scale-select`)           BUILT, generated data only
  -> decadal change-point tests                             qc/changepoint.py                                BUILT, generated series only
  -> cross-scale fusion (fixed rule)                        qc/crossscale.py                                 BUILT, not yet wired to the daily scores
  -> single test pass (chosen architecture only)            BUILT for daily; cross-scale test pass NOT WIRED
  -> regional aggregation                                   qc/regions.py                                    BUILT; IMD's boundary JSON loader and acceptance checks in qc/imd_regions.py (file fetched by scripts/fetch_imd_regions.py, not committed; licence not stated)
  -> score export (schema 1)                                NOT BUILT
  -> live daily input (IMD merged grid) via a bridge check  qc/bridge.py, qc/imd_merged.py                  BUILT; file layout partly established, the ROW ORDER is NOT (decided by verify_orientation against RF25); live path parked
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
4. Intervals (checked by simulation on generated data, `docs/research/bootstrap-unit-check.md`): the primary table is per region. The overall interval resamples whole years with the regions fixed, because the claim is about these 8 regions in new years; with 5 validation or 8 test years it still undercovers (about 84-90% for a nominal 95%), and that is stated next to every interval. Claims about unseen regions (held-out clients 3 and 6) use years crossed with regions. Event-level resampling is not used: events in one year and region are not independent. No interval is reported from fewer than 5 resampled years. This choice is the project's own; no QC paper found uses it.
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

## 9. What the new code does and does not do (2026-11-18)

- `scale_scorers.py`: baselines `gamma_zero` and `loo_median`; candidates `gbm_neighbour` and `mlp_neighbour` (scikit-learn, not the Gamma-head network). The leave-one-out baseline uses the MEDIAN of the neighbours: a first version with an inverse-distance weighted mean smeared one bad cell into its neighbours (a test showed a neighbour's score rising by more than a third of the bad cell's rise). Kriging is NOT IMPLEMENTED.
- `scale_select.py`: thresholds from clean threshold-year periods; recall on all validation years; false alarms reported out of sample (non-threshold years) and on all years; whole-year bootstrap intervals, none below 5 years. With the real 5 validation years and 2 threshold years only 3 years are out of sample, so no interval is given for false alarms.
- `crossscale.py`: fixed max or noisy-OR (the sum of ratios) with the coherent-extreme discount. A learned fusion is NOT IMPLEMENTED. It is not yet connected to the stored daily scores.
- `regions.py` and `imd_regions.py`: IMD's own boundary file (36 sub-divisions, 4 regions from its `region_cod`) loads and was checked by hand on the RF25 land grid: all 10 known places fall in the expected sub-division by polygon, 9 of 10 by grid cell (Chennai's cell is sea in RF25, so it cannot be tested at cell level); 34 of the 36 sub-divisions have cells on the RF25 land grid (the Andaman & Nicobar and Lakshadweep islands have none) and 122 of 4,964 land cells are in no sub-division. The first real run still uses the 8 client regions as the labelled stand-in; the IMD map is used once the owner switches it on. No licence is stated by IMD, so no derived map is published.
- `bridge.py`: the acceptance rule is frozen (config `bridge:` block and `docs/qc-evaluation-protocol.md`): 0.5 mm/day pass/fail, 2.5 mm reported only, cell-level correlation decides, a model shift is a warning, years 2016 and 2017 only (code refuses others). `run_bridge` refuses unless `confirmed_by_owner` is true.
- `imd_merged.py`: three sample files (15 Jul 2016, 10 Jan 2017, 2 Sep 2016) fetched 2026-11-18 showed each is exactly 241 x 281 x 4 bytes, little-endian float32 (big-endian gives values near 1e38), with no undefined cells in these three. The ROW ORDER could not be established: the control file implies south-first, IMD's 0/1 map grid is north-first, and the three days gave conflicting rain-over-India hints. `read_grd` therefore requires the row order and `verify_orientation` must decide it against RF25 on the same dates on a machine that has RF25; units (assumed mm/day) and the day the value belongs to are unverified.
- `changepoint.py`: SNHT and Pettitt with simulated critical values; hits mean "network or sensor change, not distinguishable".

## 10. Open items

- Establish the row order of the merged-grid files by running `verify_orientation` against RF25 on a machine that has RF25 (several rainy days).
- IMD's access terms and the archive depth of the merged grid are still unconfirmed; no bulk download until they are known (the live path is parked).
- Decide when to switch the regional output from the 8 client regions to IMD's map (the loader and checks exist).
- Whether LSTM and Mamba-style candidates are worth adding to the daily temporal slot (my suggestion: no; see the session notes).
