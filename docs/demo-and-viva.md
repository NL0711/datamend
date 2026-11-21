# DataMend: demo script, whole flow, and viva answers

For the student who built DataMend. Plain language. Every claim here comes from `TODO.md`, `AGENTS.md`, `README.md` or the code. Where a number was not measured, it is marked `assumed`. If you are unsure, say "that is not verified" instead of guessing. That is the rule of the project (`AGENTS.md` section 4), and examiners reward it.

One sentence to remember: **DataMend is a prototype. It checks weather-station data with rules, adds a pretrained model score that is not validated, shows the evidence, and an agent that only proposes while a human decides.**

---

# 1. THE DEMO (8 to 10 minutes)

## 1.1 Before you walk in (do this 30 minutes early)

Ports:

- Backend: `http://localhost:8000` (API docs at `/docs`, needs sign-in).
- Frontend with `npm run dev`: `http://localhost:5199` (it proxies `/api` and `/ws` to port 8000).
- Frontend with `docker compose up --build`: `http://localhost:5173`. The compose file runs backend and frontend only. It does NOT run the scorer. Docker was not verified in this environment (README says so).
- Scorer: its own service, started separately (below). Use port 8001 so it does not clash with the backend.

Launch, local (the safest, this is what was tested):

1. Backend, in the repo root: `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`
2. Frontend: `cd frontend`, `npm run dev`, open `http://localhost:5199`.
3. Sign-in: the local default test account from config is `admin@admin.com` / `admin`. Only for local use. Say so if asked.
4. `.env` (copied from `.env.example`) needs, for the full demo: `GEMINI_API_KEY` (agent), `SCORER_URL=http://127.0.0.1:8001` and `SCORER_SECRET=<same value as the scorer>` (Keras score). Never show `.env` on screen.

Start the scorer (needs the weights built once: `python fetch_weights.py`, then `python convert.py` in a Python 3.11 venv with TensorFlow, see `ml-service/scorer/README.md`; the weights are not in git):

- `cd ml-service/scorer`, then set `SCORER_SECRET` and run `uvicorn app:create_app --factory --port 8001`.
- Check: open `http://127.0.0.1:8001/health`. It should answer with the model id and revision.

Warm up the Keras score BEFORE the audience arrives (important):

- The model needs 288 readings per station and variable, at the stream's own cadence, before any score appears. The simulator default is one reading every 5 s, so 288 readings take 24 minutes (288 x 5 s, arithmetic).
- A model flag needs more: a per-station threshold needs `SCORER_MIN_CLEAN_SCORES` = 1000 clean scores first (`assumed` config value). Until then nothing is flagged by the model.
- To get there fast: Settings, "Input stream", set the simulator cadence lower (the allowed range is 0.05 to 60 s, default 5 s), for example 0.5 s, press "Save and restart stream". Then 288 readings take about 2.5 minutes and 1,000 more clean scores about 8 more minutes (arithmetic, not measured; try it once before the demo and reset the cadence to 5 s afterwards if you want a calm stream).
- Honest statement for the audience: "At this cadence the 288-step window covers minutes, not a day. The model was trained on 288-step windows of one synthetic series. I use it as is."

Also before you walk in:

- Upload the synthetic sample once (Section 1.3, step 9) so the Agent and Events have a run to read.
- Keep a screen recording or screenshots of a good run as a fallback (Section 1.5).
- Know that the Render deploy is NOT verified. Demo from your laptop.

## 1.2 What not to say or click (read this twice)

Do not claim:

- That the ESP32 source works on real hardware. No hardware exists; it is tested only with a fake MQTT transport and a virtual-packet endpoint.
- That the Keras model is accurate, validated, or evaluated. It has NOT been evaluated on this platform's data. Every score says "not validated".
- That the agent is reliable. About 7 live Gemini turns were made; one completed with a proposal, the others were stopped by the guards. There is no evaluation of the agent.
- That the Render deployment works. Not verified (backend memory with agent packages on Render's 512 MB is unmeasured; the scorer's memory on Render is unmeasured).
- That simulator data is real. It is synthetic. The dashboard shows no "simulated" badge by the owner's decision, so YOU must say it.
- That thresholds are calibrated. They are `assumed` design values.
- That any model is novel. See Section 3.

