---
labels: [wayfinder:map]
title: Rainfall time-series validation platform
---

# Rainfall time-series validation platform (map)

## Destination

A locked **spec** (written as `shared-docs/DATAMEND_ARCHITECTURE.docx` plus the build slices in `TODO.md`; the guide for the narrator team is `shared-docs/DATAMEND_AI_INTEGRATION_GUIDE.docx`) of DataMend reshaped into a rainfall time-series data validation platform: scope, architecture, vocabulary, the evidence contract for the teammate's MCP LLM narrator, and a list of build slices each sized for one session (including the removal of the legacy temperature/pressure/humidity app). Nothing is built while mapping.

## Notes

- Domain: precipitation QC. Vocabulary lives in `CONTEXT.md`; the live gauge feed is documented in `docs/RAINFALL_LIVE_FEED.md`; the offline ML line is `ml-service/qc` (see `docs/qc-system-spec.md`).
- Consult the `grilling` and `domain-modeling` skills for decision tickets; update `CONTEXT.md` when a term is resolved.
- Standing rules from `AGENTS.md`: no fake functionality; mark anything unbuilt NOT IMPLEMENTED; label synthetic results as synthetic; the rainfall core must not depend on other variables.
- User preference: file changes only with the Edit/Write tools, never shell rewrites.
- Rainfall only. The teammate owns AI explainability as an MCP LLM narrator; our side provides flags and a structured evidence payload, plus a rule-based baseline so the platform works without the narrator.
- Tracker: local markdown (no tracker was configured). Tickets are `tickets/*.md`; frontmatter holds `status`, `assignee`, `blocked_by`.

## Decisions so far

- [What does the dashboard look like for a validation platform?](tickets/t06-dashboard-shape.md): layout D, timeline over queue (full-width series chart and check lanes on top; live strip, filterable worklist and decision pane below, all linked); four rail items (Runs, Run view, Live gauge feed, trimmed Settings), nine current views dropped; server-side paging at 50 flagged rows, evidence loaded on open, chart downsampled server-side; the four prototype variants are a primary source for a throwaway branch.
- [How do we evaluate and demonstrate the validation claim?](tickets/t07-evaluation-and-demo.md): daily headline numbers on the RF25 synthetic benchmark (labelled synthetic), ISD replay local and unlabelled only; reading profile gets a conformance suite plus an unlabelled flag rate on the real Weather Union log, no recall or precision; metrics as in the protocol at shipped thresholds with UNCERTAIN as its own row and trained-provider results kept separate; performance measured on the target environment; demo = live feed plus a labelled synthetic upload; a "Not claimed" section in the spec.
- [Does the Locations feature stay, and is it trimmed to precipitation only?](tickets/t09-locations-trim.md): keep only a stateless place lookup (RF25 cell, land status, client region) plus the `ScoreProvider` seam in a new `backend/app/places`; drop the four Locations tables, the tab, Open-Meteo, normals and the T/P/RH QC; Open-Meteo is dropped because it is a model product, not an observation; IMD sub-division is optional and local-only (boundary file not committed, licence unstated); removal is a slice after the new views exist; Mumbai becomes a test fixture.
- [What is the evidence schema and the Explainer/MCP contract with the teammate?](tickets/t04-evidence-and-explainer-contract.md): each fired check carries evidence with a measured/assumed/derived tag on every number; one Explainer interface with a rule-based baseline and the teammate's narrator as the second implementation (NOT IMPLEMENTED until delivered); read-only REST plus a versioned `evidence-v1` JSON Schema is the contract and the teammate hosts MCP (the platform does not in v1); explanations stored separately, always marked generated, shown beside evidence; "Explain" calls a configurable `NARRATOR_URL`; GET-only evidence, one write, static bearer token, 64 KB cap; four facts to confirm with the teammate.
- [What do verdicts, runs and reports look like, and where are they stored?](tickets/t05-results-and-reports.md): a run records input hash, settings, version and the checks not run; per row the original row, verdict, rule score and fired checks with severity bands of the rule score; no composite grade in v1 (measured numbers only); JSON and CSV exports (PDF NOT IMPLEMENTED); new Postgres-ready tables, demo storage resets on the free tier, 50-run cap; one open live run per rain day; one run per upload with per-station sections; completeness needs a declared interval.
- [What is the input contract: files, streams, timestamps and station metadata?](tickets/t02-input-contract.md): user picks a `reading` or `daily` profile with fixed columns, mm only; accumulation mode must be declared in files; rain day labelled by its end date (live accumulator currently labels by start, to fix); timezone-aware ISO 8601 stored as UTC, live data marked received; file-level problems reject, row-level problems flag and never drop; CSV and JSON (Parquet NOT IMPLEMENTED), about 10 MB; neighbour check needs 3 stations within 10 km; one `Reading`/`DailyTotal` record for every source; gappy rolled-up totals marked incomplete.
- [Which validation checks does the platform run on a rainfall time series?](tickets/t01-validation-checks.md): one check catalogue with declared needs and explicit "not run"; `reading` and `daily` profiles; a lone gauge's heavy value is UNCERTAIN, not SUSPECT; trained models are an optional score provider (NOT IMPLEMENTED); rule score and calibrated flag never mixed; v1 list of 8 reading and 4 daily checks; `scipy` stays for the climatology check.
- [What legacy temperature/pressure/humidity code, docs and hardware go, and what stays?](tickets/t08-legacy-inventory.md): about 50 backend modules, 11 views and 322 of 351 tests are legacy-only; two tangles (haversine inside `consensus.py`, catalogue CSV in a legacy package) and `conftest.py` must be fixed first; Locations is itself T/P/RH; removal order recorded.
- [What does an MCP LLM narrator need from the platform, and how is it exposed?](tickets/t03-narrator-needs.md): the platform is the MCP server side; tools use JSON Schema with structured results; no schema or size limit is defined for explanation inputs; four facts (client revision, transport, token auth, payload limits) must come from the teammate.
- [Destination and scope (chart-time decisions)](tickets/t00-destination-and-scope.md): spec as destination; core job = validate, flag with reasons, report; verdicts as in the live scorer; teammate's MCP narrator behind an Explainer interface; legacy T/P/RH app removed; claim justified by synthetic-fault metrics plus a live demo.

## Not yet specified

- Ordering and sizing of the build slices (graduates once the tickets below are closed).
- Report formats beyond JSON and CSV (PDF?), and how the run report is graded.
- How the trained `ml-service/qc` components reach the live single-gauge scorer (they need grid neighbours).
- Persistence: SQLite on a free Render service resets on restart; where run results live for the demo.
- Auth and multi-user use (does a platform need accounts?).
- README, architecture and positioning rewrite text (follows the spec).

## Out of scope

- Building anything while mapping (the map ends in a spec).
- Temperature, pressure or humidity validation.
- Sensor-health trends, degradation prediction, value correction and alerting.
- The narrator itself (teammate's work) and the UK MIDAS reviewer-feedback loop (`docs/mlops-feedback-loop-spec.md`, a separate effort).

## Open tickets

None. Every ticket is closed and the way to the destination is clear: what remains is writing `SPEC.md` (scope, architecture, vocabulary, the evidence contract, the "Not claimed" section and the ordered build slices, including the legacy removal order from the inventory) from the decisions above. That is a writing step, not a decision. Others are blocked; see `blocked_by` in each ticket.
