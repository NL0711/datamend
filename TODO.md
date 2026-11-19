# DATAMEND: TODO

Status as of 2026-11-19. The temperature/pressure/humidity phases that used to be listed here were removed with the legacy app; their history is in git. Architecture: `shared-docs/DATAMEND_ARCHITECTURE.docx`. Decisions: `docs/wayfinder/rainfall-validation-platform`.

# VALIDATION PLATFORM (backend/, frontend/)

Build slices, in order. Each fits one working session and leaves the app and its tests running.

- [x] Live rain-gauge feed (Weather Union): catalogue, client with a call budget, 03 UTC daily total, one-station scorer (rules + neighbour check, NOT a trained model), `/api/rainfall`, `docs/RAINFALL_LIVE_FEED.md`, `tests/test_rainfall_feed.py` (27 pass on a mocked transport; one real poll of 9 Mumbai stations worked, all dry so no rain value seen). UNCONFIRMED: units and period of `rain_accumulation`; raw log kept to settle it when rain falls
- [x] Documentation reduced and rewritten (README, ARCHITECTURE, shared-docs); decision map written
- [x] 1. Rainfall branch is already on `main` (`6bbe2fb`); the three test files now collect (missing `Any` import, `pydantic-settings` installed in the environment, stale version assertion); `tests/conftest.py` no longer trains models and pins a throwaway SQLite database. 401 tests collect; the full legacy suite was not run (it is scheduled for deletion)
- [x] 2. `haversine_distance_km` now lives in `backend/app/geo.py` (the legacy `spatial.consensus` re-exports it); the station catalogue CSV moved to `backend/app/rainfall/data/`; `tests/test_rainfall_isolation.py` fails if the rainfall modules import any legacy package
- [x] 3. `backend/app/validation/`: `Reading` and `DailyTotal` records, `parse_upload` (CSV and JSON, both profiles, file-level reject versus row-level flag, declared accumulation mode and zone, header aliases reported back), input-integrity flags (duplicate, out of order, gap, bad or negative or non-numeric values), Weather Union adapter; 38 conformance tests in `tests/test_validation_input.py` on generated data. NOT IMPLEMENTED: the ISD replay adapter, the HTTP upload endpoint (slice 5)
- [ ] 4. Merge the two single-gauge scorers (`backend/app/rainfall/scorer.py`, `ml-service/qc/station.py`) into one check catalogue; correct the rain-day label to the end date
- [ ] 5. Runs, results, report and JSON/CSV exports; new tables; 50-run cap
- [ ] 6. Evidence payload, the `evidence-v1` JSON Schema, baseline explainer, explanations table, `NARRATOR_URL` call
- [ ] 7. Dashboard: four-item rail (Runs, Run view, Live gauge feed, Settings), timeline over queue, server-side paging; plus an AI chat panel in the Run view (added 2026-11-19 by the owner): it sends the question and the selected row's evidence to `NARRATOR_URL`, shows replies badged AI-generated, and says "AI narrator not connected" when unset (NOT IMPLEMENTED until the teammate delivers; no canned answers)
- [ ] 8. Place lookup in a new package; then delete the Locations code, tables and tab
- [ ] 9. Delete the legacy backend top-down with its tests, then the legacy frontend views, scripts, data and the hardware folder
- [ ] 10. Trim configuration and Docker files; drop legacy dependencies (`torch`, `shap`, `pyod`, `paho-mqtt`, `statsmodels`, `scikit-learn`; `scipy` stays)
- [ ] Not built, outside this list: PDF export, Parquet input, unit conversion, MCP hosting in the platform, accounts, correction of values, alerting

Direction from the owner, 2026-11-19: treat STNet as the intended trained architecture and build toward its score-provider seam. No STNet result exists yet, so nothing may be presented as trained or measured until the run finishes (spec section 12).

Open facts to settle: the Weather Union accumulation mode (from the raw log, when it rains); the AI narrator team's MCP client revision and transport, token auth, payload limits and hosting.

---

# PRECIPITATION QC SYSTEM (`ml-service/qc/`, the optional trained layer)

Spec: `docs/qc-system-spec.md` section 14. Status as of 2026-11-17: gates 0-9 built and tested on generated worlds only.

- [x] Gate 0 setup, configs, profiles (timing run NOT RUN)
- [x] Gate 1 data contract, client map, splits, leakage audit
- [x] Gate 2 fault benchmark, protected and ambiguous extremes
- [x] Gate 3 untrained scores and metrics
- [x] Gate 4 spatial, temporal and plain GRU components
- [x] Gate 5 fusion and validation curves (budgets NOT CHOSEN)
- [x] Gate 6 federated variants
- [x] Gate 7 single-use test scoring (offline comparison and fusion on federated components built, tiny-run tests only)
- [x] Gate 8 UK MIDAS study (reader UNVERIFIED on real files)
- [x] Gate 9 paper tables, figures, claim check, methods outline (no real tables yet)
- [ ] On the training machine: timing run, three-seed training, choose and log budgets, test scoring, `python -m qc paper`
- [ ] Verify the UK reader on real MIDAS files; confirm the OPEN UK choices
- [ ] Verify the Kerala August 2018 case-study values before citing them
- ERA5 temperature, humidity and pressure work was removed from the project on 2026-11-18; the project now covers rainfall only.
- [x] Time-resolution data layer `qc/resolution.py` (monthly, seasonal, yearly periods, per-scale training statistics, period-level synthetic faults, decade means); 11 unit tests on generated arrays, none on real RF25
- [x] Per-scale code, unit-tested on generated data only: period benchmark, scorers (baselines and candidates), selection harness, change-point tests, cross-scale fusion, regional summary, bridge check (`qc/period_benchmark.py`, `scale_scorers.py`, `scale_select.py`, `changepoint.py`, `crossscale.py`, `regions.py`, `bridge.py`)
- [x] IMD boundary loader, known-place acceptance check (10 of 10 places by polygon, 9 of 10 by cell; one coastal cell is sea in RF25) and merged-grid reader (`qc/imd_regions.py`, `qc/imd_merged.py`, `scripts/fetch_imd_regions.py`); bridge acceptance rule frozen in the `bridge:` config block and `docs/qc-evaluation-protocol.md` (commit that file before the check is run)
- [x] Added 2026-11-18, unit-tested on generated data only: `loo_kriging` candidate; learned (non-negative logistic) fusion challenger; frozen architecture rule (`qc cross-scale`, `qc choose-architecture`); cross-scale test pass with its own lock (`qc cross-scale-test`); regional output by IMD sub-division and region (`qc regions-report`); `run_qc.py` phases scales, choose, regions, budgets, test
- [x] Clients rebuilt as groups of whole IMD sub-divisions before any run (`python -m qc client-map --nest-imd`, `qc/clients.py`, `qc/assets/client_subdivisions.json`); held-out clients stay 3 and 6
- [ ] Not done: any run on real RF25; score export through the score provider; scoring live gauges with the trained models (they need grid neighbours); the NOAA ISD station replay (ISD has no data after Aug 2025, so replay only); a command for the decadal power curve and break list on real data
