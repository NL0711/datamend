---
title: Measure row size and compression on Tiger with generated data
labels: [wayfinder:task]
status: closed
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

## Resolution (2026-11-20, measured)

Owner approved test tables in schema `dm_measure`; `scripts/measure_tiger_storage.py` generated the data, loaded it, measured and dropped the schema (checked: schema gone, no jobs left; the app tables in `public` were not touched). All data is **synthetic** (hourly 2023, 92 % zeros and wet hours of exponential mean 2 mm, both assumed). Service: PostgreSQL 18.6, TimescaleDB 2.32 (license `timescale`); the Tiger plan cannot be read from SQL, the ticket note says trial until 2026-12-19, not verified; database was 11.9 MB before. Timings come from one laptop with a median round trip of 217 ms, so they include network time.

| Measure | Result |
|---|---|
| 4,000,000 rows, uncompressed (53 weekly chunks) | 576,520,192 bytes = 144.1 bytes a row (table 77.2, index 67.0) |
| Same, after `compress_chunk` on all chunks (segment by source, station) | 19,996,672 bytes = 5.0 bytes a row, 28.8 times smaller; compressing took 30 s |
| 1,000,000 wet-hours-only rows, 7-day chunks | 148.4 to 46.8 bytes a row (3.2 times); about 13 rows per station and chunk is too few |
| Same data, 365-day chunks | 141.6 to 14.8 bytes a row (9.6 times) |
| 1,000,000 hourly rows, 365-day chunks | 143.5 to 2.0 bytes a row (73 times) |
| Run and result tables, 30 stations, 10,980 station-days | `validation_results` 409.6 bytes a row; all three tables 424.5 bytes per station-day; only 2 check hits (synthetic data rarely trips a check, so flagged data costs more); about 71 MB per run for 457 stations a year (derived); run took 67 s |
| COPY, 4 M rows | 742 s = 5,388 rows/s; on a 100,000-row sample 25,681 rows/s |
| Application path (`insert_observations`, 2,000 rows a statement), 100,000 rows | 47.8 s = 2,094 rows/s (about 32 min for 4 M, derived) |
| Read one station-year (8,760 rows) | server planning about 2 ms, execution about 2.7 ms; client 1.1 to 5.9 s, compressed and uncompressed alike (network, not separated) |
| `store.ensure_timescale`, once, on `dm_measure` | extension, hypertable, compression, compression_policy all succeeded, no warning, 4.8 s; created a 7-day policy job on a 12-hour schedule (removed for the measurement); the repeat call was not run |
| `ON CONFLICT DO NOTHING` into compressed chunks | works: 2,000 rows with changed values left everything unchanged (1.6 s), new rows in a compressed range inserted |

**Meaning for the 750 MB free plan.** One uncompressed state-year of 4 M hourly rows (576 MB) would nearly fill it alone, so a bulk load must be compressed right after loading, not left to the 7-day policy, which runs on a 12-hour schedule and would find the whole load uncompressed. Compressed, the raw hours are small (20 MB at 5 bytes a row, up to about 190 MB if sparse data stays at 47 bytes a row). Whether the free plan keeps compression was not checked. The larger risk is the run tables: about 71 MB per full run, and `pipeline` runs are never pruned, so ten re-runs would pass 700 MB; this feeds the compact-verdict question in t01. The 7-day chunk length compresses sparse data three times worse than 365-day chunks and should be revisited before real data (not changed here). Not measured: real CWC data (it lists non-zero hours only, so real counts may be far below 4 M), many users at once, the cost of a run with many flags.

## Earlier status note and approval request (kept for the record)

**Approval needed from the owner:** permission to create and then drop test tables in a separate schema of the Tiger service (it holds no real data yet), and to run `CREATE EXTENSION` and the compression policy there. Record the plan used (trial until 2026-12-19). Until then t01 stays open.
