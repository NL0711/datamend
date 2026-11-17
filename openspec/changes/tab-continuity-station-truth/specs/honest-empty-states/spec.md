## ADDED Requirements

### Requirement: Empty history renders an empty state

The system SHALL NOT fabricate telemetry points. When a station has no history after load, the Live view SHALL render an explicit empty state naming the station, with a manual reload action.

#### Scenario: Station with no data shows empty state

- **WHEN** hydration returns zero observations for the selected station
- **THEN** the chart area shows "No telemetry for {station} yet" (never a hardcoded 28.5 °C / 980.2 hPa / 72 % point)

#### Scenario: Failed hydration shows an error state

- **WHEN** the history fetch fails
- **THEN** the view shows a retryable error state instead of stale or invented data
