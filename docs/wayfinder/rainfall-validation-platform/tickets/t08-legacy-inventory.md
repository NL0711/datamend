---
title: What legacy temperature/pressure/humidity code, docs and hardware go, and what stays?
labels: [wayfinder:research]
status: closed
assignee: research subagent (2026-11-19)
parent: MAP
blocked_by: []
---

## Question

Inventory the repository (read-only) so the removal slice can be specified: every backend module, route, table, simulator, frontend component, test, doc, hardware folder and script that exists only for temperature, pressure and humidity; what is shared with the rainfall path and must stay (database layer, locations feature, `backend/app/rainfall`, spatial helpers, API shell, deployment files); dependencies that can be dropped (torch, shap, pyod, paho-mqtt, statsmodels?) and the effect on the image size and the Render free-tier memory; which tests cover only legacy code. Output: a Markdown inventory with file paths, grouped, and a suggested removal order that keeps the app running at each step.

## Resolution (2026-11-19)

Inventory is on the local branch `research/legacy-tpr-inventory` (commit a8ad12c, file `docs/research/legacy-tpr-inventory.md`, 206 lines; branch not pushed, throwaway). Facts the spec depends on:

- Legacy-only: about 50 backend modules, 33 REST routes plus 1 WebSocket, 6 DB tables, 11 frontend views, about 322 of 351 tests, 19 of 22 scripts, the hardware folder, 9 data CSVs, 8 model artifacts, about 35 docs. `ml-service` imports nothing from `backend`, so it is unaffected.
- The rainfall path (branch `isd-rainfall-feed`, not on `main`) uses no database, ML code, services, schemas or data sources, but is entangled in two places: `haversine_distance_km` lives inside `backend/app/spatial/consensus.py`, and the station catalogue CSV sits in the otherwise legacy `backend/app/sources/` package. Both must move first.
- `tests/conftest.py` imports `scripts.train_models` and trains legacy models for every test, so all tests depend on legacy code today.
- The Locations feature is itself temperature/pressure/humidity plus precipitation (decision needed: see the ticket on trimming Locations).
- Dependencies: `torch, shap, pyod, paho-mqtt, statsmodels, scikit-learn, scipy` are legacy-only; `psycopg2-binary` is unused; `asyncpg` depends on the persistence decision; `joblib, pandas, websockets` are also candidates.
- Measured on a Windows Python 3.13 machine (not the Render image): importing the app takes about 440 MB RSS, the shared stack about 87 MB. The CUDA-wheel image size and the 512 MB Render figure were not verified.
- Suggested order: merge the rainfall branch, move haversine and the CSV and decouple `conftest.py`, delete leaf files and legacy views, delete the backend top-down with its tests, trim config and Docker, drop dependencies last, rewrite docs.
