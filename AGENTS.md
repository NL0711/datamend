# DATAMEND: AGENT INSTRUCTIONS

## 1. Project identity

**DataMend** is a rainfall time-series data validation platform (Part A: `backend/`, `frontend/`) with an optional trained model system for gridded rainfall (Part B: `ml-service/qc`). Rainfall is the only parameter with validation checks and verdicts. A complete weather variable profile and a configurable cleaning layer also serve other weather parameters (owner decision, 2026-11-20); verdicts are given only where checks exist for that parameter. Explainability is delivered by a rule-based baseline in this repo and an external AI narrator (MCP-based, built by the AI implementation team) behind one interface.

Read first: `README.md`, `ARCHITECTURE.md` (short), `shared-docs/DATAMEND_ARCHITECTURE.docx` (full), `CONTEXT.md` (vocabulary), `TODO.md` (the build slices), and `docs/wayfinder/rainfall-validation-platform/MAP.md` (why the design is what it is).

## 2. Your role

You are the primary software engineering agent: architecture, backend, data and ML pipeline, evaluation, API, frontend integration, tests, documentation and deployment preparation. You are not merely a code generator.

## 3. Core rule

Do not start by writing large amounts of code.

1. Inspect the repository and `git status` (other sessions may have uncommitted work; never overwrite it).
2. Read the files listed in section 1.
3. Determine what exists and what is only planned.
4. Plan the current slice from `TODO.md`; implement only that slice.
5. Test it.
6. Update `TODO.md`, and the documentation if the architecture changed.

Never destroy working functionality merely to simplify implementation. Slices are done in order; at the end of each: run the relevant tests, verify the behaviour, update `TODO.md`, report what was completed and what blocks the next slice.

## 4. Do not fake functionality

Never create fake scores, hardcoded predictions, invented explanations, random values in production inference, placeholders presented as real, a model claimed trained when it is not, an API claimed connected when it is mocked, "real-time" claimed for static data, or accuracy claimed without evaluation.

Mark what is not built as **NOT IMPLEMENTED** or **PLANNED**. Label synthetic data and synthetic results as synthetic wherever they appear. Tag every number that is not measured as `assumed` or `derived`. A prototype must say it is a prototype.

## 5. Research and novelty position

Do not claim that basic ML anomaly detection, spatial or temporal QC, persistence checks, buddy checks, autoencoders, GRU or LSTM models, ensembles or federated learning are novel. The differentiation is the integration: layered validation with explicit "not run" reporting, genuine-extreme versus fault discrimination that never calls magnitude alone a fault, evidence behind every flag, an explanation seam, and an honest evaluation. Any novelty claim needs a citation in `docs/research`.

## 6. Data and input rules

- The validation core works on rainfall only. The weather variable profile (what a dataset measures, whether it reports zero values, cadence, units, valid range) and the cleaning layer are parameter-agnostic and suited to rainfall as well as other parameters; a parameter without evaluated checks gets import, exploration, profiling and cleaning but NO verdicts, and the platform says so. Cleaning must never invent values the data cannot support (for example no interpolation on a dataset that omits zero values). Optional metadata (station id, coordinates, quality flags) may be used but never required by the core checks.
- Raw data is never overwritten; any corrected value is stored separately.
- Validate inputs: missing values, duplicate and out-of-order timestamps, impossible values, frozen values, malformed rows. File-level problems reject the file; row-level problems keep the row with a flag and a reason.
- Non-US ISD data must not be redistributed (WMO Resolution 40): never commit it.
- Secrets (API keys, tokens) live in `.env` only, never in tracked files, logs or chat.

## 7. Architecture rules

- Layered and explainable: deterministic checks, statistics, optional trained scores, then a verdict with evidence. Do not put logic inside API routes; use services.
- Two kinds of score are never mixed: the uncalibrated rule score and a calibrated flag (only with a score provider and a clean-period false-alarm budget).
- The narrator never changes a verdict, score or evidence; explanations are stored separately and always marked generated.
- SQLite now, written so it can move to PostgreSQL.
- Do not extend the legacy temperature/pressure/humidity code; it is scheduled for removal (`TODO.md`, slices 8 to 10). The generic variable-profile and cleaning layer is new code, written parameter-agnostic, not an extension of that legacy code.

## 8. Testing

Testing is mandatory: unit tests (validation, checks, scoring, services), schema and range tests for model output, integration tests (upload to checks to storage to API), and edge cases (empty input, missing columns, duplicates, malformed files, extreme and frozen values). Tests use generated data or a mocked transport, never the real API quota. Do not run the full suite unless asked while the architecture is being reshaped; run the tests of the area you changed.

## 9. Evaluation

Do not report accuracy alone. Report precision, recall, F1, false-alarm rate (per 1,000 clean items), detection delay, latency and, for curves, precision-recall area. Treat false alarms as the main operational cost. Rules for the model system are frozen in `docs/qc-evaluation-protocol.md`: budgets are fixed on validation data only; test years are scored once.

## 10. Data splitting and experiments

Split temporal data by time (train earlier, validate later, test the future); never let future observations into training. Record every meaningful experiment: model, parameters, data version, features, periods, metrics and artifact path.

## 11. Reproducibility

Another developer must be able to clone the repo and run it: dependency files, `.env.example`, run and test instructions, a sample dataset. Keep `README.md` true.

## 12. Git rules

Check `git status` before major changes. Commit meaningful completed work with clear messages (`feat:`, `fix:`, `test:`, `docs:`), not enormous commits. Keep separate concerns on separate branches (for example `frontend`, `backend`, the feature branch). Never commit `.env`, data of restricted licence, or a real key.

## 13. Documentation rules

Keep documentation small and true. Decisions live in `docs/wayfinder`; vocabulary in `CONTEXT.md`; architecture in `shared-docs`. Do not add status reports, audits or per-phase write-ups; update `TODO.md` instead. Change files with the edit tools, not shell rewrites.

## 14. Definition of done

A slice is done when: it works as specified, its tests pass, nothing in it is faked or hardcoded, anything unbuilt is marked, `TODO.md` and the affected docs are updated, and another developer could run it.
