# DATAMEND: AGENT INSTRUCTIONS

## 1. Project identity

**DataMend** is a real-time weather-station data quality platform (Part A: `backend/`, `frontend/`) with an optional trained model system for gridded rainfall (Part B: `ml-service/qc`, kept as research, not on the live path). Owner decision, 2026-11-21: the platform covers rainfall AND temperature, pressure and humidity (T/P/RH), and it returns to the station-first design of the original app (commit `ab3b0b3` of `github.com/NL0711/datamend`): a header on top, a global station picker (automatic weather stations), and every page reading the one selected station.

The target architecture has five layers, each behind its own interface:

1. **Live telemetry**: a WebSocket stream from three interchangeable sources: a simulator, the Open-Meteo feed, and an ESP32 sensor (BME280 over MQTT). Every stored reading keeps its source (section 6). The owner has no ESP32 hardware (2026-11-21): that source is built and tested against a fake MQTT transport and a virtual-packet endpoint (as the original app had), and is NOT verified on a real device.
2. **Deterministic checks**: range, rate-of-change, frozen-value, persistence, cross-variable consistency (T/P/RH, dew point) and the existing rainfall catalogue, each with evidence and explicit "not run" reporting.
3. **Time-series anomaly model**: the pretrained generic Keras model `keras-io/timeseries-anomaly-detection`, plugged in through the score-provider seam, used as is (see section 7).
4. **MCP layer**: a read-only MCP server (`mcp-service/`, hosted at `/api/mcp`) exposing runs, evidence, stations and scores as tools.
5. **LLM agent**: the owner's own agent, built in this repo, that calls the MCP tools to explain and triage the selected station's data. It narrates and proposes; it never decides (section 7).

Verdicts exist for every parameter that has checks (rainfall, T, P, RH); a parameter without checks gets import, exploration, profiling and cleaning but NO verdicts, and the platform says so.

Read first: `README.md`, `ARCHITECTURE.md` (short), `CONTEXT.md` (vocabulary), `TODO.md` (the build slices), `shared-docs/DATAMEND_ARCHITECTURE.docx` (full; older than this section where they differ), `docs/wayfinder/rainfall-validation-platform/MAP.md` (why the rainfall design is what it is), and the original app's layout at `ab3b0b3` (git history of the owner's repository) before touching the shell.

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

Mark what is not built as **NOT IMPLEMENTED** or **PLANNED**. Label synthetic data and synthetic results as synthetic in docs, reports and evaluation (the dashboard is exempt, section 6). Tag every number that is not measured as `assumed` or `derived`. A prototype must say it is a prototype.

## 5. Research and novelty position

Do not claim that basic ML anomaly detection, spatial or temporal QC, persistence checks, buddy checks, autoencoders, GRU or LSTM models, ensembles or federated learning are novel. The differentiation is the integration: layered validation with explicit "not run" reporting, genuine-extreme versus fault discrimination that never calls magnitude alone a fault, evidence behind every flag, an explanation seam, and an honest evaluation. Any novelty claim needs a citation in `docs/research`.

## 6. Data and input rules

- The validation core handles rainfall and T/P/RH. The weather variable profile (what a dataset measures, whether it reports zero values, cadence, units, valid range) and the cleaning layer are parameter-agnostic; a parameter without checks gets import, exploration, profiling and cleaning but NO verdicts, and the platform says so. Cleaning must never invent values the data cannot support (for example no interpolation on a dataset that omits zero values). Optional metadata (station id, coordinates, quality flags) may be used but never required by the core checks.
- Every stored reading carries a `source` field (`simulated`, `open_meteo`, `esp32`, `upload`, `weather_union`). Owner decision, 2026-11-21: the dashboard does not add badges, prefixes or warning labels for simulated data; the original simulator (`backend/simulator` at `ab3b0b3`: diurnal generator, anomaly injector, scenarios) produces stations that sit in the same picker as the others. The `source` field stays in the database and the API, and README, reports and any evaluation say which data was simulated; no document may present simulated results as measured on real data.
- The old T/P/RH checks (WMO bounds, rate-of-change, frozen sensor, Magnus-Tetens dew-point consistency) may be reimplemented from the original app's design as new code in the check catalogue. Do not copy back its Isolation Forest, Random Forest, GRU or SHAP stack: the anomaly model is the Keras one in section 7.
- Raw data is never overwritten; any corrected value is stored separately.
- Validate inputs: missing values, duplicate and out-of-order timestamps, impossible values, frozen values, malformed rows. File-level problems reject the file; row-level problems keep the row with a flag and a reason.
- NOAA ISD (owner decisions, 2026-11-21): the ISD replay, the NOAA/IMD synoptic station list and any ISD station source stay removed. ISD hourly files may be imported again as a FILE FORMAT only (through the Import step from an upload, an Amazon S3 link or a Kaggle link), as a reader that produces ordinary rainfall readings: no station list, no replay, no ISD data in the repository.
- Secrets: the app reads API keys and tokens from `.env` or the settings store, and they are never committed or written into tracked files, logs or docs. Prototype posture (owner, 2026-11-21): the owner may paste keys in chat, and an agent may use one for a call the owner asked for.
- Prototype posture (owner, 2026-11-21): speed over ceremony. This is a prototype built for demonstration; test the area you changed, skip audits and long write-ups, and keep going rather than stopping for approval on routine choices.

