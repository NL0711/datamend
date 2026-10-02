## Context

Task 4 (serve + triage) was explored against the repo and found functionally present but divergent: the task text names `src/api/main.py`, `src/api/websocket_broadcaster.py`, endpoints `/telemetry/live` and `/alerts`, and models `AWSReading`/`AnomalyEvent`/`SensorHealth`, while the repo ships `backend/app/main.py`, `backend/app/api/{routes,websocket}.py`, `POST /api/telemetry/process`, `GET /api/anomalies/alerts/active`, and `ObservationBase`/`AnomalyEventResponse`/`SensorHealthRecord`. Three performance criteria (API P99 < 20 ms at 500 concurrent, WS delivery ≤ 50 ms, no UI lag) have no measurements. The triage client (`submitOperatorFeedback` in `frontend/src/services/api.ts`) is never called by any component. Storage runs on SQLite locally (`skyguard.db*`, `sqlite+aiosqlite` default in `config.py`) while `.env.example`/`docker-compose.yml` present PostgreSQL/TimescaleDB as the assumed path. The user directed: rename (parity), prove perf, build triage UI, SQLite as truth.

## Goals / Non-Goals

**Goals:**

- Make every spec-named endpoint and model resolve against the real backend without breaking any existing route, import, or test.
- Produce measured perf evidence for all three criteria (pass or honest fail with numbers).
- Ship clickable triage actions that persist full audit rows.
- Leave SQLite as the working default with docs and config telling one consistent story.

**Non-Goals:**

- Moving backend files to `src/api/*` (pure churn: breaks imports, tests, Dockerfiles, run scripts for zero runtime gain).
- Retuning ML thresholds, redesigning fusion, or changing the fault taxonomy.
- Migrating production data or forcing Postgres removal (it stays as the documented production option).

## Decisions

- **Additive aliases, not renames/moves, for parity.** New routes (`/alerts`, `/telemetry/live`) delegate to the same handlers/services as their canonical twins; spec-named models are Pydantic aliases/subclasses of the canonical schemas with identical validation. Rationale: existing tests (`test_api.py`, `test_phase4_api_websocket.py`), the frontend client, and `docker`/`run.bat` all reference current paths — a hard rename breaks them for cosmetic gain. Alternative (move files to `src/api/`) rejected as high-churn/no-benefit.
- **`/telemetry/live` semantics = single-observation ingest + live broadcast.** It accepts one AWS reading, runs the standard ingest path, and pushes the result over the existing `ws_manager` broadcast so "live" means the same pipeline as `/observations`, not a second pipeline. Alternative (alias to full 6-stage `/telemetry/process`) rejected: that endpoint's heavy inference conflicts with the ≤ 50 ms delivery story and the 20 ms P99 story.
- **Perf harness lives in `scripts/` + asserts in `tests/`.** A 500-concurrency API probe (asyncio/httpx against the live app or `AsyncClient`), a WS delivery timer (ingest → subscribed-client receipt), and a dashboard streaming note (measured frame/render behavior during tick bursts, plus the existing mock-broadcast stress). Results land in `docs/evaluation_report.md`. Rationale: keeps slow/flaky load probes out of the default unit suite while tests assert the budgets that pass. If a budget fails, the spec requires recording the miss, not lowering the bar silently.
- **Triage buttons live where the operator already looks.** Actions attach to `AlertCenterView` (row-level) and `EventDetailView` (detail-level), calling the existing `submitOperatorFeedback` with `operator_id` (from session/settings context or prompt default), `event_id`, mapped `verification_status`, and optional notes; success/failure toasts and refetch follow. Rationale: reuses the tested `POST /api/feedback` + repository path instead of inventing a second feedback flow.
- **SQLite is the default truth; Postgres stays optional.** `config.py` default remains `sqlite+aiosqlite`; `.env.example` and docs are rewritten so SQLite is the dev/demo path and TimescaleDB is the opt-in production path (compose stays, but nothing in the default run requires it). Any Timescale-specific DDL stays fenced behind the Postgres path. Rationale: matches observed reality (`skyguard.db-wal` in repo, local runs on SQLite) and the user's explicit direction.

## Risks / Trade-offs

- [Risk] Alias routes double the API surface and can drift from canonical handlers → Mitigation: aliases delegate to the same service functions (no copied logic) and parity tests assert identical responses.
- [Risk] 500-concurrency probe is environment-sensitive (CI vs dev machine) → Mitigation: record hardware/context with numbers; gate the strict assert behind a marker/env flag so default CI stays green while nightly/perf runs enforce.
- [Risk] P99 < 20 ms may fail against the full inference path → Mitigation: measure the lightweight ingest/broadcast path the criterion implies; report honest numbers and, on miss, file the gap rather than weakening the spec silently.
- [Risk] Triage writes from the UI hit concurrent SQLite locking under load → Mitigation: reuse the existing async session/repository path (already concurrency-tested at 20 parallel ingests); feedback writes are single-row commits.
- [Trade-off] Keeping both old and new names means two ways to spell things — accepted for backward compatibility; docs mark canonical vs alias explicitly.

## Migration Plan

1. Land aliases (backend), triage buttons (frontend), SQLite doc/config alignment — all additive; rollback is revert-to-commit.
2. Run perf probes, record results in `docs/evaluation_report.md`; passing budgets become enforced tests, failing ones become tracked gaps.
3. No data migration: SQLite files and Postgres schemas untouched; `operator_feedback` table already exists in both paths.

## Open Questions

- Should `/alerts` return the `AnomalyEventResponse` list shape or a slimmer alert shape? (Default: same shape as `/anomalies/alerts/active`.)
- Operator identity source for triage (typed-in ID vs settings vs auth)? (Default: settings/default with per-action override field.)
- Which hardware is the perf referee (dev laptop vs CI runner)? (Default: record both, enforce on the perf-marked job.)
