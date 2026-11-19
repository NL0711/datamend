# DataMend: architecture (short)

The full architecture is in [shared-docs/DATAMEND_ARCHITECTURE.docx](shared-docs/DATAMEND_ARCHITECTURE.docx). This page is the one-screen version for people and agents working in the repo.

DataMend is a **rainfall time-series data validation platform** (Part A) with an **optional trained model system** (Part B). Rainfall is the only parameter.

## Part A: validation platform (backend/, frontend/)

```
upload or live feed
  -> input-contract checks (profile, units, timestamps; reject the file, flag the row)
  -> internal record: Reading or DailyTotal (raw values untouched)
  -> check catalogue for the profile (reading or daily), checks that cannot run are listed as "not run"
  -> per row: verdict (OK / SUSPECT / UNCERTAIN / NO_DATA), rule score, severity, evidence
  -> run (stored), report headline (measured numbers only), JSON and CSV export
  -> explanation on demand: rule-based baseline, or the external AI narrator via NARRATOR_URL
```

| Piece | Status |
|---|---|
| Live gauge feed (Weather Union), 03 UTC daily totals, one-station scorer, `/api/rainfall` | IMPLEMENTED (`backend/app/rainfall`) |
| Input contract, check catalogue merge, runs and reports, evidence and explainer, dashboard | PLANNED (slices in TODO.md) |
| Place lookup (RF25 cell, land, client region) and score-provider seam | PLANNED (replaces Locations) |
| AI narrator | NOT IMPLEMENTED here (external deliverable) |
| Temperature, pressure and humidity pipeline, Locations weather code | LEGACY, to be removed |

Rules that do not change: raw data is never overwritten; every assumed number is tagged `assumed`; synthetic results are labelled synthetic; nothing unbuilt is presented as built.

## Part B: model system (ml-service/qc)

Layers: RF25 data and splits, frozen synthetic benchmark, four daily components (rules, slow, spatial CNN, temporal GRU), fusion with false-alarm budgets, monthly and yearly scorers, cross-scale rule, single-use test pass, IMD regional report. Specs: `docs/qc-system-spec.md`, `docs/qc-multires-pipeline-spec.md`, `docs/qc-evaluation-protocol.md`.

## Decisions

The reasoning behind the platform design is recorded in `docs/wayfinder/rainfall-validation-platform` (map and ticket resolutions). Vocabulary is in `CONTEXT.md`.
