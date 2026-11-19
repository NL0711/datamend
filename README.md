# DataMend

**A rainfall time-series data validation platform.** Submit a rainfall series (an uploaded file or a live rain-gauge feed); the platform runs layered checks on every reading, returns a verdict for each one with the evidence behind it, and produces a run report. Rainfall is the only parameter.

- **Explanations:** a rule-based baseline explains each flag from its evidence. An external AI narrator (MCP-based, built by the AI implementation team) can be connected behind the same interface, and the dashboard has an "Ask the AI" chat that talks to it. **The narrator itself is NOT IMPLEMENTED here**: with `NARRATOR_URL` unset the chat says "AI narrator not connected" and answers nothing.
- **Optional trained layer:** the model system in `ml-service/qc` scores rainfall on the IMD RF25 grid. Only the score-provider seam exists in the platform; **no trained score is connected**, and no trained model has run on real data.

**Honest status.** Built and tested (generated data, mocked transports): the input contract (CSV and JSON, reject the file or flag the row), the check catalogue (8 reading and 4 daily checks, each declaring what it needs, with explicit "not run"), runs and reports (measured numbers only, no composite grade), JSON and CSV exports, the `evidence-v1` contract, the baseline explainer, the live Weather Union feed scored by the same catalogue, a stateless place lookup, the NOAA ISD India replay and station network map, the bulk-data pipeline (CWC ingest, proposals, audit sample, snapshots, model registry, label-fusion retraining), a single-admin sign-in, and the dashboard. Everything is rules, one statistic, a neighbour check and a small label-fusion re-weighting of the checks: **not a trained deep model**. Thresholds and weights are design choices, uncalibrated. There are no real quality-control labels for India, so no accuracy figure is claimed for real data; the sample files in `data/samples` are **synthetic**. Not verified: the Docker image has not been built here, the PostgreSQL/Timescale path and the Kaggle trigger have not been run against a live service, and a 200,000-row upload has not been timed. Not built: PDF export, Parquet input, unit conversion, the IMD sub-division lookup, user accounts beyond the one admin, retraining the RF25 STNet, scoring with a trained model on the server, the shadow run, the LLM proposer. See [TODO.md](TODO.md) for the slices and [docs/wayfinder/rainfall-validation-platform/SPEC.md](docs/wayfinder/rainfall-validation-platform/SPEC.md) for the spec, including what is not claimed.

## What is in the repo

| Path | What |
|---|---|
| `backend/` | FastAPI backend. `app/validation` (input contract, check catalogue, runs, evidence, explainers), `app/rainfall` (live Weather Union feed, NOAA ISD replay), `app/pipeline` (bulk ingest, proposals, audit, snapshots, registry, retraining, lineage), `app/places` (stateless place lookup), `app/api` (routes, sign-in). |
| `frontend/` | React + Vite app: a home page, a sign-in page and the dashboard (Overview, Station network, Runs, Run view, Data explorer, Review queue, Data pipeline, Anomaly lab (synthetic faults), Locations, Live gauge feed, Settings). |
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

**Sign-in.** With `REQUIRE_LOGIN=true` (the default) every `/api` route except `/api/auth/login`, `/me` and `/logout` needs a signed-in session, so nothing is readable without signing in. There is one admin account, set by `ADMIN_EMAIL` and `ADMIN_PASSWORD`. **The defaults (`admin@admin.com` / `admin`) are for local use only: anyone who knows them can sign in, so set your own values on any public deployment.** An empty `ADMIN_PASSWORD` switches sign-in off. Sessions are kept in memory (12 hours) and end when the server restarts; failed attempts and wrong tokens are rate limited per client address (the TCP peer; `X-Forwarded-For` is not trusted, so behind a proxy run uvicorn with `--proxy-headers`); `/docs`, `/redoc` and `/openapi.json` also need the session (send `X-Admin-Token`), and `/` answers with the status only when signed out; there is no password reset. `ADMIN_TOKEN` (optional) is a second credential for scripts: send it as the `X-Admin-Token` header. Saved dashboard settings go to `data/runtime_settings.json` (git-ignored; it contains your key).

**Web app routes** (hash routes, so a static host needs no rewrite): home at `/`, sign-in at `/#/login`, dashboard at `/#/app` (asks you to sign in first). To connect the live Weather Union feed: sign in, open Settings, enter your Weather Union key and a city, then Save and Test connection (or set the key and city in `.env`).

For bulk data, sign in and open **Data pipeline**: upload a CWC hourly rainfall CSV (National Water Data Portal), press Check, review the proposed corrections, audit a random sample of days the checks called fine, freeze a training snapshot and register models trained offline (a promotion gate decides the champion). The small label-fusion model can be retrained on the server's CPU or as a private Kaggle notebook. **Train on Kaggle** can use your own free Kaggle account: enter your Kaggle username and API key in the Kaggle account panel (kept in the browser tab only, sent as `X-Kaggle-Username` and `X-Kaggle-Key` headers for each Kaggle request), tick the consent box, and the notebook is pushed to your account (private, CPU, no internet); without your own account the server's `KAGGLE_USERNAME` and `KAGGLE_KEY` are used if set. Limits: your key passes through the server's memory for the request and is never stored or logged; the snapshot (station-days and your labels) goes to a third party under your account; Kaggle's API cannot show your remaining quota or cancel a notebook; it is still untested against live Kaggle (the tests mock the command line). Scoring with a model on the server is not built; the CWC licence for storing derived flags is unconfirmed.

