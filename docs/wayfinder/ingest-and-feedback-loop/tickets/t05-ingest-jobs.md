---
title: How do bulk uploads and source pulls become jobs?
labels: [wayfinder:grilling]
status: closed
assignee: built on feature/ingest-pipeline (2026-11-20)
parent: MAP
blocked_by: [t01-storage-schema]
---

## Question

Decide the ingest path for a burst of data: accept and return a job id, where the file lives (object store choice and cost), the Postgres jobs table as the queue, chunking by station and time, idempotency, size and rate limits, back-pressure, status shown in the dashboard, failure and retry, and where the worker runs given that Render's free web service sleeps (paid background worker or an on-demand process).

## Resolution (2026-11-20, decided by building on `feature/ingest-pipeline`; the owner asked for the pipeline instead of a spec)

**Decided and built** (`backend/app/pipeline/jobs.py`, `cwc.py`, `backend/app/api/pipeline.py`, `frontend/src/validation/PipelineView.tsx`; tests in `tests/test_pipeline.py`):

- **Accept, then process:** `POST /api/pipeline/ingest` (admin session) streams the upload to disk in 1 MB blocks while hashing it (SHA-256), refuses anything over 300 MB with 413, creates a `pipeline_jobs` row and returns 202 with the job at once. `run_job` then runs as a FastAPI background task; `wait=true` runs it before returning (for small files and tests).
- **The jobs table is the queue, in one process.** No broker, no worker service, no object store. A job is `queued`, `running`, `done` or `failed` and records rows read, inserted, already stored (duplicate), bad, stations, the first 50 bad rows with their problem, and every assumption made about the source (`cwc.ASSUMPTIONS`: time zone, zero hours, units, licence).
- **Chunking:** by file order, 2,000 rows per flush, one commit per chunk, with `asyncio.sleep(0)` between chunks so other requests get in. Not by station or time.
- **Idempotency:** the raw store's primary key (ticket t01); a re-uploaded file stores nothing new and its rows show as "already stored". The file hash is kept but not used to refuse a repeat.
- **File-level versus row-level:** a missing required column raises `CwcFormatError` before the first row and fails the whole job; a row with no station, an unreadable time or a non-numeric value is counted, listed and skipped while the other rows go in.
- **Failure and retry:** `fail_interrupted_jobs` (called at start-up from `main.py`) marks any job still `queued` or `running` as failed with a message to upload again, because the saved file is deleted when processing ends or the process dies. Retry is the owner uploading the file again, which is safe. There is no automatic retry.
- **Status in the dashboard:** the Data pipeline page lists jobs and their counts; `GET /api/pipeline/jobs` and `/jobs/{id}`. Checking is a separate step (`POST /jobs/{id}/check`, only when the job is `done`).
- **Source adapter:** `jobs.SOURCES = {"cwc": cwc}`; a source is a module with `ASSUMPTIONS`, `read_rows` and `station_record`. The CWC adapter takes the columns measured in ticket t04. Time `dd-mm-yyyy hh:mm` is read as IST and stored as UTC.

**Rejected or not taken:** an object store (the file lives on the server's disk, `PIPELINE_UPLOAD_DIR` or the system temp folder, only while the job runs); a paid background worker or an on-demand process (the work runs inside the web process); a message queue; chunking by station and time; rate limits and back-pressure (only the size cap exists).

**Caveats:**

- **Render free web service:** a sleep or restart during a job kills it. The job is then marked failed on the next start, and the upload has to be repeated, because the file was only on that server's disk. This is acceptable for one owner uploading occasionally, not for unattended pulls.
- **Disk:** a 300 MB upload sits on the server disk and the free Render disk is ephemeral; not measured against Render's limits.
- **Assumed:** the time zone is IST (the source does not say); the zero hours are omitted in the source files, so a missing hour is neither dry nor missing; units are mm per hour as the column name says. All three are written on every job and are not confirmed with the portal.
- **Measured on SQLite only:** the real Tripura file and a 400,000-row generated file in about 67 s; nothing on Tiger.
- **Only one source:** the existing ISD replay and live feeds do not go through this path.

**Closed because** the question's alternatives were answered for v1 by choosing the simplest one that works for one owner. What a larger or unattended ingest needs is listed under "Not yet specified" in the MAP (upload storage beyond the server disk, a worker that survives restarts, rate limits).
