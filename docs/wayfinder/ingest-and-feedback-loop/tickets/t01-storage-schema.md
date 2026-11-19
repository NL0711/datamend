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
