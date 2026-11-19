---
title: Rainfall time-series validation platform (spec)
status: confirmed by the owner 2026-11-19; written from the closed tickets t00 to t09
---

# DataMend rainfall validation platform: spec

This spec is the destination of `MAP.md`. It restates the decisions in the tickets in one place and orders the build. It contains no new decisions. Where a ticket and this file disagree, the ticket wins and this file is wrong. Vocabulary is in `CONTEXT.md` ("Validation platform language"); it is not repeated here. Anything not built is marked **NOT IMPLEMENTED**; numbers that are design choices are uncalibrated.

## 1. Scope

**Job.** Take a rainfall time series (a file upload or the live gauge feed), run layered validation, and return per-reading flags with reasons plus a run-level report. (t00)

**In scope.** Rainfall only. CSV and JSON input. Two resolution profiles, `reading` and `daily`. Rule-based checks with explicit "not run". Structured evidence per flag. A rule-based baseline explanation. JSON and CSV exports. A four-item dashboard.

**Out of scope.** Temperature, pressure and humidity. Gauge-health trends, value correction, alerting. The narrator itself (teammate's work). The UK MIDAS feedback loop. Monthly and yearly validation (offline `ml-service` work).

**NOT IMPLEMENTED (outside the build list).** PDF export, Parquet input, unit conversion, MCP hosting in the platform, accounts, correction of values, alerting, the narrator, any trained score provider, a composite quality grade.

## 2. Architecture

Layered and explainable: deterministic checks, statistics, an optional trained score provider, then a verdict with evidence. Logic lives in services, not routes. SQLite now, written to move to PostgreSQL.

```
 upload (CSV/JSON) ─┐
 Weather Union feed ─┼─ adapters ─> Reading / DailyTotal ─> check catalogue ─> verdict + rule score + evidence
 ISD replay (local) ─┘                                        │                     │
                                                      "not run" list          Explainer (baseline | narrator)
                                                                                    │
                                              runs / results / hits / explanations (SQLAlchemy) ─> REST ─> dashboard, exports
```

**Components**

| Component | Decision | Ticket |
|---|---|---|
| Input adapters | Upload, `weather_union`, `isd_replay` all produce one `Reading` or `DailyTotal` record; raw values kept untouched beside derived ones | t02 |
| Check catalogue | One catalogue; each check declares its needs; unmet needs give "not run: reason" | t01 |
| Score provider | Optional seam for trained scores; NOT IMPLEMENTED until a real RF25 run exists | t01, t09 |
| Run store | `validation_runs`, `validation_results`, `validation_check_hits`, `explanations`; 50-run cap | t05, t04 |
| Explainer | One interface, two implementations (baseline, narrator) | t04 |
| Place lookup | Stateless `locate(lat, lon)` in `backend/app/places`: RF25 cell, land/sea, client region | t09 |
| API | Read-only evidence endpoints; one write (store an explanation) | t04 |
| Dashboard | Four rail items, layout D | t06 |

**Rules that bind every slice**
- Raw data is never overwritten. A corrected value, if ever added, is stored separately.
- Magnitude alone never makes a verdict SUSPECT, except above the physical ceiling or an internal inconsistency.
- The rule score and a calibrated flag are never mixed; UI and exports name which one a number is.
- The narrator never changes a verdict, score or evidence.
- No model product (for example Open-Meteo) is ever labelled an observation.

## 3. Input contract (t02)

- The user picks the profile per upload. `reading`: `timestamp`, `station_id`, and `accumulation` and/or `intensity`. `daily`: `day`, `station_id`, `mm`. Unit is mm (mm per hour for intensity); other units are rejected.
- A file with `accumulation` must declare `cumulative` or `per_reading`; no default. The live feed keeps its configured mode, labelled unconfirmed.
- Rain day is 03 UTC to 03 UTC, labelled by the date it **ends**. `backend/app/rainfall/daily.py` labels by start today and is fixed in slice 4.
- Timestamps are ISO 8601 with a zone, stored as UTC. No zone is rejected unless the upload declares one for the whole file. Live readings carry `time_basis: received`.
- **Reject the file:** empty, missing required columns, a timestamp column that does not parse at all, unsupported unit. **Flag the row, never drop or silently fix it:** duplicate timestamps, out-of-order rows, gaps, non-numeric or negative values. Sorting happens only after reporting the disorder.
- CSV and JSON, about 10 MB (about 200,000 rows), several stations per file. `latitude` and `longitude` optional. Header aliases are documented and reported back.
- `Reading` and `DailyTotal` fields: `source`, `station_id`, optional `latitude` and `longitude`, `time_basis`, `accumulation_mode`, `units_confirmed`, `row_ref`.
- A rolled-up daily total with gaps is produced and marked `complete: false`.

## 4. Check catalogue v1 (t01)

| Profile | Checks |
|---|---|
| reading | missing or all-null (NO_DATA); negative value; intensity above physical ceiling; counter jump; counter reset (informational); frozen non-zero intensity; intensity above zero with flat counter; neighbour check (isolated wet or dry) |
| daily | impossible value (negative or above 1,000 mm); repeated positive value on consecutive days (complete days only); own-climatology upper tail (gamma on the gauge's earlier wet days, "not run" until 30 wet days exist); neighbour check on daily totals |
| both | input-integrity checks from section 3 |

- Neighbour check needs at least 3 stations with coordinates within 10 km in the same run.
- A lone gauge's heavy value is **UNCERTAIN**, not SUSPECT. Confirmation of an extreme comes only from neighbours or a grid.
- Verdicts: `OK`, `SUSPECT`, `UNCERTAIN`, `NO_DATA`. Severity is three bands of the rule score: high at 0.7 or above, medium from 0.3 up to 0.7, low below 0.3 (design choice).
- Excluded from v1: the slow 30/90-day component and the trained spatial and temporal models.
- `scipy` stays; `scikit-learn`, `torch`, `shap`, `pyod`, `statsmodels`, `paho-mqtt` go.

## 5. Results and reports (t05)

- **Run record:** id, time, profile, source (`upload` or `live`), input hash, row and station counts, settings used, platform version and git commit, duration, status, full "not run" list with reasons.
- **Per row:** original row untouched, `row_ref`, verdict, rule score, fired checks (name, one-line reason, evidence reference, severity).
- **Report headline (measured only):** completeness, share SUSPECT, share UNCERTAIN, counts per check, the "not run" list. No composite grade.
- **Completeness:** needs a declared `interval_minutes` for readings (live uses its poll interval); daily expects one total per day first to last. Otherwise "not computed".
- **Multi-station files:** one run, one section per station.
- **Live feed:** one open `live` run per rain day; polls append; the run closes at 03 UTC; closed runs count toward the cap.
- **Exports:** JSON (full run, rows, evidence) and CSV (original columns plus verdict, rule score, severity, fired checks). PDF NOT IMPLEMENTED.
- **Storage label:** "demo storage, resets on restart". The downloaded JSON is the durable copy.

## 6. Evidence and Explainer contract (t04)

**Evidence per fired check:** `check`, `layer`, `profile`; `observed` (value, unit); `threshold` (value and why); `window` (readings or days with `row_ref`, capped at 24 readings or 14 days, with a link to the rest); `neighbours` (ids, distances, values) when used; `time_basis`; `reason` (one plain sentence). **Every number carries `basis`: `measured`, `assumed` or `derived`.** A `provider` block (per-fault-type scores, ensemble disagreement, `calibrated`, `label_tier: synthetic`) exists only when a score provider ran.

**Explainer:** `explain(flag, evidence) -> Explanation { text, contributions[], model_id, generated: true }`. The baseline fills a template from the evidence. The narrator is a second implementation. The platform computes no confidence for an explanation.

**Exposure:** read-only REST plus a versioned JSON Schema (`docs/contracts/evidence-v1.schema.json`, additive changes only within v1). The teammate hosts any MCP layer. "Explain" calls a configurable `NARRATOR_URL` with the evidence and stores the reply; if unset the UI says "AI narrator not connected" and shows the baseline.

**Storage:** `explanations` table linked to (run, `row_ref`, fired check): `text`, `generator` (`baseline-rules` or `mcp-narrator`), `model_id`, `created_at`, `generated: true`. The UI shows measured evidence beside any explanation and badges narrator text "AI-generated".

**Access (design choices to confirm with the teammate):** GET-only evidence, one write, static bearer token per environment, rate limited, 64 KB response cap with a `next` link.

**Open facts only the teammate can supply:** MCP client revision and transport, static bearer token acceptance, real payload limits, Render hosting behaviour. The request and response shape of `NARRATOR_URL` is the interface they must confirm.

## 7. Dashboard (t06)

Layout D, timeline over queue. Four rail items:

1. **Runs:** the list, "new run" upload, the "demo storage, resets on restart" label.
2. **Run view:** full-width series chart (intensity bars, accumulation line, verdict markers) and check lanes on top; below, the live strip, filterable worklist and decision pane. A chart marker, lane tick or queue item selects the same reading. Headline measured numbers, "not run" list, JSON and CSV export buttons (PDF NOT IMPLEMENTED).
3. **Live gauge feed.**
4. **Settings:** feed city and interval, accumulation mode, narrator URL.

At real size: 50 flagged rows per page from the server, sorted by rule score, filtered by verdict, check or station; evidence loaded by one GET when a row opens; the chart shows one station at a time and downsamples long series on the server.

Always on screen: the original row untouched, evidence with basis tags, the baseline explanation marked generated, the narrator slot marked NOT IMPLEMENTED until delivered, synthetic data labelled synthetic.

Dropped: Command Center, Live Telemetry, Alert Center, Sensor Health, Event Forensics, Data Explorer, Anomaly Lab, XAI Reasoner, Locations. The prototype variants stay on `prototype/validation-dashboard` as a source; only layout D is rebuilt (slice 7).

## 8. Evaluation and demo (t07)

**Daily profile, headline numbers (SYNTHETIC).** RF25 per-cell series with faults from the frozen generator (radius 0 for single-gauge checks, footprint faults for the neighbour check). Reported: recall per fault kind and overall at shipped thresholds (flag means SUSPECT; UNCERTAIN is its own row, outside both denominators); false alerts per 1,000 clean cell-days; event recall and detection delay for stuck, repeat and drift; protected-extreme false-flag rate; precision-recall area over the rule score with no calibration claim. Deterministic rules, so one run. Intervals by resampling whole years, none under 5 years. Provider results, if any, reported separately at frozen budgets (final 1.0, review 5.0), with the held-out fault-type split and per-kind recall on strong faults.

**ISD replay:** unlabelled demonstration of flag rates only, local, never committed (WMO Resolution 40).

**Reading profile:** a conformance suite (each check fires on a minimal generated case and stays silent on a clean one; pass or fail only) and an "unlabelled flag rate, not a false-alarm rate" on the real Weather Union raw log. No recall or precision.

**Performance:** time for a 200,000-row upload, live poll cycle time, peak memory, measured on the target environment (Docker, 512 MB cap) with the machine named. No target before measurement.

**Demo:** the live feed panel (honestly mostly dry) plus a labelled synthetic upload with injected faults through the same pipeline so every check fires. The ISD replay is not shown publicly.

## 9. Not claimed

- Accuracy on real labels (none exist for India).
- Any trained-model result until a real RF25 run exists.
- Calibration of the rule score.
- Precision or recall for the reading profile.
- The units and period of Weather Union's accumulation counter (UNCONFIRMED; to be settled from the raw log when it rains).
- The quality of Weather Union's data.
- That any single check, or the layered approach, is novel.
- "Real-time" means polling every 15 minutes with received-time stamps.

## 10. Build slices, in order

Each fits one session and leaves the app and its tests running. `TODO.md` is the live checklist and must match this list.

| # | Slice | Done when |
|---|---|---|
| 1 | Merge the rainfall branch (check whether `6bbe2fb` already covers it); fix the three test files that fail to collect; decouple `tests/conftest.py` from legacy model training | Tests collect and run without training legacy models |
| 2 | Move `haversine_distance_km` out of `spatial/consensus.py` and the station catalogue CSV out of `sources/` | Rainfall path imports nothing from legacy packages |
| 3 | Input contract, `Reading` and `DailyTotal`, input-integrity checks, conformance suite | Reject and flag rules of section 3 tested; one record for upload, live and ISD |
| 4 | Merge `backend/app/rainfall/scorer.py` and `ml-service/qc/station.py` into one catalogue with declared needs and "not run"; fix the rain-day label to the end date | Section 4 table implemented; conformance suite passes |
| 5 | Runs, results, report, JSON and CSV exports, new tables, 50-run cap, live run per rain day | Upload to checks to storage to API integration test passes |
| 6 | Evidence payload, `evidence-v1` schema, baseline explainer, `explanations` table, `NARRATOR_URL` call | Schema validates examples; narrator absent state shown |
| 7 | Dashboard layout D with four rail items and server-side paging | Page, evidence-on-open and downsampling work at 200,000 rows |
| 8 | `backend/app/places`, then delete Locations code, tables, tab | Lookup tests pass; no Locations references remain |
| 9 | Delete legacy backend top-down with its tests, then legacy frontend views, scripts, data, hardware folder | App and remaining tests run at each step |
| 10 | Trim config and Docker; drop legacy dependencies (`scipy` stays) | Image builds; memory measured on the target environment |

Evaluation numbers (section 8) are produced after slice 4 for the daily profile and after slice 5 for platform performance; they are reported only when measured.

## 11. Open facts

- Weather Union accumulation mode (from the raw log, when it rains).
- The narrator team's MCP client revision and transport, token auth, payload limits and hosting.
- Whether `psycopg2-binary` and `asyncpg` stay, which depends on the persistence decision; SQLite on a free Render tier resets on restart.
- Image size and the 512 MB figure on the real Render image, not verified.
