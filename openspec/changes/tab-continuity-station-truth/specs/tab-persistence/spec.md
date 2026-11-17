## ADDED Requirements

### Requirement: Tabs persist across switches

The system SHALL mount each tab view once (lazily on first visit) and keep it mounted, hiding inactive tabs with CSS instead of unmounting.

#### Scenario: State survives a tab round-trip

- **WHEN** the operator leaves the Live tab for another tab and returns
- **THEN** the timeline, scroll position, filters, and selections are exactly as left, with no refetch flash

#### Scenario: Hidden tabs do no background work

- **WHEN** a tab is hidden
- **THEN** its polling intervals and auto-refetch effects are paused (via the `active` prop) while the single global WebSocket client keeps running

### Requirement: Station switch resets cleanly

The system SHALL clear the Live timeline and dedupe cursor before hydrating the newly selected station, and drop frames older than the newest rendered point.

#### Scenario: No stale-station flash on switch

- **WHEN** the operator switches from station A to station B
- **THEN** no station-A points render under station B, and no out-of-order points enter the timeline from inflight fetches
