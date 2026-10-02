## Why

Task 4 verification (explore session) found the serving layer functionally present but nominally divergent from its task text, its three performance criteria unmeasured, its triage action unusable from the UI, and its database story split between SQLite reality and PostgreSQL docs. This change closes all four gaps so Task 4 can be called done honestly.

## What Changes

- **Rename/parity (additive, non-breaking):** spec-named endpoints (`/alerts`, `/telemetry/live`) and spec-named Pydantic v2 models (`AWSReading`, `AnomalyEvent`, `SensorHealth`) resolve against the real backend; existing paths (`/anomalies/alerts/active`, `/telemetry/process`, `ObservationBase`, `AnomalyEventResponse`, `SensorHealthRecord`) keep working unchanged. No file moves (`src/api/*` is not created; `backend/app/*` stays canonical).
- **Perf evidence:** the three Task 4 criteria are measured and recorded — API P99 under 20 ms at 500 concurrent requests, WebSocket alert delivery ≤ 50 ms from ingestion, dashboard streaming without UI lag — or reported as failed with numbers if the system misses.
- **Triage UI:** Confirm Fault / Reject False Alarm / Approve Imputation buttons in the alert/event views call the existing `submitOperatorFeedback` client against `POST /api/feedback`, storing operator ID, event ID, verification status, and timestamp.
- **SQLite truth:** SQLite (`sqlite+aiosqlite`) is declared and wired as the storage and operations database for development and demo; PostgreSQL/TimescaleDB remains an explicitly optional production path, and no supported flow requires it.

## Capabilities

### New Capabilities

- `api-parity`: spec-named endpoint and model aliases resolving to the canonical backend without breaking existing routes or clients.
- `perf-evidence`: measured proof (or honest failure report) for the API, WebSocket, and dashboard performance criteria.
- `triage-ui`: operator triage actions in the dashboard wired to the feedback endpoint with full audit fields.
- `sqlite-truth`: SQLite as the declared default storage/operations database with docs and config aligned.

### Modified Capabilities

- None (no existing specs in `openspec/specs/` to modify).

## Impact

- Affected code: `backend/app/api/routes.py`, `backend/app/schemas/schemas.py`, `backend/app/main.py` (if alias wiring needed), `frontend/src/components/AlertCenterView.tsx`, `frontend/src/components/EventDetailView.tsx`, `frontend/src/services/api.ts`, `backend/app/config.py`, `.env.example`, `docker-compose.yml` docs/comments, `docs/` evaluation notes.
- Affected tests: new parity tests (alias resolution, model equivalence), new perf measurement scripts/tests, triage round-trip test (UI handler → `/api/feedback` → DB row), SQLite default-path test.
- No breaking changes: all existing routes, imports, and stored data keep working; aliases are additive.
