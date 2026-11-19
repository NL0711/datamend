---
title: Measure row size and compression on Tiger with generated data
labels: [wayfinder:task]
status: open
assignee:
parent: MAP
blocked_by: []
---

## Question

Facts the schema decision waits on, measured not assumed: bytes per row of the current run and result tables, and of a candidate lean hypertable (station, time, value, flags) with and without compression, for a generated 4-million-row series. Also ingest speed with COPY and the time to read one station-year. Needs the owner's OK to create and then drop test tables in the Tiger service (it holds no real data yet); use a separate schema and clean up after. Record the numbers and the Tiger plan used (free versus the trial).

## Status note (2026-11-20, still open, nothing measured)

The build did not measure anything on Tiger. What the code now makes measurable, once the owner approves:

- **The candidate lean table exists:** `pipeline_observations` (`backend/app/pipeline/models.py`) is the lean hypertable the question described (station, time, value, plus `source` and `job_id`), and `store.ensure_timescale` applies hypertable, compression (segment by `source`, `station_key`) and a 7-day compression policy. So "with and without compression" is a matter of running that function on a generated series and comparing `hypertable_size` before and after compressing chunks.
- **The current run and result tables can be sized** by running `qc.run_qc` on the stored series (one result row and its check hits per station-day) and reading the table sizes.
- **Ingest speed:** `jobs.run_job` inserts in 2,000-row chunks through `ON CONFLICT DO NOTHING`; it is not COPY. Only a SQLite figure exists (400,000 generated rows in about 67 s, TODO.md). A COPY comparison would need new code.
- **Missing:** a generator for a 4-million-row series is not in the repository (the 400,000-row file was a throwaway script), and a "read one station-year" timing has no script.

**Approval needed from the owner:** permission to create and then drop test tables in a separate schema of the Tiger service (it holds no real data yet), and to run `CREATE EXTENSION` and the compression policy there. Record the plan used (trial until 2026-12-19). Until then t01 stays open.
