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

Frontier (unblocked): [Measure row size and compression on Tiger](tickets/t02-measure-row-size.md), [Read the CWC data terms and shape](tickets/t03-cwc-terms-and-shape.md), [How do station points map onto RF25 cells?](tickets/t07-station-to-cell-mapping.md). Blocked: the others, see `blocked_by` in each ticket.
