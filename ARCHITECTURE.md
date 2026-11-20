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
| Sign-in gate (`api/auth.py`): `REQUIRE_LOGIN` (default on) middleware makes every `/api` route except `/api/auth/login`, `/me`, `/logout` need a session; one admin (`ADMIN_EMAIL`, `ADMIN_PASSWORD`; defaults `admin@admin.com` / `admin` are local only, change them on any public deployment); sessions in memory, lost on restart; `ADMIN_TOKEN` accepted as `X-Admin-Token` for scripts; failed attempts rate limited; no other accounts | IMPLEMENTED and tested |
| Settings editable from the dashboard (Weather Union key, city, interval, mode; narrator URL and token): `/api/settings`, needs a session or `ADMIN_TOKEN`, secrets write-only | IMPLEMENTED against mocked transports; no real Weather Union call made |
| NOAA ISD India replay (`rainfall/isd_replay.py`, `api/replay.py`): 24-hour rainfall of Indian ISD stations to Aug 2025, fetched from NOAA's public bucket on request (or at start with `ISD_REPLAY_ON_START`; `ISD_REPLAY_STATIONS`), stored as one daily run with source `replay`, labelled REPLAY, never live. Non-US ISD data (WMO Resolution 40): never committed | IMPLEMENTED against mocked transport; not run against NOAA by tests |
| Database (`db/database.py`, `config.normalize_database_url`): SQLite by default; `DATABASE_URL` accepts a host's `postgres://` string. Tables are created at start-up, no migrations. Tiger Cloud (Timescale) is the intended persistent store | Timescale hypertable and compression step (`pipeline/store.py`) UNTESTED against a live service |
| Place lookup (`backend/app/places`: RF25 cell, land, client region) | IMPLEMENTED; IMD sub-division NOT IMPLEMENTED |
| Score-provider seam for trained scores | seam only; NO trained score is connected |
| Admin review loop (`validation/review.py`): reviewer decisions on flagged rows, stored apart from the evidence, admin-token protected, summary says they are not ground truth | IMPLEMENTED |
| Overview, Data explorer, event-forensics context, Anomaly lab (synthetic faults), gauge catalogue | IMPLEMENTED |
| Station network (`validation/stations.py`, `places/imd.py`, `frontend/src/validation/NetworkView.tsx`): a flat India map drawn from the RF25 land mask with the 580 Weather Union gauges and 541 Indian synoptic stations (NOAA's list, most operated by IMD; NOT IMD's own list, which is not public), each gauge coloured by its check, flag and audit state, with the nearest IMD station and a link into the audit queue for that station | IMPLEMENTED; tested on generated data, looked at in a browser with generated synthetic rows |
| Web app (`frontend/src`, hash routes): home `/`, sign-in `/#/login`, dashboard `/#/app` (sign-in first). Dashboard views: Overview, Station network, Runs, Run view, Data explorer, Review queue, Data pipeline, Anomaly lab, Locations (the place lookup), Live gauge feed, Settings | IMPLEMENTED; type-checked and unit-tested; the Station network view was looked at in a browser, the rest not by its author |
| PDF export, Parquet input, unit conversion, MCP hosting, user accounts beyond the one admin, composite quality grade | NOT IMPLEMENTED |

The legacy temperature, pressure and humidity app was removed (see git history).

### Data pipeline (`backend/app/pipeline`, `api/pipeline.py`, `/api/pipeline`; design in `docs/mlops-feedback-loop-spec.md`)

```
CWC hourly CSV -> ingest job (chunked, idempotent)   -> raw observations, immutable (pipeline_observations)      cwc.py, jobs.py, store.py
  -> roll-up to rain-day totals (03 UTC to 03 UTC) -> daily checks -> an ordinary validation run               qc.py
  -> proposals (rule-based; a suggestion only) -> reviewer accepts: correction stored beside the original, label  proposals.py
  -> audit sample (random draw of unflagged days, weighted; estimates missed faults)                           audit.py
  -> training snapshot (time-cut, hashed, locked test years 2018-2025 excluded)                                snapshot.py
  -> retraining: label-fusion weights over the checks, on the server CPU or a private Kaggle notebook           fusion.py, training.py, kaggle_trigger.py
  -> model registry; a challenger becomes champion only through the gate; rollback                             registry.py
  lineage graph: job -> run -> snapshot -> training -> model (read-only, built from the tables)                 lineage.py
```

| Piece | Status |
|---|---|
| CWC adapter (IST assumed, only non-zero hours present, licence unconfirmed), raw store, ingest jobs, roll-up, checks, proposals, corrections, audit sample, snapshots, registry and gate, lineage | IMPLEMENTED; tested on generated data and mocked transport |
| Label-fusion retraining on the server CPU | IMPLEMENTED; it only re-weights the checks from one reviewer's labels, it is not a deep model |
| Kaggle notebook retraining (`KAGGLE_USERNAME`, `KAGGLE_KEY`, `pip install kaggle`) | IMPLEMENTED against a mocked command line; UNTESTED against live Kaggle |
| Gate metrics from a model trained elsewhere | recorded as DECLARED; the platform cannot verify them |
| STNet long-memory test (stage 2 only, Kaggle notebook E) and the paired whole-year comparison (`python -m qc paired`) | BUILT and unit-tested on generated data; NOT RUN on RF25 |
| RF25 STNet retraining, scoring with a registered model on the server, shadow run, LLM proposer | NOT IMPLEMENTED |

### Deployment

Frontend on Vercel; `frontend/vercel.json` rewrites `/api/*` to the Render backend (`Dockerfile.backend`, `render.yaml`), so the browser sees one origin. The free Render plan has no persistent disk: use `DATABASE_URL` for Tiger Cloud or PostgreSQL, and set `ADMIN_EMAIL` and `ADMIN_PASSWORD` there (`render.yaml` does not).

Rules that do not change: raw data is never overwritten; every assumed number is tagged `assumed`; the rule score and a calibrated flag are never mixed; the narrator never changes a verdict, score or evidence; synthetic results are labelled synthetic; nothing unbuilt is presented as built.

## Part B: model system (ml-service/qc)

Layers: RF25 data and splits, frozen synthetic benchmark, daily components (rules, slow, spatial CNN, temporal GRU, and the STNet fault detector under architecture validation), fusion with false-alarm budgets, monthly and yearly scorers, cross-scale rule, single-use test pass, IMD regional report. Specs: `docs/qc-system-spec.md`, `docs/qc-multires-pipeline-spec.md`, `docs/qc-evaluation-protocol.md`. It imports nothing from `backend/`, and the platform imports nothing from it except one committed JSON asset (`ml-service/qc/assets/client_map.json`).

## Decisions

The reasoning behind the platform design is recorded in `docs/wayfinder/rainfall-validation-platform` (map, ticket resolutions and the spec). Vocabulary is in `CONTEXT.md`.