Do not click:

- Settings, then any real-key fields, while projecting (keys are write-only, but do not risk it).
- "Start simulator" on all stations at 0.05 s cadence unless you tried it (it stores many rows: about 100k rows a day at 5 s and 6 stations, so fast cadence grows quickly; there is no retention yet).
- Anything under Weather Union live unless you have a key and know the daily call budget (900/day counter).
- The Agent "Accept" button on a proposal you have not read.

## 1.3 The click-by-click script

Times are targets. Total about 9 minutes.

1. **Sign in (0:00 to 0:30).** Open `http://localhost:5199`, go to the sign-in page, enter the local account.
   - See: the dashboard shell. Header on top, left rail with numbered pages, footer status bar.
   - Say: "DataMend is a station-first dashboard. One station picker in the header, and every page reads the station I pick."

2. **The rail and keys (0:30 to 1:00).** Point at the rail: Overview, Live, Alerts, Events, Explorer, Review, Injector, Agent. These are keys 1 to 8. Press `2` to go to Live, `1` to go back. Press `s` for Settings.
   - Say: "Eight pages, keys 1 to 8. Import and Settings are in the header."

3. **Station picker and Overview (1:00 to 1:45).** Press `1`. Click the header station picker, search "Bengaluru" or a city, pick a gauge. Then show the globe or map.
   - See: pins for the 580 Weather Union gauges at catalogue positions. A station with no coordinates has no pin.
   - Say: "The 580 gauge catalogue is the only station list. A position is the catalogue's, never guessed."

4. **Settings, then Input stream (1:45 to 2:30).** Click Settings in the header (or `s`). Find the "Input stream" block.
   - See: active source (simulated, Open-Meteo, ESP32, Weather Union), station set, cadence. "Save and restart stream".
   - Say: "One block chooses the source and the station set. Changing it restarts the stream. Keys are write-only secrets."

5. **Live, start the simulator (2:30 to 3:30).** Press `2`. In the picker choose a simulator station (KTLX, KOKX, KAMX, KATX, KFWS or KDMX). The simulator starts by itself with the server (STREAM_AUTOSTART_SIMULATOR, default on), so there is no start button: the Live page shows "Simulator: running" and you only need to pick a station. Change the cadence in Settings > Input stream.
   - See: temperature, pressure and humidity updating, the source chip in the header turning to the live state.
   - Say: "This is the original simulator, so the data is synthetic. Every stored reading keeps a `source` field in the database and API. The dashboard has no badge, so I am telling you now: it is simulated."
   - If the Keras score area shows "not run: need 288 readings, have N", leave it. That is correct behaviour.

6. **Injector: SPIKE (3:30 to 4:30).** Press `7` (Injector). Pick the simulator station, anomaly SPIKE, parameter temperature, press inject.
   - See: the effect on Live within a tick or two, and a detection with a verdict and evidence.
   - Say: "I inject a synthetic spike. The reading is labelled with the fault kind as ground truth in the stored data. The check that fires shows its evidence."

7. **Injector: DRIFT then METEOROLOGICAL_EXTREME (4:30 to 5:45).**
   - DRIFT: inject a drift. Say honestly: "Drift is the hardest. In my synthetic evaluation, drift recall was 0.75 and a 3 C drift was not detected; drifts only reach UNCERTAIN." Do not promise it will flag.
   - METEOROLOGICAL_EXTREME: inject it. It moves pressure and temperature down and humidity up together, consistently. See it NOT classed as a fault by size alone.
   - Say: "A genuine extreme is physically consistent across variables, with a steady dew point. The platform never calls magnitude alone a fault. In the synthetic evaluation, this kind is never SUSPECT."

8. **Alerts and Events with evidence (5:45 to 7:00).** Press `3` (Alerts), then `4` (Events). Open one detection.
   - See: the verdict (OK / SUSPECT / UNCERTAIN / NO_DATA), a rule score, severity, and evidence for each check that fired, with each number tagged measured, assumed or derived. Where the Keras score exists, a provider block that says "not validated".
   - Say: "Every flag has evidence behind it. The rule score and the model score are never mixed. A model flag alone can only raise UNCERTAIN, never SUSPECT."
   - Note: Alerts lists unreviewed flagged rows of validation runs; there is no alert store or acknowledge button yet (NOT IMPLEMENTED). Stream detections appear in the anomaly list under the evidence pane.