## 7. Architecture rules

- Layered and explainable: deterministic checks, statistics, optional trained scores, then a verdict with evidence. Do not put logic inside API routes; use services.
- Two kinds of score are never mixed: the uncalibrated rule score and a calibrated flag (only with a score provider and a clean-period false-alarm budget).
- The narrator never changes a verdict, score or evidence; explanations are stored separately and always marked generated.
- SQLite for local use and tests; PostgreSQL (Supabase pooler) for a deployment, chosen by `DATABASE_URL`. Live-feed reading history has its own module and store (`rainfall/history.py`): local SQLite, or Tiger Cloud when `FEED_HISTORY_URL` is set.
- Stations: the station catalogue is the 580 Weather Union gauges (`backend/app/rainfall/data/weather_union_stations.csv`). It is the only station list behind the picker, the globe and the map; it is also an input-stream setting (below). Do not reintroduce the NOAA/IMD synoptic list. A station without coordinates gets no pin, and a station's position is the catalogue's, never guessed. Weather Union (read live, 2026-11-21, 13 of 580 stations): type 1 stations answer temperature, humidity, wind speed and direction, rain intensity and accumulation; type 2 stations answer rain only; some fields come back null (also `aqi_pm_10`, `aqi_pm_2_point_5` exist); there is NO pressure field. The catalogue's `device_type` disagreed with the live answer for 4 of 13 sampled stations, so trust the live response, not the CSV. A missing field (always pressure, and T/RH on type 2 stations) is "not run" for that check or is filled from Open-Meteo at the station's coordinates or from an attached ESP32, never invented.
- Input-stream config: one settings block (`runtime_settings`, with `.env` defaults, editable by the admin) chooses the active source (`simulated`, `open_meteo`, `esp32`, `weather_union`), and for each the station set it applies to (default: the Weather Union catalogue, or a chosen subset such as one city), cadence, and coordinates or topic where needed. Keys and broker credentials are write-only secrets. Changing the config restarts the stream and the UI shows the active source and station set.
- The temperature/pressure/humidity app removed in `TODO.md` slice 9 is superseded by the owner's decision of 2026-11-21: T/P/RH is back in scope, as new code on the current platform (services, run pipeline, evidence, review, explain seams), not a paste of the deleted modules. The removed modules stay in git history for reference only.
- Streaming: telemetry sources implement one `TelemetrySource` interface (start, stop, status, a labelled reading); a manager owns the active source; the WebSocket route only relays what the services produce. A dropped source reports its state ("disconnected", "stale since ...") and never fabricates readings to fill the gap. Streamed readings are stored raw and scored by the same check catalogue and score provider as uploads.
- The Keras model `keras-io/timeseries-anomaly-detection` is a generic, pretrained reconstruction autoencoder. Owner decision, 2026-11-21: use it as is, no retraining. Therefore it is a score provider only and never produces a verdict alone. Facts from its card (read 2026-11-21 through a sub-agent; the repo's weights were not opened): a convolutional reconstruction autoencoder, 288-step windows of ONE variable (so one score per station per variable), a TensorFlow SavedModel that needs `keras<3`; the training mean, standard deviation and the anomaly threshold are NOT shipped, and it was trained on one synthetic series. Decisions (owner, 2026-11-21): scale each window with a causal trailing z-score of that station's own history (`assumed`); windows use the source's native cadence with no resampling, and a score says "not run: need 288 readings, have N" until the window is full; the threshold is set per station and variable from that station's own recent clean history at a configured false-alarm budget (`assumed`, a config value), and a flag may be raised from it. The model weights are never retrained. The original SavedModel files are fetched from the model hub at setup (`ml-service/scorer/fetch_weights.py`) and not committed; the converted ONNX file (55 KB, parity-checked against TensorFlow) and its `SOURCE.json` (repo, revision, author credit) ARE committed (owner decision, 2026-11-21) so that a fresh clone or Render can build the scorer image without TensorFlow. Serving: a separate TensorFlow scorer service (`ml-service/`, its own container), called over HTTP by the backend with a timeout; the web process never imports TensorFlow, and the platform runs with the scorer absent ("scorer not available", checks still run).
- Own agent: the LLM agent is built and owned in this repository (`backend/app/agent/`, an agent loop over MCP tools). Its default model provider is Gemini (owner, 2026-11-21): the agent reuses the HTTP client and guards in `validation/gemini.py`. The AI-team narrator (`NARRATOR_URL`, `NarratorExplainer`, `mcp-service/narrator/`) and the separate Gemini "Explain (AI)" and "Propose with AI" paths are retired in the same slice that lands the agent (remove them then, not before; the rule-based baseline stays as the fallback); the MCP server stays. The model provider is a setting (`AGENT_PROVIDER`, `AGENT_MODEL`, key in `.env`), not hardcoded, and the agent runs with no provider ("agent not connected", the rule-based baseline still explains). Per-turn limits: a maximum number of tool calls, a token budget, a timeout.
- Agent pipeline (owner's design, 2026-11-21): input, perception, reasoning, decision making, explanation, action, in that order, with two cross-cutting parts: structured event logging and an independent execution gate. The logging and the gate are design proposals for the seminar, not requirements from the presentation; the agent is a PROTOTYPE of a sandboxed, bounded decision-support agent and says so in the UI and docs.
  - **Framework: LangGraph** (owner decision, 2026-11-21). The pipeline stages are graph nodes (`agent/graph.py`): perceive, reason, decide, explain, gate, act; "abstain or ask the user" is a conditional edge; the gate node is the only path to the act node, so the model cannot route around it. Gemini through `langchain-google-genai` and MCP tools through `langchain-mcp-adapters` (versions pinned when installed; verify both load before building on them). The graph state is the task state: objective, constraints, evidence references (run id, row ref, evidence hash, station id), candidate actions, status. Services hold the logic, routes only call the graph.
  - **Perception**: reads the selected station's runs, evidence, stream state and model score through MCP tools only; each tool result is stored in the task state as an evidence reference.
  - **Reasoning and candidates**: the language model interprets the request and PROPOSES candidate actions; it does not execute anything.
  - **Decision**: deterministic checks (`agent/policy.py`) reject any candidate that breaks a policy or a tool permission: allowed actions are an allowlist (propose a reviewer label, add a review note, acknowledge an alert (a flag on the alert only, never on a verdict), ask for a re-run of the checks, ask the user a question); anything that changes a verdict, score, evidence, raw data, settings or a secret is not on the list. Where the evidence is inadequate or stale (evidence hash changed, source disconnected, checks "not run"), the agent asks for clarification or abstains and says why; it never forces a decision.
  - **Explanation**: a short account built from the recorded evidence and the selection criteria, plus the rejected alternatives with their reasons where available; stored apart from the evidence, marked generated, and refused if it names a number, check or station the tools did not return.
  - **Execution gate** (`agent/gate.py`): independent of the model and of the decision step; it re-verifies the chosen action against policy, permissions and a fresh evidence hash immediately before calling any tool, and the real outcome (success, refusal, error) is appended to the record, never assumed.
  - **Event log** (`agent_events`, append-only): one structured row per step (task id, step, inputs by reference, model id and version, tool calls, decision, rejected alternatives, gate result, outcome, time). No secrets in it. It is what the UI's "why" view and the tests read.
  - Provider, dataset, deployment platform and exact thresholds (tool-call cap, abstain rule) are open choices, set in config and recorded when chosen. No real-world consequential action is needed to evaluate the concept: the actions above only touch the platform's own review records, a human accepts them, and tests use a fake model and fake tools.
- MCP and agent: the MCP server is read-only; the agent reaches platform data only through MCP tools with the read-only token, never through admin credentials. Tool output is untrusted text for the agent, tool definitions stay pinned, calls are rate limited and audited. Agent replies are stored apart from evidence, marked generated, and may not name a number, check or station that the tools did not return. The agent may propose a reviewer label; a human accepts it.
- The station picker is global state: one `selectedStationId` in the shell, shared by every page, and any link between pages (alert to event, globe to live view) sets it.

## 8. Testing

Testing is mandatory: unit tests (validation, checks, scoring, services), schema and range tests for model output, integration tests (upload to checks to storage to API), and edge cases (empty input, missing columns, duplicates, malformed files, extreme and frozen values). Tests use generated data or a mocked transport, never the real API quota (WebSocket and MQTT sources are tested with a fake transport; the Keras scorer with a stub that returns known errors, plus one gated test that loads the real model when it is installed). Do not run the full suite unless asked while the architecture is being reshaped; run the tests of the area you changed.

## 9. Evaluation

Do not report accuracy alone. Report precision, recall, F1, false-alarm rate (per 1,000 clean items), detection delay, latency and, for curves, precision-recall area. Treat false alarms as the main operational cost. Rules for the Part B model system are frozen in `docs/qc-evaluation-protocol.md`: budgets are fixed on validation data only; test years are scored once.

The generic Keras model is not retrained, but it is still evaluated before any claim about it: run it on this platform's own data (clean replay and seeded synthetic faults, labelled synthetic), report the same measures, and state that the model was not fitted to the data. Until that evaluation exists, every place the score appears says "not validated". Report stream latency (source reading to screen) as measured, per source.

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
