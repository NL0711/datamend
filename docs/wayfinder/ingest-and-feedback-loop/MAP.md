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

- [How do bulk uploads and source pulls become jobs?](tickets/t05-ingest-jobs.md) (decided by building, 2026-11-20, branch `feature/ingest-pipeline`): accept a streamed upload (300 MB cap, hashed) and return a job id at once; the jobs table is the queue and the work runs in the web process in 2,000-row chunks; re-ingest is idempotent; a bad file fails the job, bad rows are counted and listed; a job cut off by a restart is marked failed and the file is uploaded again. No object store, worker service or rate limit. IST and omitted zero hours are assumed and written on every job.

- [How do AI proposals, reviewer decisions, corrections and labels relate?](tickets/t06-reviewer-workflow-and-proposals.md) (decided by building, 2026-11-20): proposals are generated, stored apart, with no effect until accepted; an accepted correction keeps the original beside it; accepting also writes a `confirmed_fault` review; labels come only from reviewer decisions (follow-up and unsure are not labels); a weighted random sample of unflagged days estimates missed faults; one reviewer, rule-based proposer only.

## Not yet specified

- Monitoring and alerting (flag rate per station, drift) beyond what the MLOps spec section 8 says.
- Scoring with a registered model on the server, and the RF25 grid mapping it needs (graduated to [t10](tickets/t10-server-scoring-and-shadow-run.md)); the shadow run (same ticket).
- The LLM proposer and explainer (the narrator team's service; would be a second `Proposer`), and what a model-derived flag adds to the narrator's evidence payload (needs the teammate's facts).
- Roles beyond one admin: several reviewers, accounts, per-reviewer agreement. The reviewer is a free-text name behind the shared admin token.
- PostgreSQL migrations and upload storage beyond the server disk (graduated to [t11](tickets/t11-migrations-and-upload-storage.md)); paid-plan cost model after the trial.
- Kaggle bring-your-own accounts: today one `KAGGLE_USERNAME` and `KAGGLE_KEY` in the server environment; whose account runs a notebook, and where the snapshot may go, is open (see t08 and t12).
- Lineage beyond the stage graph (job, run, snapshot, training, model). Row-level lineage exists only as the run view and has no row key from a verdict to its raw hours (see t01).
- Retraining the RF25 STNet from labels (not built; needs t10).
- Live sources beyond CWC and the existing feeds.
- Ordering and sizing of the build slices (graduates once the tickets below close).

## Out of scope

- Building anything while mapping.
- Variables other than rainfall; satellite or reanalysis grids as a primary source (a lead only).
- The narrator itself (teammate's work).
- Training a neural model on the Render server in v1.

## Open tickets

The pipeline is built (branch `feature/ingest-pipeline`; `TODO.md` lists what is built and NOT IMPLEMENTED). Each open ticket below needs an owner decision or approval, not more building.

- [Measure row size and compression on Tiger](tickets/t02-measure-row-size.md): unrun; needs the owner's OK to create and drop test tables in the Tiger service.
- [Storage schema](tickets/t01-storage-schema.md): built and decided in part; open for retention, the compact-verdict question and the t02 numbers. Has a `## Needs the owner` list.
- [Training hand-off and gate](tickets/t08-training-handoff-and-gate.md): built; open for the label minimums (20 faults, 100 clean), the 5 per 1,000 budget, where the threshold is fixed, Kaggle and the licence, and the gate design. Has a `## Needs the owner` list.
- [May CWC data from 2018 to 2025 be used?](tickets/t09-test-years-and-cwc-data.md): the locked test years block the only real CWC file by default.
- [Server scoring and the shadow run](tickets/t10-server-scoring-and-shadow-run.md): blocked on t08.
- [Migrations and upload storage](tickets/t11-migrations-and-upload-storage.md).
- [Ask NWIC about derived data](tickets/t12-ask-nwic-about-derived-data.md): owner task; the CWC licence for derived flags is unconfirmed.