9. **Import and run an upload (7:00 to 7:45, can be done earlier off-screen).** Click Import in the header. Use the file option: choose `data/samples/synthetic_readings_with_faults.csv`, profile `reading`, accumulation mode `cumulative`, interval `15`, tick synthetic, press Validate.
   - See: a run with a headline report, flagged rows, "not run" list.
   - Say: "Same check catalogue for uploads and for the stream. The sample file is synthetic."
   - Link import: the box accepts a Kaggle dataset or a public S3 link, but it reads reading or daily CSV/JSON, gzip files and NOAA ISD hourly files (as a file format only). The S3 link `s3://noaa-isd-pds/data/2024/421820-99999-2024.gz` was tried through the Import page and gave a completed run (94 rows, 1 station): it is safe to paste live. The owner's public Kaggle dataset holds gridded NetCDF, which imports nothing, so do not paste it.

10. **Explorer and Review (7:45 to 8:30).** Press `5` (Explorer): stored readings of the station in a table. Select station SYN-A (it appears in the picker after the upload). Press `6` (Review): the review queue. Open a flagged row, save a decision such as `false_alarm` or `confirmed_fault` (needs the admin sign-in).
    - Say: "A reviewer decision is stored apart from the evidence. It never changes a verdict. The summary says these are one person's opinions, not ground truth."

11. **Agent (8:30 to 9:30).** Press `8`. With SYN-A selected, ask "Which flagged row at this station matters most?" and press "Ask the agent".
    - See: a generated answer marked generated, a proposal (for example a reviewer label), and a "why" view with the event log: each step, the gate result and the real outcome. Proposals have Accept and Dismiss.
    - If the agent is not connected (no key) the page says "agent not connected" and the rule-based baseline explains. That is also a valid thing to show.
    - Say: "The agent is a prototype. It reads data only through read-only MCP tools, proposes, and a gate that does not trust the model re-checks everything before it acts. A human accepts. It never changes a verdict, score, evidence, raw data or a setting."
    - Honest line: "It is not reliable live. In my test most turns were stopped by the guards, which is the guards working, but it is not evaluated."
    - What the agent reads: stored validation runs (such as the uploaded file), not live stream readings. State this if asked. Stream and source state ("disconnected", "stale") are not read by the agent yet.

12. **Close (9:30 to 10:00).** Say: "Built and tested on generated data and mocked transports. The model score is not validated, the ESP32 is not tested on hardware, and the deploy is not verified. The design is the contribution: layered checks, explicit 'not run', evidence behind every flag, and a bounded agent."

## 1.4 What the audience should leave with

- Station-first dashboard, one global station.
- Checks fire with evidence. Genuine extremes are not called faults by size.
- The model score exists, is clearly labelled not validated.
- The agent proposes, the gate verifies, a human accepts.

## 1.5 Fallback plan

If the live Weather Union or Open-Meteo API fails or there is no network:

- Use the simulator (needs no network). It is the primary demo source anyway.
- Say: "Open-Meteo and Weather Union need network and, for Weather Union, a key and a daily call budget. I demo the simulator and show the settings for the others." A dropped source reports "disconnected" or "stale since ..." and the platform never invents readings to fill the gap. You can even show that as a feature.

If the scorer is not running or slow:

- The platform runs without it. The Events provider block says the scorer is not available, and checks still run. This is by design. The backend uses a 2 s timeout and backs off for 30 s after a failure.
- If the warm-up is not finished, show the "not run: need 288 readings, have N" message. That is honest: "The model needs a full window; it does not guess."
- If you pre-warmed and the score shows, show it and say "not validated". Do not say it detects anything.

If the agent fails (no key, rate limit, Gemini slow):

- The page says "agent not connected" or a guard stops the turn. Open the "why" view to show the event log and the gate or guard reason. Say: "The guards refuse invented checks, invented numbers and unsafe actions; this is that."
- Last resort: screenshots or a recording of an earlier successful turn, said clearly to be a recording.

If the whole app fails:

