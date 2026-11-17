## ADDED Requirements

### Requirement: Single global station selection

The system SHALL treat `selectedStationId` from `SystemConfigurationContext` as the only station selection. Every tab SHALL render data for that station (or an explicit fleet-wide scope where the view supports it).

#### Scenario: Station change propagates to all tabs

- **WHEN** the operator selects station AWS-002 in any station picker
- **THEN** the Live, Health, Alerts, Events, and XAI tabs all show AWS-002 data (Alerts defaulting to that station with an explicit "All stations" escape)

#### Scenario: No tab keeps a divergent station

- **WHEN** the frontend source is swept for private station states
- **THEN** no view holds a station selection that overrides or ignores the global id

### Requirement: Valid default station

The system SHALL reconcile the default station against the station registry, falling back to the first registry station when the stored default is absent.

#### Scenario: Unknown default falls back to registry

- **WHEN** the stored default station is not in the fetched registry
- **THEN** the global selection becomes the first registry station and every tab renders that station's data
