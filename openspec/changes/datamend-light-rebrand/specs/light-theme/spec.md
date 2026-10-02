## ADDED Requirements

### Requirement: Dashboard renders a light theme

The system SHALL render all dashboard views with light surfaces and dark text: light page background, white or near-white cards/panels/tables, slate-900 primary text with slate-600 secondary text, and light borders. No view SHALL present a dark navy background as its primary surface.

#### Scenario: Every tab opens light

- **WHEN** the operator opens each dashboard tab (Overview, Live Monitoring, Alert Center, Sensor Health, Event Detail, Data Explorer, injector, settings)
- **THEN** page, cards, tables, and panels render light surfaces with dark readable text

#### Scenario: No dark hexes remain on primary surfaces

- **WHEN** the codebase is swept for the legacy dark surface set (`#0F1726`, `#152033`, `#1B2A44`, `#233656`, `#0C1320`, `#263B5E`)
- **THEN** no matches remain on primary view surfaces (allowlisted accents such as code spans excepted and documented)

### Requirement: Severity and status remain readable on light surfaces

The system SHALL preserve severity/status color semantics (nominal/warning/critical/info) with text contrast suitable for light backgrounds, including status chips, badges, table cells, and charts.

#### Scenario: Severity chips meet contrast on light

- **WHEN** an alert of each severity renders in the Alert Center and Event Detail views
- **THEN** its chip pairs a deepened hue with a tinted light background and remains legible

#### Scenario: Charts remain legible on light

- **WHEN** telemetry and attribution charts render
- **THEN** gridlines, tooltips, and series colors are visible against light chart backgrounds