- Show `README.md` honest-status paragraph, the architecture figure `docs/architecture/datamend-architecture.svg`, the TODO measured numbers, and walk the flow in Section 2 verbally. Test results: run `python -m pytest tests/test_agent_graph.py -q` (offline, fake model and fake tools) if the machine works.

---

# 2. THE WHOLE FLOW (the story)

A reading is born. It is checked. It may get a model score. It becomes a verdict with evidence. It is stored. It is shown. An agent can read it and suggest something. A gate checks the suggestion. A human accepts or not.

```
SOURCE (one active at a time)
  simulator | Open-Meteo | Weather Union | ESP32 (MQTT, fake transport only)
        |   backend/app/stream/{simulator,open_meteo,wu_source,esp32}.py, source.py (TelemetrySource)
        v
STREAM MANAGER  backend/app/stream/manager.py, runtime.py
  owns the active source; reports running / stale / disconnected; never fabricates;
  fans out to bounded per-subscriber queues
        v
RAW STORE  stream_readings (source column, raw values never overwritten)
        v
CHECKS  backend/app/stream/scoring.py + validation/weather_checks.py (11 T/P/RH checks)
        + validation/checks.py (rainfall catalogue)
  range, rate of change, frozen, spike vs history, level shift, dew point vs temperature,
  dew point jump, dropout, reporting gap, ...; a check that cannot run says "not run"
        v
OPTIONAL KERAS SCORE  backend/app/scorer/{window,threshold,client,service}.py
        |  HTTP, 2 s timeout, X-Scorer-Secret
        v  ml-service/scorer (ONNX, onnxruntime only, no TensorFlow in the web process)
  288 readings -> trailing z-score -> reconstruction error -> per-station threshold at the
  false-alarm budget -> "provider" block, validated: false
        v
VERDICT + EVIDENCE  OK / SUSPECT / UNCERTAIN / NO_DATA, rule score, severity
  rule score and model score are never mixed; model flag alone = UNCERTAIN (model_flag)
        v
STORAGE  stream_events (detections), validation_runs/_results/_check_hits, reviews
  SQLite locally, PostgreSQL (Supabase pooler) by DATABASE_URL
        v
API + WEBSOCKET  /api/anomalies, /api/observations, /api/validation/*, /ws/live
  (WebSocket: session cookie, X-Admin-Token, or a 60 s single-use ticket)
        v
DASHBOARD  frontend/src/App.tsx: Overview, Live, Alerts, Events, Explorer, Review, Injector, Agent
  one selectedStationId (StationContext) shared by every page
        v
MCP LAYER  mcp-service/datamend_mcp (12 read-only tools), hosted at /api/mcp (backend/app/mcp_gateway.py)
        v
AGENT  backend/app/agent/graph.py (LangGraph):
  perceive (MCP tools only) -> reason (Gemini proposes) -> decide (policy.py allowlist)
  -> explain (explain.py, grounded) -> GATE (gate.py) -> act
  abstain / ask the user is a conditional edge; event log agent_events is append-only
        v
HUMAN  Agent page: Accept or Dismiss (POST /api/agent/proposals/{id}/accept, admin)
  the accept records a reviewer label or note on the platform's own review records
```

Story in plain words:

1. The owner chooses a source in Settings. The stream manager starts it. If the source drops, the manager says "disconnected" or "stale since ...". It never invents readings.
2. Each reading is stored raw with its `source`. The processor keeps a bounded history per station (96 readings) and runs the checks. A variable a station never reports (Weather Union has no pressure) is "not run", not filled.
3. If a scorer is configured, the backend keeps a 288-value window per station and variable at the native cadence. It scales the window with its own mean and standard deviation (`assumed`), sends it to the scorer service, and gets back one error number. A per-station threshold at a false-alarm budget (1 per 1,000, `assumed`) decides whether the model flags it. This needs 288 readings, then 1,000 clean scores.
4. The verdict comes from the rule checks, with evidence. The model score sits beside it in a provider block marked not validated.
5. The detection is stored, pushed over the WebSocket and shown on the pages.
6. The MCP server exposes runs, evidence and stations as read-only tools. The agent calls them with a read-only token.
7. The agent's language model (Gemini) proposes candidate actions. Deterministic policy rejects anything not on the allowlist. The explanation is built from recorded evidence and refused if it names a number, check or station the tools did not return.
8. The gate, independent of the model, re-checks policy, permissions and a fresh evidence hash right before acting. Only then the action is recorded as a proposal.
9. A human accepts or dismisses it. Nothing the agent does changes data, verdicts or settings.

