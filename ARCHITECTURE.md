# DataMend: architecture (short)

The full architecture is in [shared-docs/DATAMEND_ARCHITECTURE.docx](shared-docs/DATAMEND_ARCHITECTURE.docx) (written before the build); the spec in `docs/wayfinder/rainfall-validation-platform/SPEC.md` is newer where they differ. This page is the one-screen version for people and agents working in the repo.

DataMend is a **rainfall time-series data validation platform** (Part A) with an **optional trained model system** (Part B). Rainfall is the only parameter.

## Part A: validation platform (backend/, frontend/)

```
upload (CSV, JSON) or live Weather Union feed
  -> input contract (profile, units, timestamps; reject the file, flag the row)          backend/app/validation/ingest.py
  -> internal record: Reading or DailyTotal (original row untouched)                     validation/records.py
  -> check catalogue for the profile; checks that cannot run are listed as "not run"     validation/checks.py
  -> per row: verdict (OK / SUSPECT / UNCERTAIN / NO_DATA), rule score, severity, evidence
  -> run stored (validation_runs, _results, _check_hits), report headline (measured numbers only), JSON and CSV export   validation/runs.py
  -> evidence-v1 payload per fired check                                                 validation/evidence.py, docs/contracts
  -> explanation on demand, stored separately and marked generated                       validation/explain.py, narrate.py
       rule-based baseline | the external AI narrator via NARRATOR_URL (also the "Ask the AI" chat)
```

| Piece | Status |
|---|---|
| Input contract, `Reading` and `DailyTotal`, input-integrity flags | IMPLEMENTED and tested on generated data |
| Check catalogue: 8 reading and 4 daily checks plus duplicate-row; thresholds are design choices, uncalibrated | IMPLEMENTED, conformance-tested (pass or fail only, no recall or precision) |
| Runs, report, exports, 50-run cap, paged rows (50 per page), downsampled series, one-row evidence | IMPLEMENTED; demo storage, resets on restart |
| Live Weather Union feed (`backend/app/rainfall`), scored by the same catalogue as one open run per rain day | IMPLEMENTED; accumulation units and period UNCONFIRMED |
| `evidence-v1` schema, baseline explainer, explanations table, narrator client, chat endpoints | IMPLEMENTED against a mocked narrator |
| AI narrator | NOT IMPLEMENTED here (external deliverable); `docs/contracts/narrator-request-v1.md` is a proposal awaiting the AI team |
| Settings editable from the dashboard (Weather Union key, city, interval, mode; narrator URL and token): `/api/settings`, admin-token protected, secrets write-only | IMPLEMENTED against mocked transports; no real Weather Union call made |
| Place lookup (`backend/app/places`: RF25 cell, land, client region) | IMPLEMENTED; IMD sub-division NOT IMPLEMENTED |
| Score-provider seam for trained scores | seam only; NO trained score is connected |
| Admin review loop (`validation/review.py`): reviewer decisions on flagged rows, stored apart from the evidence, admin-token protected, summary says they are not ground truth | IMPLEMENTED |
| Overview, Data explorer, event-forensics context, Anomaly lab (synthetic faults), gauge catalogue | IMPLEMENTED |
| Dashboard (`frontend/src/validation`: Overview, Runs, Run view, Data explorer, Review queue, Anomaly lab, Locations, Live gauge feed, Settings) | IMPLEMENTED; type-checked and unit-tested, not looked at in a browser by the author |
| PDF export, Parquet input, unit conversion, MCP hosting, accounts, composite quality grade | NOT IMPLEMENTED |

The legacy temperature, pressure and humidity app and the Locations feature were removed (see git history).

Rules that do not change: raw data is never overwritten; every assumed number is tagged `assumed`; the rule score and a calibrated flag are never mixed; the narrator never changes a verdict, score or evidence; synthetic results are labelled synthetic; nothing unbuilt is presented as built.

## Part B: model system (ml-service/qc)

Layers: RF25 data and splits, frozen synthetic benchmark, daily components (rules, slow, spatial CNN, temporal GRU, and the STNet fault detector under architecture validation), fusion with false-alarm budgets, monthly and yearly scorers, cross-scale rule, single-use test pass, IMD regional report. Specs: `docs/qc-system-spec.md`, `docs/qc-multires-pipeline-spec.md`, `docs/qc-evaluation-protocol.md`. It imports nothing from `backend/`, and the platform imports nothing from it except one committed JSON asset (`ml-service/qc/assets/client_map.json`).

## Decisions

The reasoning behind the platform design is recorded in `docs/wayfinder/rainfall-validation-platform` (map, ticket resolutions and the spec). Vocabulary is in `CONTEXT.md`.
