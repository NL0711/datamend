## 1. API parity aliases

- [x] 1.1 Add `GET /api/alerts` delegating to the active-alerts handler with identical query params and response shape
- [x] 1.2 Add `POST /api/telemetry/live` for single-reading ingest plus `ws_manager` live broadcast
- [x] 1.3 Add Pydantic v2 `AWSReading`, `AnomalyEvent`, `SensorHealth` models mirroring canonical validation exactly
- [x] 1.4 Add parity tests asserting alias-vs-canonical response and validation equivalence, with existing routes unchanged

## 2. Performance evidence

- [x] 2.1 Add 500-concurrency API probe script recording P50/P95/P99/max and error count with run context
- [x] 2.2 Add WebSocket ingest-to-receipt delivery timer test against the 50 ms budget
- [x] 2.3 Assess dashboard streaming under tick bursts and record frame/backlog behavior
- [x] 2.4 Record all three outcomes in `docs/evaluation_report.md`, enforcing passing budgets as marked tests and filing misses as tracked gaps

## 3. Triage UI

- [x] 3.1 Add Confirm Fault / Reject False Alarm / Approve Imputation actions to `AlertCenterView` rows wired to `submitOperatorFeedback`
- [x] 3.2 Add the same triage actions to `EventDetailView` with operator ID handling and success/failure feedback
- [x] 3.3 Add round-trip test proving UI payload → `POST /api/feedback` → persisted audit row with operator ID, event ID, status, timestamp

## 4. SQLite truth

- [x] 4.1 Verify fresh-clone default path (start, ingest, query, feedback) runs on SQLite with no external DB
- [x] 4.2 Align `config.py` default, `.env.example`, README, and docs on SQLite-default with TimescaleDB as opt-in production
- [x] 4.3 Fence Timescale-specific DDL to the PostgreSQL path and prove the default suite passes with no DB server