---

# 3. VIVA QUESTIONS WITH MODEL ANSWERS

## A. Problem and novelty

**Q1. What problem does DataMend solve?**
Weather-station data has faults: spikes, drifts, frozen sensors, dropouts. Bad data hurts anyone using it. DataMend checks readings as they stream in or are uploaded, gives a verdict for each with the evidence, and says clearly what it could not check.

**Q2. Is your anomaly detection novel?**
No. Range checks, rate-of-change, frozen-value and persistence checks, autoencoders and ensembles are all well known. I do not claim them as new. The difference is the integration: layered validation with explicit "not run" reporting, separating genuine extremes from faults, evidence behind every flag, and a bounded agent with an independent gate. Any stronger claim would need a citation in `docs/research`, and I have not made one.

**Q3. What do you mean by "genuine extreme versus fault"?**
A heavy storm can make pressure drop and humidity rise, and that is real weather. A broken sensor gives a jump that no other variable supports. The checks never call a value a fault by size alone. Magnitude alone is UNCERTAIN. If temperature, pressure and humidity move together consistently with a steady dew point, it is a genuine-extreme candidate. In my synthetic evaluation METEOROLOGICAL_EXTREME was never SUSPECT.

**Q4. Why is "not run" reporting important?**
A silent skip looks like a pass. If pressure never arrives, as with Weather Union, a pressure check cannot say the data is fine. So it says "not run" with a reason. Verdicts exist only for parameters that have checks. For others the platform says there are none.

**Q5. What is the contribution of your project, in one sentence?**
A station-first platform where layered rule checks, a labelled-not-validated model score and a bounded agent all sit behind clear interfaces, with evidence for every flag and honest reporting of what is not built or not verified.

## B. Architecture choices

**Q6. Why station-first?**
The owner decided to return to the original app's design: a header with one global station picker and every page reading the selected station. One `selectedStationId` is shared by every page, and links between pages set it. It matches how an operator thinks: "what is wrong at this station?".

**Q7. Why layers (checks, then model, then verdict)?**
Each layer is explainable and replaceable. Deterministic checks give evidence a person can read. The model is optional and only gives a score. The verdict is built from the rule checks. If the scorer is down, the checks still run. That separation also keeps the rule score and the model score from being mixed.

**Q8. Why SQLite and PostgreSQL both?**
SQLite for local use and tests, because it needs no setup. PostgreSQL (the Supabase pooler) for deployment because Render's free plan has no persistent disk. `DATABASE_URL` chooses. The repo sets a small pool and no statement cache for the pooler. On the real Supabase, tables are created at start-up and migrations were never applied there (no `alembic_version`), which I know is a gap. Supabase's free-tier limits are not checked.

**Q9. Why a separate scorer service?**
TensorFlow is heavy, and the model needs `keras<3`. The web process never imports TensorFlow. The scorer is its own container using ONNX and onnxruntime only. The backend calls it over HTTP with a 2 s timeout. If it is absent the platform says "scorer not available" and carries on.

**Q10. Why Weather Union plus a simulator plus Open-Meteo?**
The 580 Weather Union gauges are the station catalogue and the live real source. Open-Meteo gives model estimates of T/P/RH at a point and needs no key. The simulator gives controllable synthetic data with seeded fault injection, which I need to test the checks. All sources implement one `TelemetrySource` interface so they are interchangeable.

**Q11. Why a WebSocket, and what if it drops?**
Readings arrive continuously, so push is better than polling. The WebSocket route only relays what the services produce. If a source drops, the manager reports "disconnected" or "stale since ...". The browser client reconnects with a growing delay (2.5 s up to 60 s). Nothing is faked to fill the gap.

## C. Data and checks

**Q12. Where do your check thresholds come from?**
They are design choices, `assumed`, and uncalibrated. There are no real quality-control labels for these stations, so I could not calibrate them. I tested them only on synthetic data. Real-station calibration is future work.

**Q13. Which checks do you run on temperature, pressure and humidity?**
Eleven: corrupt value, value out of range, extreme value, rate of change, frozen value, spike versus history, level shift, dew point above temperature, dew point jump, dropout and reporting gap. Rainfall uses the older catalogue (8 reading and 4 daily checks).

