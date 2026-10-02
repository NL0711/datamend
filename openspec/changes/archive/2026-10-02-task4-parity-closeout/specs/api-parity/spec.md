## ADDED Requirements

### Requirement: Spec-named endpoint aliases resolve

The system SHALL expose `GET /api/alerts` and `POST /api/telemetry/live` as working aliases that delegate to the same handlers and services as `GET /api/anomalies/alerts/active` and the standard observation ingest path, with existing routes unchanged.

#### Scenario: Alerts alias matches canonical alerts

- **WHEN** a client calls `GET /api/alerts` with the same query parameters as `GET /api/anomalies/alerts/active`
- **THEN** both endpoints return the same status code and payload shape for the same database state

#### Scenario: Telemetry live ingests and broadcasts

- **WHEN** a client posts one valid AWS reading to `POST /api/telemetry/live`
- **THEN** the system persists the observation through the standard ingest path and pushes the result to subscribed WebSocket clients

#### Scenario: Existing routes keep working

- **WHEN** existing clients and tests call the current routes and imports
- **THEN** all previously working routes return the same results as before this change

### Requirement: Spec-named Pydantic v2 models validate identically

The system SHALL provide Pydantic v2 models named `AWSReading`, `AnomalyEvent`, and `SensorHealth` that enforce validation identical to their canonical counterparts (`ObservationBase`, `AnomalyEventResponse`, `SensorHealthRecord`).

#### Scenario: Reading alias accepts and rejects the same payloads

- **WHEN** the same payload is validated against `AWSReading` and `ObservationBase`
- **THEN** both accept the same valid readings and reject the same invalid readings with equivalent errors

#### Scenario: Event and health aliases mirror canonical shapes

- **WHEN** an anomaly event and a sensor health record are serialized through the alias and canonical models
- **THEN** field names, types, and value ranges match exactly
