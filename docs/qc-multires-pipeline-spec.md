# Multi-resolution rainfall QC pipeline: build spec

Status: updated 2026-11-18 with the owner's decisions and `docs/research/multires-models-evaluation-live-source.md` (agent-written, not reviewed line by line). The code for every stage below now exists and is unit-tested on generated arrays and a generated world (see the pipeline block). **Nothing has run on real RF25: no benchmark, scorer, selection or bridge result exists.** Items marked NOT IMPLEMENTED are listed in section 9.

Rule from the owner (2026-11-18): build the complete pipeline first, so that all real training is done once, on the architecture the evidence supports. While the architecture is not final, web-app work is limited to improvements; the temperature/pressure/humidity removal is decided but waits (`docs/PROJECT_OVERVIEW_WEBAPP.md`, section 8a).

## 0. Decisions made by the owner (2026-11-18)

1. **Live daily input: IMD's own near-real-time merged grid** (see section 7). Subject to confirming access terms and archive depth.
2. **Regional output: IMD's regional units**, the 36 meteorological sub-divisions and the 4 homogeneous regions (section 6b).
3. **Monthly/seasonal scale: confirmed**, together with the yearly scale. Candidate models per section 4.
4. **Accepted as stated, with the labels kept in the docs:** leave-one-out neighbour kriging with a ratio cut of 3 (El Hachem et al. 2022) is a single-paper proposal; gamma plus a zero-probability term is documented practice; pooled gradient-boosted regression and daily scores as features have no precedent found and stay experiments; the bootstrap unit is this project's own choice, revised after a simulation check (section 5, item 4).
5. Validation on synthetic faults is acceptable for a first estimate, always labelled synthetic.
6. **Regions (2026-11-18, revised twice the same day):** the regional OUTPUT uses IMD's 36 sub-divisions and 4 homogeneous regions (`assign_by_area_share`, `derive_regions`). The 8 clients are now ALSO built from whole IMD sub-divisions (the owner asked for the most proper architecture before any run; the k-means blobs split 17 of 34 sub-divisions across clients, so a result by sub-division or a claim about an unseen sub-division would have mixed trained and unseen cells). Clients stay the unit for training, held-out evaluation (clients 3 and 6), per-client normalisation and federated simulation; a sub-division now nests inside one client. The 4 homogeneous regions do not nest in clients (a client can span two). No command writes regional output yet.
7. **Live path (2026-11-18, superseded by decision 13 the same day):** it was first parked until IMD's terms and file layout were confirmed; the owner then chose NASA IMERG Late V07, and finally dropped IMERG and chose the AWS stations configured in the web app (decision 13).
8. **Bridge rule (2026-11-18):** frozen in `docs/qc-evaluation-protocol.md` and the `bridge:` config block: pass/fail at 0.5 mm/day with 2.5 mm reported only; PSS >= 0.5, FAR <= 0.5, |bias| <= 20%, percentage RMSE <= 150%, cell-level correlation >= 0.8 (area-mean reported beside it); a model shift outside 0.8 to 1.25 of the p99 ratio is a warning that triggers recalibration; years 2016 and 2017 only.
9. **Boundary and orientation (2026-11-18):** IMD's boundary file is used as published (no licence stated; fetched by script, not committed; checked as degrees by the known-place test); IMD's four regions are the file's own: CENTRAL INDIA, EAST AND NORTH EAST INDIA, NORTH WEST INDIA, SOUTH PENINSULA. Both the known-place test and the RF25 orientation check must pass before any regional or live-product output is shown. Contacting IMD was dropped as irrelevant while the live path is parked.
10. **Architecture rule, test scope, decadal deliverable (2026-11-18):** the rule for adopting a cross-scale combination (recall at least 0.02 higher than daily-only at the final budget, false alarms within budget, protected extremes flagged not higher, simplest wins) is frozen in `docs/qc-evaluation-protocol.md`; the budgets 1.0 and 5.0 apply to whichever fused score is chosen; the test pass scores the chosen architecture, the daily-only baseline and the untrained baselines, all named beforehand, plus the stress years for evaluation; the decadal scale delivers a power curve and a descriptive break list, outside the test pass.
11. **Regional output (2026-11-18):** per IMD sub-division and per homogeneous region: daily area-weighted share of suspect cells at the review and final flags, with a monthly roll-up, flagged cell-period counts, the driving scale and the largest connected suspect cluster; validation and test years from stored scores only (test years only after the test lock is finished); JSON with provenance for the web app and one CSV per run.
12. **More candidates (2026-11-18):** a kriging variant of the leave-one-out scorer (`loo_kriging`, a candidate not a baseline) and a learned cross-scale fusion with non-negative weights (a challenger judged by the same rule as the architecture choice).
13. **Live source (2026-11-18, final):** NASA IMERG was chosen and then DROPPED by the owner (training and data load too large). The real-time demonstration will use the AWS (automatic weather station) feeds already configured in the web app. Checked the same day: those feeds are six US radar-site IDs replayed from a CSV, carry temperature, pressure and humidity only, and have no rainfall field (section 7). A rainfall-carrying station feed, the ingestion of it and a one-station scorer are NOT BUILT, and the choice of feed is open. No gridded product is bridged at present, so the bridge check (`qc/bridge.py`) and its frozen rule are unused.

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
  -> cross-scale fusion (fixed rule + learned challenger)   qc/crossscale.py, crossscale_run.py (`qc cross-scale`, `qc choose-architecture`)   BUILT, generated world only
  -> single test pass (chosen architecture only)            daily BUILT; cross-scale qc/crossscale_test.py (`qc cross-scale-test`) BUILT, generated world only
  -> regional aggregation and output                        qc/regions.py, qc/regions_report.py (`qc regions-report`), qc/imd_regions.py   BUILT, generated world only; IMD boundary file fetched by scripts/fetch_imd_regions.py, not committed, licence not stated
  -> score export (schema 1)                                NOT BUILT
  -> live daily input (the web app's AWS stations)           NOT BUILT: the configured feeds have no rainfall field and are replayed, not live (section 7); qc/bridge.py and qc/imd_merged.py exist but are unused
  -> web app reads exported scores                          NOT BUILT (docs/LOCATIONS_MODEL_SCORES_PLAN.md)
```

## 3. Scorer interface (the seam)

- `fit(train_periods, stats, rng) -> artifact` uses training years only.
- `score(periods, artifact) -> (P, n_land)`; higher means more suspicious; NaN where the period is not valid.
- Inputs it may use: the target cell's own history and its neighbours' values with the target and a hidden radius removed, climatology, season. Never the target period's own value, never a later period.
- Outputs are standardised on clean threshold years, as the daily components are (ratio to the clean 99.9th percentile). A fused daily score (`fusion_*`) is a log-odds value that is negative on clean days, so it is read as softplus(z) = log(1 + exp(z)) before standardising (`crossscale_run.load_part`); found when the first real `cross-scale` run stopped on "the clean reference is not positive" (2026-11-18, before any result was frozen). Other scores are read as stored.

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

1. Frozen synthetic benchmark per scale: aggregated daily faults (`aggregate_labels`, `visible` labels) plus period-level faults (`corrupt_periods`). Hashed, and the hash is recorded in its manifest. The daily benchmark's pin was removed by the owner on 2026-11-18, so the hash is recorded, not enforced.
2. Train every candidate and baseline for at least 3 seeds. Same data, same budget.
3. Metrics: PR-AUC, recall at the final and review budgets, false alarms per 1,000 clean periods, and **range-based event recall and false alarms** (an event is a run of flagged periods). **Point-adjusted F1 is not used.**
4. Intervals (checked by simulation on generated data, `docs/research/bootstrap-unit-check.md`): the primary table is per region. The overall interval resamples whole years with the regions fixed, because the claim is about these 8 regions in new years; with 5 validation or 8 test years it still undercovers (about 84-90% for a nominal 95%), and that is stated next to every interval. Claims about unseen regions (held-out clients 3 and 6) use years crossed with regions. Event-level resampling is not used: events in one year and region are not independent. No interval is reported from fewer than 5 resampled years. This choice is the project's own; no QC paper found uses it.
5. Keep the simplest candidate whose recall at the budget is within one standard error of the best. Record the choice and evidence in `docs/qc-evaluation-protocol.md` and commit it.
6. Genuine-extreme check: a spatially coherent heavy period must not be flagged above the budget.
7. Budgets are already picked (final 1.0, review 5.0 per 1,000 clean cell-days). They are logged with `run_qc.py budgets` and the protocol file is committed before the single test pass.

## 6. Cross-scale fusion and regional output

**Fusion.** Default is fixed and label-free: standardise each scale's score on clean threshold years and combine by maximum or noisy-OR, after aligning the scales (a daily score maps to its month and year). A learned fusion (logistic on scale scores, fitted on 2013-2015 synthetic faults only) is a challenger and must beat the fixed rule on 2016-2017. A coherent-extreme rule lowers confidence when neighbours and several scales agree. Output keeps two meanings apart: "unusual weather" and "suspect data".

**6b. Regional output (IMD units).** Aggregate by the **36 meteorological sub-divisions** and the **4 homogeneous regions**, the units IMD uses for regional rainfall summaries (IMD SOP; district rainfall is a mean of stations, sub-division and region values are area-weighted). For each unit and period report: the area-weighted share of suspect cells at the review and final flags, the number of review items, and the strongest scale. IMD's departure-from-normal bands may be shown beside it for weather context only. The suspect-data output must **not** reuse IMD's category names, because it measures data quality, not rainfall. Open: the sub-division boundary file is not in the repo and must be sourced from IMD.

## 7. Live input (daily scale only): the web app's AWS stations (IMERG was dropped)

**Decided 2026-11-18: the real-time demonstration uses the AWS (automatic weather station) feeds already configured in the web app. NASA IMERG, first chosen the same day, was DROPPED by the owner (too much data and time); its code, tests and requirement were removed.** What the configured feeds are, checked in the code and data on 2026-11-18:

- The configured source `NoaaISDDataSource` replays `data/noaa_aws_network.csv` in a loop: six stations with US radar-site IDs (KTLX, KOKX, KAMX, KATX, KFWS, KDMX), carrying temperature, pressure and humidity only. An earlier documentation agent found that the file was built by `scripts/build_noaa_network.py` from one Denver record copied to six station names with fixed offsets. So that feed is not live, not in India, and has no rainfall field.
- Nothing in `backend/app/sources` or the canonical telemetry schema has a precipitation field. Only the Locations feature's Open-Meteo adapter returns precipitation, and that is a model product, not a gauge.
- Real Indian stations with rainfall do exist in NOAA's ISD archive: of 369 Indian station files for 2022 that the project had downloaded, 349 carried some liquid-precipitation data, but only 11.7% of all records did, and the accumulation periods are mixed (24 hours most common, many records with an unspecified period). Daily totals would have to be assembled from the 24-hour reports. **ISD is not a live feed at present (checked 2026-11-18):** through NOAA's data query service, five stations in India (Safdarjung, Mumbai and two others), the US and the UK all have no record after 24 to 25 August 2025, and in NOAA's AWS bucket there is no 2026 folder and every 2025 yearly file was written on 29 August 2025. The owner chose ISD India stations on 2026-11-18, so as it stands it can only be REPLAYED: real station observations up to August 2025, streamed in time order and labelled "replay", never "live".

**ISD rainfall format, checked 2026-11-18 on the 2022 Indian files (369 stations):** the liquid-precipitation groups are AA1 to AA4 (period in hours, depth in tenths of mm with 9999 = missing, condition code, quality code). Of 31,908 groups with a 24-hour period, 17 have missing depth; 31,873 sit on observations stamped in the 03 UTC hour, so the daily total is end-stamped at 03 UTC, which matches IMD's 08:30 IST day (NOAA does not document end-of-period stamping; this is measured, not documented). Quality codes are '1' (30,559) and '2' (1,332); condition codes are '3' (29,031), '9' (1,592), '2' (1,268). 343 stations have at least one 03 UTC 24-hour total in 2022. Other periods (99, 9, 21, 18, 15, 12, 6, 3, 1 hours) are mixed in and are not usable as daily totals. Redistribution: non-US ISD data falls under WMO Resolution 40, so ISD data must not be committed to the repo or shown as raw values in a public demo. Details: docs/research/noaa-isd-rainfall-facts.md.

NOT BUILT, and needed for a real-time station demonstration: a rainfall field in the canonical schema and in ingestion; a live or near-live feed of station rainfall (for India, none is configured); an adapter that turns a station's reports into a 03 UTC daily total; a scorer that works on one station (its own history and climatology), because the RF25-trained spatial models need grid neighbours; and wiring to the dashboard. RF25 is itself partly built from these gauges, so its climatology at a station's cell is not independent of that station. The owner must choose the feed (section 10).

**Considered and not used.** NASA IMERG (dropped). The IMD merged GPM grid (not needed; kept only as code, see below). CHIRPS preliminary (its daily values are pentad totals spread with IMERG's shape). Open-Meteo is display only, or at most an interim feed labelled model-based.

**The IMD merged grid, code kept but unused.** The IMD/NCMRWF near-real-time daily GPM-merged 0.25 degree grid, `https://imdpune.gov.in/cmpg/Realtimedata/gpm/Rain_Download.html` (algorithm paper: https://link.springer.com/article/10.1007/s12040-025-02550-0). I opened the page: it offers a binary daily file picked by date with a sample control file and a map-grid file (241 x 281), and states no day definition, latency, period or usage terms. The research agent, from the paper, reports: IMERG Late corrected with about 2,600 IMD gauges, a 03 UTC day, about 1-day latency, running since October 2015, validated only for July 2014 against RF25. I have not read the paper myself.

Known issues of the IMD merged grid, to be handled before it is ever used:
- **Not independent of RF25.** It is tuned with IMD gauges, so agreement with RF25 is partly built in. Say so wherever a bridge result is shown.
- **Access terms and archive depth unconfirmed**, and whether scripted download is allowed. Ask IMD before automating.
- **Day alignment.** IMD's day is 08:30 IST to 08:30 IST (03 UTC to 03 UTC). Which date RF25 gives an 08:30 reading is undocumented, so measure it (lags -1, 0, +1 day against all-India and sub-division daily means) on 2016-2017 and freeze the result.
- **Overlap with validation years is short:** the product exists from October 2015, so only about 2016-2017 can be used for the bridge check. Never the test years 2018-2025. A pre-written acceptance rule is needed before looking (agreement metrics: rain/no-rain at 0.5 mm per day with false alarm ratio, equitable threat score, Peirce skill score, percentage RMSE, mean bias, by region and season).
- **Model shift step:** score the product with the RF25-trained daily models on 2016-2017 and compare the score distribution with RF25's. A large shift means the daily models are not valid on this product without recalibration.

## 8. Build order

1. Scorer interface; baselines (gamma-with-zero, leave-one-out residual); period-level benchmark with a recorded hash.
2. Candidates: pooled regressors and the masked-neighbour net (monthly, yearly); decadal change-point tests.
3. Selection harness and its protocol-log entry.
4. Cross-scale fusion and the coherent-extreme rule.
5. Score export, sub-division boundary source, regional aggregation (6b).
6. The live daily path from a rainfall-carrying station feed (section 7): schema field, ingestion, a 03 UTC daily total per station, a one-station scorer, dashboard wiring. No gridded product is bridged.
7. Only after the architecture is fixed: full training, budgets log, single test pass.

## 9. What the new code does and does not do (2026-11-18)

- `scale_scorers.py`: baselines `gamma_zero` and `loo_median`; candidates `loo_kriging` (ordinary kriging, exponential variogram per period, anomaly = log1p total minus log1p climatology, weights renormalised when a neighbour is missing, calibrated by a per-client spread), `gbm_neighbour` and `mlp_neighbour` (scikit-learn, not the Gamma-head network). The leave-one-out baseline uses the MEDIAN of the neighbours: a first version with an inverse-distance weighted mean smeared one bad cell into its neighbours (a test showed a neighbour's score rising by more than a third of the bad cell's rise). 
- `scale_select.py`: thresholds from clean threshold-year periods; recall on all validation years; false alarms reported out of sample (non-threshold years) and on all years; whole-year bootstrap intervals, none below 5 years. With the real 5 validation years and 2 threshold years only 3 years are out of sample, so no interval is given for false alarms.
- `crossscale.py`, `crossscale_run.py`: fixed max or noisy-OR (the sum of ratios) with the coherent-extreme discount, and a learned challenger (non-negative logistic weights fitted on the fusion-fit years' synthetic faults, outside the threshold years). `qc cross-scale` stores each scale's scores like any other component, fuses them, and tabulates daily-only against every combination, fixed and learned, on the held-out threshold years. `qc choose-architecture` applies the frozen rule and writes the choice once, with the references and weights frozen.
- `crossscale_test.py` (`qc cross-scale-test`): the single-use cross-scale test pass with its own lock. It needs the daily test pass finished, the architecture chosen and the budgets fixed; it applies the frozen fusion without refitting, and scores only the chosen architecture, the daily-only baseline and the untrained baselines, for the test and stress years. Tested on a generated world only.
- `regions_report.py` (`qc regions-report`): daily and monthly regional output by IMD sub-division and homogeneous region from stored scores (flagged shares, flagged cells, largest connected cluster, injected-fault share, driving scale). Test and stress years only after the daily test pass is finished. Tested on a generated world only.
- Clients (`clients.py`, `qc client-map --nest-imd`): the 8 clients are groups of whole IMD sub-divisions; see the decisions above.
- `regions.py` and `imd_regions.py`: IMD's own boundary file (36 sub-divisions, 4 regions from its `region_cod`) loads and was checked by hand on the RF25 land grid: all 10 known places fall in the expected sub-division by polygon, 9 of 10 by grid cell (Chennai's cell is sea in RF25, so it cannot be tested at cell level); 34 of the 36 sub-divisions have cells on the RF25 land grid (the Andaman & Nicobar and Lakshadweep islands have none) and 122 of 4,964 land cells are in no sub-division. No licence is stated by IMD, so no derived map is published.
- `bridge.py`: the acceptance rule is frozen (config `bridge:` block and `docs/qc-evaluation-protocol.md`): 0.5 mm/day pass/fail, 2.5 mm reported only, cell-level correlation decides, a model shift is a warning, the validation years 2013 to 2017 only (code refuses any other year; widened from 2016-2017 on 2026-11-18 before any run). `run_bridge` refuses unless `confirmed_by_owner` is true.
- `imd_merged.py`: three sample files (15 Jul 2016, 10 Jan 2017, 2 Sep 2016) fetched 2026-11-18 showed each is exactly 241 x 281 x 4 bytes, little-endian float32 (big-endian gives values near 1e38), with no undefined cells in these three. The ROW ORDER could not be established: the control file implies south-first, IMD's 0/1 map grid is north-first, and the three days gave conflicting rain-over-India hints. `read_grd` therefore requires the row order and `verify_orientation` must decide it against RF25 on the same dates on a machine that has RF25; units (assumed mm/day) and the day the value belongs to are unverified.
- `changepoint.py`: SNHT and Pettitt with simulated critical values; hits mean "network or sensor change, not distinguishable".

## 10. Open items

- Live path: choose the rainfall-carrying station feed (the configured web-app feeds have none; real Indian stations in NOAA ISD carry rainfall in only about 12 percent of records, mostly as 24-hour totals); then build the ingestion, the daily total, the one-station scorer and the dashboard wiring. Nothing of this is built.
- The IMD merged grid is optional: its row order needs `verify_orientation` against RF25, and its access terms are unconfirmed.
- The decadal deliverable (a power curve on injected steps and a descriptive break list on the real yearly series) has the tests (`changepoint.py`) but no command that runs it on real data.
- Score export (schema 1) for the web app is NOT BUILT.
- Whether LSTM and Mamba-style candidates are worth adding to the daily temporal slot (my suggestion: no).
- Nothing has run on real RF25: every result above is from generated data.
