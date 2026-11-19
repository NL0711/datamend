---
title: What do verdicts, runs and reports look like, and where are they stored?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []   # t01 and t02 closed 2026-11-19
---

## Question

Decide the result model: the record of one validation run (input, settings, versions, timing); per-reading verdict, severity and how the score is derived; the run report (counts by check, completeness, quality grade and exactly how it is computed, never arbitrary); export formats; tables and storage (SQLite now, Postgres-ready; what survives a free-tier restart); how batch runs and live-feed windows are stored the same way.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner (Q1-Q8, all as recommended). Vocabulary is in `CONTEXT.md` (Run, Rule score, Verdict).

1. **Run record.** Run id and time, profile, source (`upload` or `live`), a hash of the input, row and station counts, the settings used (check thresholds, accumulation mode, neighbour radius), platform version and git commit, duration, status (completed, or failed with the reason), and the full list of checks that did not run with the reason. Modelled on the traceability of `ml-service/qc/runs.py`.
2. **Per-row result.** The original row untouched, its `row_ref`, the verdict, the rule score, and the fired checks, each with its name, a one-line reason, an evidence reference and a severity. Severity is three bands of the rule score (high at 0.7 or above, medium from 0.3 up to 0.7, low below 0.3), a documented design choice, uncalibrated. No second score is invented.
3. **No composite quality grade in v1.** Without labels it would be arbitrary. The report headline is measured numbers: completeness, share of rows SUSPECT, share UNCERTAIN, counts per check, and the "not run" list. A grade is a possible later addition, only with a documented formula.
4. **Exports.** JSON (full run record, per-row results and evidence) and CSV (one row per reading, original columns untouched plus verdict, rule score, severity and fired checks). PDF is NOT IMPLEMENTED.
5. **Storage.** New SQLAlchemy tables `validation_runs`, `validation_results` and `validation_check_hits`, written to work on SQLite now and PostgreSQL later. On the Render free tier SQLite resets on restart, so the UI and API label storage as "demo storage, resets on restart"; the downloadable JSON is the durable copy. At most 50 runs are kept, oldest pruned. Paid persistence is outside this map.
6. **Live feed.** One open `live` run per rain day (03 UTC to 03 UTC); each poll appends its readings and verdicts; at the 03 UTC rollover the run closes and a new one opens. Closed live runs count toward the 50-run cap like uploads.
7. **Multi-station files.** One run per upload with a section per station (own completeness and counts); the neighbour check works across the stations in that file under the 3-stations-within-10-km rule.
8. **Completeness.** For readings, the upload declares `interval_minutes` (no default) and the live feed uses its poll interval; expected readings per station-day follow from that. For daily series, expected is one total per day from the first to the last day. A station with no declared interval shows completeness "not computed", never a guess.
9. **Legacy tables.** The legacy tables (`stations`, `observations`, `anomaly_events`, `sensor_health`, `model_runs`, `operator_feedback`) are replaced by these in the removal slices; the Locations tables depend on the separate Locations ticket.
