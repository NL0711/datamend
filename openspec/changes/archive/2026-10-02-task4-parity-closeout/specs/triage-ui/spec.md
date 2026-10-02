## ADDED Requirements

### Requirement: Triage actions are clickable in the dashboard

The system SHALL provide Confirm Fault, Reject False Alarm, and Approve Imputation actions on alerts in `AlertCenterView` (row-level) and `EventDetailView` (detail-level).

#### Scenario: Operator confirms a fault from the alert feed

- **WHEN** the operator clicks Confirm Fault on an alert row
- **THEN** the dashboard sends the feedback request and shows success or failure feedback to the operator

#### Scenario: Operator rejects a false alarm from event detail

- **WHEN** the operator clicks Reject False Alarm in the event detail view
- **THEN** the dashboard sends the feedback request with `FALSE_POSITIVE` status

#### Scenario: Operator approves an imputation

- **WHEN** the operator clicks Approve Imputation on an event carrying an imputed value
- **THEN** the dashboard sends the feedback request with `IMPUTATION_APPROVED` status

### Requirement: Feedback persists full audit fields

The system SHALL persist every triage action with operator ID, event ID, verification status, and timestamp via `POST /api/feedback`.

#### Scenario: Triage round-trip stores the audit row

- **WHEN** a triage action is submitted for an event by an operator
- **THEN** the database holds a row with the matching operator ID, event ID, verification status, and timestamp, readable back through the API