**Q14. What is the dew point check?**
The dew point is computed from temperature and humidity (Magnus-Tetens style). It can never be above the temperature. If it is, or if it jumps while the other variables do not explain it, then at least one sensor is probably wrong. It is a cross-variable consistency check.

**Q15. What happens when a variable is missing?**
If a station never reports it (such as Weather Union pressure), that check is "not run". If a variable reported before and then vanishes, that is a dropout. Missing values are never filled by the checks. For cleaning, the platform never invents values the data cannot support; for example, no interpolation on a rainfall dataset that omits zero values unless an explicit reason is recorded.

**Q16. What about raw data?**
Raw data is never overwritten. A corrected value, if any, is stored separately. Row-level problems keep the row with a flag and a reason; file-level problems reject the file.

**Q17. Why trust the live Weather Union answer over the CSV catalogue?**
For 4 of 13 sampled stations the CSV `device_type` disagreed with the live answer. So I trust the live response. The catalogue still supplies positions.

## D. The Keras model

**Q18. What model is it, and did you train it?**
It is `keras-io/timeseries-anomaly-detection`, a pretrained convolutional reconstruction autoencoder with 9,505 parameters. Input is a window of 288 steps of one variable. I did not train it and did not retrain it. It was trained on one synthetic series. I use it as is, as a score provider only.

**Q19. Why reconstruction error?**
An autoencoder learns to rebuild normal-looking windows. A window that looks unusual gets rebuilt badly, so a large error suggests something unusual. It needs no fault labels. But "unusual" is not "faulty": a storm is unusual too. That is why it never decides a verdict alone.

**Q20. Why a z-score?**
The training mean and standard deviation are not shipped with the model. So I scale each window with its own mean and standard deviation (a trailing z-score of that window). That is `assumed`. It is a stand-in, and I flag that the model's raw error says little without the platform's own scaling and evaluation. I saw a flat all-zero window score higher than a one-spike window.

**Q21. How is the threshold set?**
The training threshold is not shipped either. So for each station and variable, the threshold is the quantile of that station's own earlier clean errors at a false-alarm budget of 0.001, which is 1 per 1,000 (`assumed`). It needs 1,000 clean scores first (`assumed`). Until then nothing is flagged by the model.

**Q22. Why ONNX?**
Render's free plan has 512 MB RAM, which is too tight for TensorFlow. I converted the model once to ONNX and run it with onnxruntime. I checked it against TensorFlow on 32 seeded windows: the maximum output difference was 1.55e-6 (tolerance 1e-4). That is only those windows, not exhaustive. Locally the container used about 52 MiB and one window took about 8 ms. Render itself is not verified.

**Q23. Is the model validated?**
No. It has not been evaluated on this platform's data: no precision, recall or false-alarm figures. Every place the score appears says "not validated". The real scorer was exercised by hand, not end to end through the stream. A model flag alone can raise only an UNCERTAIN event.

**Q24. Why 288 readings, and why not resample?**
The model was trained on 288-step windows. I use the source's native cadence with no resampling, so no values are invented. Until the window is full the score says "not run: need 288 readings, have N". Windows also ignore timestamp gaps in the current build (a missing value empties the window, but time gaps are not modelled); that is a known limit.

## E. The agent

**Q25. What is your agent, and why LangGraph?**
It is a graph with stages: perceive, reason, decide, explain, gate, act. The owner chose LangGraph because the pipeline maps onto nodes, and "abstain or ask" is a conditional edge. The `act` node has exactly one incoming edge, from the gate, and a test checks that structurally. So the model cannot route around the gate.

**Q26. Why is the gate independent of the model?**
The model can be wrong or manipulated. The gate is plain code. Just before acting, it re-verifies the action against policy, permissions and a fresh evidence hash. If the evidence changed since it was read, it refuses. The real outcome (success, refusal, error) is recorded, never assumed.

**Q27. What can the agent do?**
Five things from an allowlist: propose a reviewer label, add a review note, acknowledge an alert (a flag on the alert only), ask for a re-run of the checks, ask the user a question. Anything touching a verdict, score, evidence, raw data, settings or a secret is not on the list. In the current build, "acknowledge" and "re-run" only record a proposal; there is no alert store or re-run yet.

