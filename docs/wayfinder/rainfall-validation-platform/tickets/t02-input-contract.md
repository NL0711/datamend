---
title: What is the input contract: files, streams, timestamps and station metadata?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

What may be submitted for validation, and how is the input itself validated? Decide: accepted file formats (CSV, JSON, Parquet) and required columns for a rainfall series (timestamp, value, station id, optional coordinates); the unit and period of values (instantaneous intensity, running accumulation, daily total), including the unresolved Weather Union accumulation semantics; the day definition (03 UTC to 03 UTC); time-zone and ordering rules; checks on the file itself (duplicates, gaps, malformed rows, missing columns) and what is rejected versus flagged; how the live feed and batch upload share one internal record.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner (Q1-Q8, all as recommended). Vocabulary is in `CONTEXT.md` (Rain day, Time basis, Reading, Daily total, Resolution profile).

1. **Profiles and columns.** The user picks the profile per upload. `reading`: `timestamp`, `station_id`, and `accumulation` and/or `intensity`. `daily`: `day`, `station_id`, `mm`. Unit is mm (mm per hour for intensity); other units are rejected because unit conversion is NOT IMPLEMENTED.
2. **Accumulation semantics.** A file using `accumulation` must declare `cumulative` or `per_reading`; there is no default. The live Weather Union feed keeps its configured mode, labelled unconfirmed.
3. **Rain day label.** A rain day (03 UTC to 03 UTC) is labelled by the date it ENDS, as in the IMD convention and `ml-service/qc/station.py`. Known inconsistency until a build slice fixes it: `backend/app/rainfall/daily.py` labels by the start date.
4. **Timestamps.** ISO 8601 with a time zone, stored as UTC. A timestamp without a zone is rejected unless the upload declares one zone for the whole file. Live readings carry the time of receipt (`time_basis: received`, not `observed`); gap checks on received data are marked weaker in the evidence.
5. **Reject versus flag.** File-level problems (empty file, missing required columns, a timestamp column that does not parse at all, an unsupported unit) reject the whole upload with a clear message. Row-level problems (duplicate timestamps, out-of-order rows, gaps, non-numeric or negative values) never drop or silently fix a row: the row stays with an input-integrity verdict and a reason. Sorting happens only after reporting that the input was out of order. This replaces the legacy upload's habit of swallowing timestamp errors.
6. **Formats, limits, metadata.** CSV and JSON in v1; Parquet is NOT IMPLEMENTED. About 10 MB (about 200,000 rows). Several stations per file. `latitude` and `longitude` are optional; the neighbour check runs only with at least 3 stations with coordinates within 10 km in the same run, otherwise it is reported "not run". Header renaming uses a documented alias set and is reported back, never silent.
7. **One internal record.** `Reading` and `DailyTotal` are used by every source. Fields: `source` (`upload`, `weather_union`, `isd_replay`), `station_id`, optional `latitude` and `longitude`, `time_basis`, `accumulation_mode`, `units_confirmed`, `row_ref` (file row or live sequence number). Raw values are kept untouched beside any derived value. The live sources and the ISD parser are adapters that produce these records.
8. **Rolled-up daily totals with gaps** are still produced, marked `complete: false`. The impossible-value and climatology upper-tail checks run on them (an incomplete total is a lower bound, so a value already too high is still evidence); the repeated-value check runs only on complete days.
