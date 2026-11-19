# DataMend

**A rainfall time-series data validation platform.** Submit a rainfall series (an uploaded file or a live rain-gauge feed); the platform runs layered checks on every reading, returns a verdict for each one with the evidence behind it, and produces a run report. Rainfall is the only parameter.

- **Explanations:** a rule-based baseline explains each flag from its evidence. An external AI narrator (MCP-based, built by the AI implementation team) can be connected behind the same interface, and the dashboard has an "Ask the AI" chat that talks to it. **The narrator itself is NOT IMPLEMENTED here**: with `NARRATOR_URL` unset the chat says "AI narrator not connected" and answers nothing.
- **Optional trained layer:** the model system in `ml-service/qc` scores rainfall on the IMD RF25 grid. Only the score-provider seam exists in the platform; **no trained score is connected**, and no trained model has run on real data.

**Honest status (2026-11-19).** Built and tested: the input contract (CSV and JSON, reject the file or flag the row), the check catalogue (8 reading and 4 daily checks, each declaring what it needs, with explicit "not run"), runs and reports (measured numbers only, no composite grade), JSON and CSV exports, the `evidence-v1` contract, the baseline explainer, the live Weather Union feed scored by the same catalogue, a stateless place lookup, and the dashboard. Everything is rules, one statistic and a neighbour check: **not a trained model**. Thresholds and weights are design choices, uncalibrated. There are no real quality-control labels for India, so no accuracy figure is claimed for real data; the sample files in `data/samples` are **synthetic**. Not verified: the dashboard has not been looked at in a browser by the author of this change, the Docker image has not been built here, nothing has been deployed, and a 200,000-row upload has not been timed. Not built: PDF export, Parquet input, unit conversion, the IMD sub-division lookup, accounts. See [TODO.md](TODO.md) for the slices and [docs/wayfinder/rainfall-validation-platform/SPEC.md](docs/wayfinder/rainfall-validation-platform/SPEC.md) for the spec, including what is not claimed.

## What is in the repo

| Path | What |
|---|---|
| `backend/` | FastAPI backend. `app/validation` (input contract, check catalogue, runs, evidence, explainers), `app/rainfall` (live Weather Union feed), `app/places` (stateless place lookup), `app/api` (routes). |
| `frontend/` | React + Vite dashboard: Overview, Runs, Run view, Data explorer, Review queue (the admin review loop), Anomaly lab (synthetic faults), Locations, Live gauge feed, Settings. |
| `ml-service/` | The optional model system (`ml-service/qc`) and its training code. See `ml-service/README.md`. Imports nothing from `backend/`. |
| `data/samples/` | Two small **synthetic** uploads with injected faults (made by `scripts/make_synthetic_sample.py`). |
| `docs/contracts/` | The `evidence-v1` JSON Schema with an example, and the proposed narrator request and response (awaiting the AI team's confirmation). |
| `shared-docs/` | Documents for the team (Word files). |
| `docs/` | Model specs (`qc-*.md`), the live-feed note, research, decision records (`docs/wayfinder`). |
| `CONTEXT.md` | The glossary of terms. |

## Run it

Backend (Python 3.10 or newer):

```powershell
pip install -r requirements.txt
copy .env.example .env     # optional: set WEATHER_UNION_API_KEY and WEATHER_UNION_CITY to enable the live feed
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

To connect the live Weather Union feed from the dashboard, add `ADMIN_TOKEN=<a long random string>` to `.env` (generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`), restart, open Settings, enter the token, your Weather Union key and a city, then Save and Test connection. Without `ADMIN_TOKEN` editing is off (you can still set the key and city in `.env`). Saved settings are kept in `data/runtime_settings.json` (git-ignored; it contains your key).

To fill the Station network map without a key, open it and press Load replay (needs `ADMIN_TOKEN`). That fetches real NOAA ISD daily rainfall of Indian stations up to Aug 2025 and shows it as a REPLAY, never as live. The data is not stored in the repository (WMO Resolution 40).

Open `http://localhost:8000/docs`. Runs are under `/api/validation`, the live feed under `/api/rainfall` (503 until a key and a city are set), the place lookup under `/api/places`. Storage is a local SQLite file: "demo storage, resets on restart"; download a run's JSON export to keep it.

Frontend:

```powershell
cd frontend
npm install
npm run dev      # http://localhost:5199 (proxies /api to the backend on port 8000)
npm test         # unit tests of the dashboard helpers and API client
npm run build
```

Try it without any data of your own: in the dashboard open Runs, choose `data/samples/synthetic_readings_with_faults.csv`, profile `reading`, accumulation mode `cumulative`, interval `15`, tick "synthetic". Or with Docker (`docker compose up --build`, then `http://localhost:5173`; not verified in this environment).

Tests (generated data and mocked transports; no network, no API quota, a throwaway database):

```powershell
python -m pytest tests -q
```

## Deploy

- **Frontend:** Vercel, branch `frontend`, root directory `frontend`. The dashboard calls relative `/api/...` paths; `frontend/vercel.json` rewrites them to the Render backend (`https://datamend-backend.onrender.com`), so no environment variable or CORS setting is needed. If the backend URL changes, change the one `destination` in that file. A free Render backend that has been asleep can take about a minute to answer the first request.
- **Backend:** Render, Docker (`Dockerfile.backend`). The free plan has 512 MB RAM, no persistent disk (SQLite resets on restart) and sleeps after 15 minutes idle. The browser reaches it through Vercel's rewrite (same origin), so `CORS_ORIGINS` only matters for direct calls. Measured, not on the Render image: the idle app uses about 79 MiB of working set on Windows with Python 3.11.

## Documents

- [docs/wayfinder/rainfall-validation-platform/SPEC.md](docs/wayfinder/rainfall-validation-platform/SPEC.md): the platform spec and the "Not claimed" list.
- [shared-docs/DATAMEND_ARCHITECTURE.docx](shared-docs/DATAMEND_ARCHITECTURE.docx): architecture of the platform and the model system (written before the build; the spec above is newer where they differ).
- [shared-docs/DATAMEND_AI_INTEGRATION_GUIDE.docx](shared-docs/DATAMEND_AI_INTEGRATION_GUIDE.docx) and [docs/contracts](docs/contracts): the contract for the AI narrator.
- [docs/RAINFALL_LIVE_FEED.md](docs/RAINFALL_LIVE_FEED.md): the live gauge feed.
- [docs/qc-system-spec.md](docs/qc-system-spec.md), [docs/qc-evaluation-protocol.md](docs/qc-evaluation-protocol.md): the model system.
