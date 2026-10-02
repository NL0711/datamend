## ADDED Requirements

### Requirement: Icons appear only in the navigation bar

The system SHALL use lucide icons in the tab navigation bar only. Content views (cards, tables, dossiers, status strips, settings, injector) SHALL NOT render decorative icons; meaning is carried by typography and color.

#### Scenario: Content views have no decorative icons

- **WHEN** the frontend source outside the navigation bar is swept for lucide imports and icon components
- **THEN** no decorative icon usage remains (loading spinners and the triage-exempt list, if any, documented in the change)

#### Scenario: Navigation keeps its icons

- **WHEN** the operator uses the tab navigation bar
- **THEN** each tab still shows its icon alongside its label

### Requirement: Actions outside navigation are text-first

The system SHALL render action buttons outside the navigation bar (including triage Confirm/Reject/Approve, retry, copy, locate actions) as text buttons without leading glyph icons.

#### Scenario: Triage actions are text-only

- **WHEN** the operator views triage actions in the Alert Center or Event Detail view
- **THEN** Confirm Fault, Reject False Alarm, and Approve Imputation appear as text buttons that submit the same feedback payloads as before
