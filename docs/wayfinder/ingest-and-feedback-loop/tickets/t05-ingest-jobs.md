---
title: How do bulk uploads and source pulls become jobs?
labels: [wayfinder:grilling]
status: open
assignee:
parent: MAP
blocked_by: [t01-storage-schema]
---

## Question

Decide the ingest path for a burst of data: accept and return a job id, where the file lives (object store choice and cost), the Postgres jobs table as the queue, chunking by station and time, idempotency, size and rate limits, back-pressure, status shown in the dashboard, failure and retry, and where the worker runs given that Render's free web service sleeps (paid background worker or an on-demand process).