**Q28. Why does the agent never decide?**
It is a language model. It can invent things. Decisions about data quality must rest on deterministic checks and a human. So it narrates and proposes; a human accepts. Its explanations are marked generated and are refused if they name a number, check or station that the tools did not return.

**Q29. How do you handle prompt injection?**
Tool output is treated as untrusted text. The agent reaches data only through read-only MCP tools with a read-only token, never admin credentials. Tool definitions are pinned with a manifest lock. Even if injected text convinced the model to propose something bad, the policy allowlist and the gate would reject it. This is by design; I have not run a formal prompt-injection test campaign, so I do not claim it is immune.

**Q30. How reliable is the agent?**
Not reliable live, and not evaluated. About 7 live Gemini turns were made: one completed with a recorded proposal, the others were correctly stopped by guards (an invented check name, no candidate passing policy, a malformed row id). Perception is a fixed plan (the newest run and its top-scored flagged row); the model proposes but does not call tools itself. Tests use a fake model and fake tools.

**Q31. What limits do you put on a turn?**
A maximum of 6 tool calls, a token budget of 12,000 (input estimated as characters/4, `assumed`), and a 90 s timeout. These are config defaults, `assumed`, not tuned. The agent runs with no provider too ("agent not connected"), and the rule-based baseline still explains.

**Q32. What is in the event log?**
`agent_events`, append-only, one structured row per step: task id, step, inputs by reference, model id, tool calls, decision, rejected alternatives, gate result, outcome, time. No secrets. The Agent page's "why" view and the tests read it.

## F. Evaluation and honesty

**Q33. What accuracy do you report?**
I do not report accuracy alone. On the synthetic evaluation (seeded simulator, 12 seeds): 0 false alarms in 86,400 clean readings at 60 s cadence, 0.008 false alarms per 1,000 at 5 s cadence, and 0 SUSPECT on clean data. Event recall was 1.0 for six of the eight fault kinds, DRIFT 0.75 (a 3 C drift is not detected), NOISE_BURST 0.84. Scoring took about 0.7 ms per reading, excluding the database write.

**Q34. Are those numbers real-world results?**
No. All of them are on synthetic data from my own simulator, with faults injected by my own injector. The checks were designed knowing those fault shapes, so the numbers are optimistic and say little about real stations. I have not evaluated on any real station.

**Q35. Why 0 false alarms is not proof?**
Because the clean data is the simulator's smooth diurnal pattern. Real data is messier. Zero false alarms in 86,400 synthetic readings shows the checks do not misfire on that generator; it does not prove they would on real weather.

**Q36. Did you measure latency?**
Scoring cost about 0.7 ms per reading (measured). Stream latency from source reading to screen has NOT been measured per source yet; the project rule says to report it as measured, and I have not done that.

**Q37. What would you do to evaluate the Keras model?**
Run it on this platform's own data: a clean replay plus seeded synthetic faults (labelled synthetic), and report precision, recall, F1, false alarms per 1,000, detection delay and latency, stating that the model was not fitted to the data. Until then it is "not validated".

## G. Testing

