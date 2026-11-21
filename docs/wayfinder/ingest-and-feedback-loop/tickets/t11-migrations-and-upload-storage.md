---
title: How are schema changes applied, and where do uploads live beyond the server disk?
labels: [wayfinder:grilling]
status: open
assignee:
parent: MAP
blocked_by: []
---

## Question

Two gaps the build left. Schema: tables are created by `create_all` at start-up (`backend/app/db/database.py::init_db`) and never altered, so the first column change on a database that already holds reviewer labels has no path. Decide a migration tool (for example Alembic), whether it must work on both SQLite and Tiger PostgreSQL, and what runs before the hypertable step so `migrate_data` is not needed on a large table. Uploads: a file is held on the server disk only while its job runs and is deleted afterwards (`backend/app/pipeline/jobs.py`); a restart on Render's free service fails the job and the owner uploads again. Decide whether that is enough, or whether files go to an object store (which one, what it costs after the trial ends 2026-12-19) or the job runs in a worker that survives a restart, and add rate limits and back-pressure if sources are pulled without a person present.
