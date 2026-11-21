# Station-first platform with Keras scoring and an own agent: decisions

Settled with the owner on 2026-11-21. This is a prototype. `AGENTS.md` carries the rules; this page records why.

## Direction
Return to the station-first layout of the original app (`ab3b0b3` of `github.com/NL0711/datamend`): header on top, one global station picker, every page reads the selected station. Cover rainfall and T/P/RH. Add three things: the generic Keras model `keras-io/timeseries-anomaly-detection` as a score provider, an MCP layer (exists), and the owner's own LLM-assisted agent.

## Decisions
| # | Decision | Reason |
|---|---|---|
| 1 | Agent provider: Gemini (setting, not hardcoded) | Client and guards already in `validation/gemini.py` |
| 2 | Stations: the 580 Weather Union gauges plus the original simulator's stations, in one picker. NOAA ISD removed | Owner request |
| 3 | Weather Union returns T, humidity, wind, rain (type 1) or rain only (type 2); never pressure; the CSV `device_type` is unreliable (4 of 13 sampled disagreed with the live answer). A missing field is "not run", not filled | Read live 2026-11-21 |
| 4 | Dashboard shows no badges for simulated data; the `source` field stays in the data; docs and evaluation say what was simulated | Owner request |
| 5 | Retire the AI-team narrator, `NARRATOR_URL`, `mcp-service/narrator/` and the Gemini explain/propose paths when the agent lands. Keep the MCP server and the rule-based explainer (fallback) | The own agent replaces them |
| 6 | Header holds Settings and Import. Rail: Overview, Live, Alerts, Events, Explorer, Review, Injector, Agent. Dropped: Sensor Health, Models, Anomalies | One physical sensor makes a health index meaningless; model score moves into Events |
| 7 | Agent actions: propose a reviewer label, add a note, acknowledge an alert, ask for a re-run of the checks, ask the user | Bounded, human accepts |
| 8 | Keras input: causal trailing z-score per station and variable; native cadence; "not run" until 288 readings | Training scaler is not shipped; no resampling, so no invented values |
| 9 | Keras flag: per-station, per-variable threshold from that station's clean history at a configured false-alarm budget | Training threshold is not shipped |
| 10 | Keras serving: a separate scorer service on a second Render free web service, with the model converted once to ONNX and run with `onnxruntime` (owner, 2026-11-21; Google Cloud and AWS were both ruled out by the owner; Render's free 512 MB is too tight for TensorFlow but probably fine for ONNX, NOT measured); the fallback, if the ONNX output does not match TensorFlow's, is the same scorer with TensorFlow on a Hugging Face Space; local Docker for development. The backend calls the scorer over HTTP behind the same interface either way | Needs `keras<3`; keeps TensorFlow out of the backend |

## Framework and hosting, for a reviewer
- **Agent framework: LangGraph** (changed from "no framework" at the owner's request, 2026-11-21). The seminar pipeline (perceive, reason, decide, explain, gate, act) maps onto graph nodes; abstain/clarify is a conditional edge; the gate is a node that every action must pass, so its independence from the model is visible in the code. Gemini via `langchain-google-genai`, MCP tools via `langchain-mcp-adapters` (not yet verified with the versions we install). ADK was the alternative: more Gemini- and Cloud Run-native, but its gate would be a callback. Deployment is the same for both: a library inside the Render backend. The policy checks, gate rules and `agent_events` log are our contribution on top of the framework.
- **Hosting:** frontend on Vercel, backend with the agent and MCP gateway on Render (one deploy, no extra hop), the Keras scorer as a second Render free web service running the ONNX model (a shared-secret header checked by the scorer; it sleeps when idle, so the first call after a pause may time out and the backend then says "scorer not available"; a periodic ping can keep it awake; free-tier memory and hours NOT checked). Fallback: a Hugging Face Space with TensorFlow. The owner has no ESP32 hardware (2026-11-21), so the ESP32 source is built against a fake MQTT transport and a virtual-packet endpoint and is not verified on a real device. Google Cloud and AWS were ruled out by the owner. Secrets go in the Render dashboards; the backend needs `DATABASE_URL` pointing at the owner's Supabase Postgres (use the pooler address; the repo already sets small pool and no statement cache for it) since Render's free plan has no persistent disk. Tiger Cloud is optional now: without TimescaleDB the feed history and pipeline store use plain tables. Supabase's free-tier pause and size limits are NOT checked. The agent calls the Gemini API with a key from Google AI Studio (not the Cloud console); that is a Google service too, so it is only usable if the owner's existing key works from the deployed host (not checked).

## Defaults set without the owner (all `assumed`, config values)
Tool calls per agent turn: 6. Keras false-alarm budget: 1 flag per 1,000 clean windows. Abstain when the evidence hash changed, the source is stale, or the relevant checks did not run.

## Known facts about the Keras model (card read through a sub-agent, weights not opened)
Conv1D reconstruction autoencoder, 288 steps x 1 feature, TensorFlow SavedModel needing `keras<3`, about 42 kB of weights, trained on one synthetic series (NAB `art_daily_small_noise`); training mean/std and threshold not shipped.