**Q38. How did you test?**
Unit tests for checks, scoring and services; schema and range tests for model output; integration tests from upload to checks to storage to API. Tests use generated data and mocked transports, never the real API quota. The ESP32 and WebSocket paths use a fake transport. The scorer uses a stub that returns known errors, plus one gated test that loads the real model when installed. TODO.md records 806 backend tests passing at the S4 slice, and 76 agent tests plus 85 frontend tests at S6 (counts recorded at those dates; run them again to quote today's).

**Q39. What is NOT tested?**
The ESP32 on a real device or broker, the Docker build of the full stack, Render, live S3, a private Kaggle dataset, the Agent page in a browser (not opened when recorded), and the agent beyond a handful of live turns. Frontend component tests are mostly absent; there are helper tests.

## H. Deployment

**Q40. How is it deployed?**
Frontend on Vercel, backend on Render with Docker, scorer planned as a second Render service. Vercel rewrites `/api/*` to the Render backend so the browser sees one origin. Render deployment is NOT verified by me for the latest build, and Render's free 512 MB memory with the agent packages is unmeasured (locally the import-only idle memory was about 179.5 MB with agent and adapter packages, on Windows).

**Q41. Why a WebSocket ticket?**
Vercel proxies `/api` but not WebSockets, so the browser must connect straight to the backend's own address, and it cannot send the session cookie to another site. So a signed-in browser calls `POST /api/stream/ticket` and gets a 60 s single-use ticket to open `/ws/live` (`VITE_WS_URL`). The ticket is not a session. It lives in memory, so it is valid on that instance only.

**Q42. What about secrets?**
Keys live in `.env` or the settings store, never committed. API keys and broker passwords are write-only in the UI. Event logs are redacted. The default admin account `admin@admin.com` / `admin` is for local use only; on any public deployment I must set my own values.

## I. Limitations and future work

**Q43. What are the main limitations?**
Thresholds are assumed and uncalibrated. No evaluation on real stations. The Keras model is not validated. The ESP32 source is untested on hardware. The agent is unreliable and unevaluated. No retention policy for stored readings. Alert acknowledge and re-run are only recorded proposals. Open-Meteo returns the same grid values for nearby stations.

**Q44. What would you do next?**
Evaluate the Keras score on this platform's data with the standard measures. Calibrate thresholds on labelled real data. Test the ESP32 with a real BME280. Measure stream latency per source. Verify the Render deployment and memory. Improve drift detection (recall 0.75 on synthetic). Add retention and an alert store.

**Q45. What is the old rainfall model system (Part B)?**
`ml-service/qc` is a research system for gridded rainfall (the STNet family), kept but not on the live path. Its results are on synthetic faults and validation years only. Do not present it as part of the live platform.

## J. Hard and trick questions, with safe answers

**Q46. "So is your system accurate?"**
I cannot say that. On my synthetic data it raised no false alarms in 86,400 clean readings and found most injected fault kinds. I have no real labels, so I make no accuracy claim for real stations.

**Q47. "Your autoencoder is just anomaly detection. Where is the novelty?"**
Agreed, it is not novel and I do not claim it is. The model is a pretrained generic one I use as is. What I built is the integration: layered checks with evidence and "not run" reporting, and a bounded agent behind a gate.

**Q48. "Does the ESP32 work?"**
It is built and tested against a fake MQTT transport and a virtual-packet endpoint. I do not have the hardware, so it is not verified on a real device or a real broker.

**Q49. "Why did you not retrain the model on weather data?"**
That was the owner's decision: use it as is. Retraining would also need labels and an evaluation I do not have. Because it is not retrained, I treat it as a score provider only and label it "not validated".

**Q50. "Can the agent change a verdict if it wants to?"**
No. Verdict, score, evidence, raw data and settings are not on the action allowlist, the gate re-checks before acting, and the agent reads only through read-only tools. A human accepts any proposal. I cannot claim it is perfectly secure; I have not done a formal security test.

**Q51. "Your simulator shows no badge. Is that deceptive?"**
It was an owner design decision for the dashboard. The `source` field stays in the database and API, and my docs and this presentation say what is simulated. I am telling you here: the demo data is synthetic.

**Q52. "Is it real time?"**
The stream is live for the source that is running: the WebSocket pushes readings as they are produced. But Open-Meteo values are model estimates polled at an interval (default 900 s, assumed), Weather Union polls at 900 s default, and the simulator is synthetic. I have not measured end-to-end latency, so I do not quote one.

**Q53. "What if the scorer is down in production?"**
The platform keeps running. The checks still run, and the page says "scorer not available". The backend times out after 2 s and backs off for 30 s. It never fabricates a score.

**Q54. "The agent did not work in the demo. Is it broken?"**
It is a prototype and not reliable live. When a guard stops a turn, that is the design: it refuses invented checks and unsafe actions rather than forcing a decision. The event log shows why.

**Q55. "Did you write the checks yourself or copy the old app?"**
The old app's checks were reimplemented as new code in the current catalogue; its Isolation Forest, Random Forest, GRU and SHAP stack was not copied back. The only model is the Keras one.

**Q56. "How do you know the ONNX model is the same as the original?"**
I compared them on 32 seeded windows: maximum output difference 1.55e-6, within a 1e-4 tolerance. That covers those windows only, not every input.
