# DataMend

**A rainfall time-series data validation platform.** Submit a rainfall series (an uploaded file or a live rain-gauge feed); the platform runs layered checks on every reading, returns a verdict for each one with the evidence behind it, and produces a run report. Rainfall is the only parameter.

- **Explanations:** a rule-based baseline explains each flag from its evidence. An external AI narrator (MCP-based, built by the AI implementation team) can be connected behind the same interface. It is optional.
- **Optional trained layer:** the model system in `ml-service/qc` scores rainfall on the IMD RF25 grid and can attach its scores through a score-provider seam.

**Honest status (2026-11-19).** The live gauge feed is built and tested; the rest of the platform (input contract, check catalogue, runs, reports, evidence, dashboard) is designed and **not yet built**. There are no real quality-control labels for India: every accuracy figure is on synthetic faults and is labelled that way. No trained model has run on real data inside the platform. See [shared-docs/DATAMEND_ARCHITECTURE.docx](shared-docs/DATAMEND_ARCHITECTURE.docx) for the full picture and [TODO.md](TODO.md) for the build slices.

## What is in the repo

| Path | What |
|---|---|
| `backend/` | FastAPI backend. `backend/app/rainfall` is the live rain-gauge feed (Weather Union). The temperature/pressure/humidity pipeline is legacy and scheduled for removal. |
| `frontend/` | React + Vite dashboard (Vercel config in `frontend/vercel.json`). A throwaway prototype of the new dashboard layout is in `frontend/src/prototype-validation/` (not for production). |
| `ml-service/` | The model system (`ml-service/qc`, locked) and its training code. See `ml-service/README.md`. |
| `shared-docs/` | Documents for the team: the architecture and the integration guide for the AI implementation team (Word files). |
| `docs/` | Model specs (`qc-*.md`), the live-feed note, primary-source research (`docs/research`), the decision records (`docs/wayfinder`) and the seminar files. |
| `CONTEXT.md` | The glossary of terms. |

## Run it

Backend:

```powershell
pip install -r requirements.txt
copy .env.example .env     # set WEATHER_UNION_API_KEY and WEATHER_UNION_CITY to enable the live feed
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000/docs`. The live feed endpoints are under `/api/rainfall`; they return 503 until a key and a city are set.

Frontend:

```powershell
cd frontend
npm install
npm run dev      # http://localhost:5199
npm run build
```

Tests of the live feed (generated data and a mocked transport; no network, no API quota):

```powershell
python -m pytest tests/test_rainfall_feed.py -q
```

## Deploy

- **Frontend:** Vercel, branch `frontend`, root directory `frontend`, env `VITE_BACKEND_URL` set to the backend URL.
- **Backend:** Render, Docker, branch `backend` (`render.yaml`). The free plan has 512 MB RAM, no persistent disk (SQLite resets on restart) and sleeps after 15 minutes idle. Set `CORS_ORIGINS` to the Vercel URL.

## Documents

- [shared-docs/DATAMEND_ARCHITECTURE.docx](shared-docs/DATAMEND_ARCHITECTURE.docx): architecture of the platform and the model system.
- [shared-docs/DATAMEND_AI_INTEGRATION_GUIDE.docx](shared-docs/DATAMEND_AI_INTEGRATION_GUIDE.docx): the contract for the AI narrator.
- [docs/RAINFALL_LIVE_FEED.md](docs/RAINFALL_LIVE_FEED.md): the live gauge feed.
- [docs/wayfinder/rainfall-validation-platform/MAP.md](docs/wayfinder/rainfall-validation-platform/MAP.md): the decisions behind the platform design.
- [docs/qc-system-spec.md](docs/qc-system-spec.md), [docs/qc-evaluation-protocol.md](docs/qc-evaluation-protocol.md): the model system.