**Bulk data.** Open **Data pipeline**: upload a CWC hourly rainfall CSV (National Water Data Portal; an ingest job reads it into an immutable raw store), press Check (hours are rolled up to rain-day totals and run through the daily checks), review the proposed corrections, audit a random sample of days the checks called fine, freeze a training snapshot, retrain the label-fusion model (on the server CPU, or as a private Kaggle notebook if `KAGGLE_USERNAME` and `KAGGLE_KEY` are set and `pip install kaggle` was run), or register a model trained elsewhere; a promotion gate decides the champion, and a lineage graph shows job, run, snapshot, training and model. NOT IMPLEMENTED: retraining the RF25 STNet, scoring with a model on the server, the shadow run, the LLM proposer. The CWC licence for storing derived flags is unconfirmed; the Kaggle trigger is untested against live Kaggle.

**ISD replay and station network.** The Station network page draws the India map with the Weather Union gauges and IMD synoptic stations. To fill it without a key, press Load replay (admin). That fetches real NOAA ISD daily rainfall of Indian stations up to Aug 2025 (the 14 default stations, or those in `ISD_REPLAY_STATIONS`) and shows it labelled REPLAY, never as live. `ISD_REPLAY_ON_START=true` fetches it once at start-up. Non-US ISD data is subject to WMO Resolution 40: it is fetched at run time and never committed or redistributed.

**Database.** `DATABASE_URL` defaults to a local SQLite file ("demo storage, resets on restart" on a free host; download a run's JSON export to keep it). It also accepts the string a host hands out (`postgres://...?sslmode=require`), which is converted to `postgresql+asyncpg://`. Tiger Cloud (Timescale) is the intended persistent store. The tables are created at start-up; there are no schema migrations. The Timescale hypertable and compression step (`pipeline/store.py`) is **UNTESTED against a live service**.

Open `http://localhost:8000/docs`. Runs are under `/api/validation`, the replay under `/api/validation/replay`, the live feed under `/api/rainfall` (503 until a key and a city are set), the place lookup under `/api/places`, the pipeline under `/api/pipeline`, sign-in under `/api/auth`.

Frontend:

```powershell
cd frontend
npm install
npm run dev      # http://localhost:5199 (proxies /api to the backend on port 8000)
npm test         # unit tests of the dashboard helpers and API client
npm run build
```

Try it without any data of your own: sign in (`/#/login`), in the dashboard open Runs, choose `data/samples/synthetic_readings_with_faults.csv`, profile `reading`, accumulation mode `cumulative`, interval `15`, tick "synthetic". Or with Docker (`docker compose up --build`, then `http://localhost:5173`; not verified in this environment).

Tests (generated data and mocked transports; no network, no API quota, a throwaway database):

```powershell
python -m pytest tests -q
```

## Deploy

- **Frontend:** Vercel, branch `frontend`, root directory `frontend`. The dashboard calls relative `/api/...` paths; `frontend/vercel.json` rewrites them to the Render backend (`https://datamend-backend.onrender.com`), so no environment variable or CORS setting is needed. If the backend URL changes, change the one `destination` in that file. A free Render backend that has been asleep can take about a minute to answer the first request.
- **Backend:** Render, Docker (`Dockerfile.backend`, settings in `render.yaml`). The free plan has 512 MB RAM, no persistent disk (SQLite resets on restart) and sleeps after 15 minutes idle; for persistence point `DATABASE_URL` at Tiger Cloud or another PostgreSQL. **Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in the Render dashboard** (`render.yaml` does not set them, so the public defaults would apply). The browser reaches the backend through Vercel's rewrite (same origin), so `CORS_ORIGINS` only matters for direct calls. Measured, not on the Render image: the idle app uses about 79 MiB of working set on Windows with Python 3.11.

## Documents

- [docs/wayfinder/rainfall-validation-platform/SPEC.md](docs/wayfinder/rainfall-validation-platform/SPEC.md): the platform spec and the "Not claimed" list.
- [shared-docs/DATAMEND_ARCHITECTURE.docx](shared-docs/DATAMEND_ARCHITECTURE.docx): architecture of the platform and the model system (written before the build; the spec above is newer where they differ).
- [shared-docs/DATAMEND_AI_INTEGRATION_GUIDE.docx](shared-docs/DATAMEND_AI_INTEGRATION_GUIDE.docx) and [docs/contracts](docs/contracts): the contract for the AI narrator.
- [docs/RAINFALL_LIVE_FEED.md](docs/RAINFALL_LIVE_FEED.md): the live gauge feed.
- [docs/qc-system-spec.md](docs/qc-system-spec.md), [docs/qc-evaluation-protocol.md](docs/qc-evaluation-protocol.md): the model system.
