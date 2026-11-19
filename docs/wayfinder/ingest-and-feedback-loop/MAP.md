---
labels: [wayfinder:map]
title: Bulk ingest and reviewer-driven model feedback loop
---

# Bulk ingest and reviewer-driven model feedback loop (map)

## Destination

A locked **spec** plus ordered build slices (added to `TODO.md`) for the next DataMend stage: bulk rainfall station data comes in from open sources, is checked and cleaned with a reviewer and AI proposals, the reviewer's decisions become labels, a model trained offline on IMD rainfall (RF25) is retrained from those labels, gated and promoted, and its flags are explained to the reviewer. Nothing is built while mapping. Tomorrow's demo is the current build, deployed and verified (not this effort).

## Notes

- Extends `docs/mlops-feedback-loop-spec.md` (PROPOSED, not built): keep its update ladder, promotion gate, shadow rule, leakage rules and audit sampling. Change: the India reviewer is the owner, a real reviewer with AI help, not a simulated one. The UK MIDAS replay stays a separate demonstration and is never pooled with India.
- Standing rules from `AGENTS.md`: rainfall only, no fake functionality, label synthetic and derived data, raw data never overwritten, the narrator never changes a verdict, score or evidence, non-US ISD data is never committed (WMO Resolution 40).
- Vocabulary in `CONTEXT.md`; consult the `grilling` and `domain-modeling` skills for decision tickets.
- Infrastructure: Tiger Cloud (Timescale) Postgres on a Performance trial (ends 2026-12-19, $1,000 credit), Render backend (free web service sleeps), Vercel frontend. All sizing numbers so far are assumptions, not measurements.
- User preference: file changes only with the Edit/Write tools, never shell rewrites. Tracker: local markdown, tickets in `tickets/*.md`.

## Decisions so far

- [Destination and scope (chart-time decisions)](tickets/t00-destination-and-scope.md): spec as destination, current build is the demo; extend the MLOps spec with a real reviewer; training runs offline and the server holds the label store, registry, scoring and gate; rainfall station sources only, each with a recorded licence check; AI only proposes, reviewer decisions become labels; stations reach the RF25 model through derived cell-day aggregation.

- [What are the CWC hourly rainfall data terms and file shape?](tickets/t03-cwc-terms-and-shape.md): licence reads only "Other (Open)", no name; the portal copyright policy allows free reproduction with accurate use and prominent source credit; nothing covers storing or redistributing derived flags, so ask the portal in writing; 83 state-period CSVs with timestamp, station id and rainfall, but columns, units, time zone and station coordinates are not verified.

- [How do station points map onto RF25 cells for scoring?](tickets/t07-station-to-cell-mapping.md): no India station-to-cell aggregation exists in code (only a point-to-cell lookup; the UK path uses inverse-distance on a 0.1 degree grid); an RF25 cell is about 23 to 28 km; ISD stations cover 9.3% of land cells (one station per occupied cell mostly) and Weather Union only 1.8% in 30 city clusters; the neighbour-dependent components were never run on sparse fields; aggregation error is unquantified, and station-versus-own-cell comparisons are not independent.

- [What does one real CWC file look like?](tickets/t04-first-file-download.md): the Tripura 2021-2025 file has station, coordinates, `dd-mm-yyyy hh:mm` time (zone not stated) and hourly mm for 5 stations and 4,354 rows; only non-zero hours are present (smallest value 0.5 mm), so absence cannot be read as dry or missing; 59 values above 100 mm an hour (max 423) need a decision; coverage is patchy.

- Build v1 (2026-11-20, owner asked for the pipeline to be ready instead of stopping at a spec): the storage schema, ingest jobs, reviewer workflow (proposals, corrections, labels, audit sample) and the training hand-off and gate were decided by building them on branch `feature/ingest-pipeline`; see `TODO.md` for what is built and what is NOT IMPLEMENTED. The tickets for those four areas stay open as the written decision record to confirm, and the measurement ticket on Tiger is still unrun.

## Not yet specified

- Monitoring and alerting (flag rate per station, drift) beyond what the MLOps spec section 8 says.
- Roles beyond one admin (several reviewers, per-reviewer agreement).
- PostgreSQL migrations (tables are only created at start-up today, never altered).
- Paid-plan cost model and which object store holds uploads.
- What a model-derived flag adds to the narrator's evidence payload (needs the teammate's facts).
- Live sources beyond CWC and the existing feeds.
- Ordering and sizing of the build slices (graduates once the tickets below close).

## Out of scope

- Building anything while mapping.
- Variables other than rainfall; satellite or reanalysis grids as a primary source (a lead only).
- The narrator itself (teammate's work).
- Training a neural model on the Render server in v1.

## Open tickets

Frontier (unblocked): [Measure row size and compression on Tiger](tickets/t02-measure-row-size.md) (needs the owner's OK to create and drop test tables). Blocked on it: the storage schema, then ingest jobs and the reviewer workflow, then the training hand-off. Blocked: the others, see `blocked_by` in each ticket.
