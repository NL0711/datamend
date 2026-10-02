## ADDED Requirements

### Requirement: API concurrency budget is measured

The system SHALL measure API P99 latency under 500 concurrent requests against the lightweight ingest path and record the result with hardware and run context.

#### Scenario: 500-concurrent probe records P99

- **WHEN** the 500-concurrency probe runs against a running backend
- **THEN** it reports P50, P95, P99, max latency, and error count in `docs/evaluation_report.md` with the machine and run context

#### Scenario: Passing budget is enforced

- **WHEN** the measured P99 is under 20 ms with zero errors
- **THEN** a marked test asserts the budget so regressions fail

### Requirement: WebSocket delivery budget is measured

The system SHALL measure alert delivery time from ingestion to subscribed-client receipt and record whether the ≤ 50 ms budget holds.

#### Scenario: Ingest-to-client delivery is timed

- **WHEN** an observation triggering an alert is ingested while a client subscribes to its station
- **THEN** the elapsed time from ingest call to client receipt is recorded and compared against 50 ms

### Requirement: Dashboard streaming smoothness is assessed

The system SHALL assess dashboard behavior under high-frequency streaming ticks and record the outcome.

#### Scenario: Tick burst renders without backlog

- **WHEN** a burst of live ticks arrives at the dashboard's streaming views
- **THEN** the assessment records render behavior (frames, backlog, dropped ticks) and states whether the no-lag criterion holds

### Requirement: Misses are reported honestly

The system SHALL NOT silently lower a performance budget; any missed criterion MUST be recorded as a tracked gap with numbers.

#### Scenario: Failed budget becomes a tracked gap

- **WHEN** a measurement exceeds its budget
- **THEN** the report records the measured value, the budget, the context, and the gap as remaining work
