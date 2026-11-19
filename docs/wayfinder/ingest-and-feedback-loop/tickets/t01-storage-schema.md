---
title: What is the storage schema for raw observations, flags, corrections and labels?
labels: [wayfinder:grilling]
status: open
assignee:
parent: MAP
blocked_by: [t02-measure-row-size]
---

## Question

Today every input row stores its original JSON, a result row and check hits (about 1 to 2 KB a row, an estimate). A state-year of hourly data is about 4 million rows (assumption), so that does not fit. Decide: raw observations as an immutable compressed hypertable; flags and evidence stored only for flagged rows with a compact verdict for the rest; corrections, proposals, labels and model scores in their own tables; the unique key that makes re-ingest idempotent; retention; how runs reference raw data. Decide whether the existing run and result tables migrate or stay for uploads.

## Resolution (2026-11-20, decided by building on `feature/ingest-pipeline`; status stays open, see "Needs the owner")

**Decided and built** (`backend/app/pipeline/models.py`, `store.py`, `qc.py`; tests in `tests/test_pipeline.py`):

- **Raw store:** one table, `pipeline_observations`: `source`, `station_key`, `observed_at` (UTC), `value_mm`, `job_id`. The primary key is (`source`, `station_key`, `observed_at`) and contains the time column, so Timescale can make it a hypertable. Rows are written once and never updated; a correction is a row in `pipeline_corrections`.
- **Idempotent re-ingest:** `store.insert_observations` uses `ON CONFLICT DO NOTHING` (SQLite and PostgreSQL dialects), 2,000 rows per statement (asyncpg allows 32,767 bound parameters). The first value stored for an hour wins; a later file that disagrees is counted as "already stored" and not applied.
- **Stations:** `pipeline_stations` (key, source, name, state, district, latitude, longitude); the first sighting wins.
- **Separate tables for the loop:** `pipeline_jobs`, `pipeline_proposals`, `pipeline_corrections`, `pipeline_audit`, `pipeline_snapshots`, `pipeline_training_jobs`, `pipeline_models`. Run-linked tables point at `validation_runs.id` with `ON DELETE CASCADE`. Generic column types only; the tables are created by `create_all` at start-up (`db/database.py::init_db`), never altered.
- **Hypertable and compression:** `store.ensure_timescale` (PostgreSQL only, best effort, stops at the first failing step, never blocks start-up) creates the extension, calls `create_hypertable('pipeline_observations', 'observed_at', migrate_data => TRUE)`, turns on compression segmented by (`source`, `station_key`) and adds a compression policy at 7 days.
- **The existing run and result tables stay and are reused.** `qc.daily_totals` rolls the hours up to rain-day totals per station and `qc.run_qc` writes them as an ordinary run with `source = "pipeline"`, profile daily, so the run, evidence, review and explanation views apply unchanged. A verdict reaches its raw hours only through the total's `raw` JSON (hours reported, hourly peak) and the run's `settings.pipeline` block; there is no row-level key from a verdict to its hours.
- **Retention, partly:** `validation.runs.prune_runs` never deletes `pipeline` runs (they hold reviewer labels) and does not count them against the run cap. Nothing deletes raw observations either.

**Not taken:** a table per source (the key carries `source`); updating a stored value on re-ingest; migrating the existing run and result tables.

**Caveats:**

- **Not built:** "flags and evidence only for flagged rows, a compact verdict for the rest". The pipeline run goes through the shared `_store_rows`, so every station-day gets a full result row with its original-row JSON. That is one row per station and day, not per hour, but it has not been measured (ticket t02).
- **Untested:** the Timescale steps against a live Tiger service (tests run on SQLite only). Compression ratio, bytes per row and read time are unmeasured.
- **Measured on SQLite only** (TODO.md): the real Tripura file (4,354 rows) and a 400,000-row generated file in about 67 s. The generator for that file is not in the repository.
- **Assumed:** about 4 million rows a state-year (from the question); the CWC files list only non-zero hours, so real counts may be much lower.
- Because the tables are never altered, any later column change needs a migration approach (Not yet specified in the MAP).

## Needs the owner

1. Retention: for how long raw hours are kept, and whether the never-pruned pipeline runs and their labels grow without limit or get an archive rule.
2. Whether a full result row per station-day is acceptable, or the compact verdict must be built after t02 gives numbers.
3. Approval for the Tiger measurements (t02). This ticket closes when those numbers exist and the Timescale step has run once against a live service.
