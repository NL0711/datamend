## ADDED Requirements

### Requirement: User-facing name is DataMend everywhere

The system SHALL present the project name as DataMend (title case in prose, titles, and UI; `datamend` for package names, ids, and URLs) across the dashboard UI, `index.html` title, API docs title, README, run scripts, compose labels, user-facing docs, and user-facing backend strings (logs, errors, emails).

#### Scenario: No user-facing DataMend string remains

- **WHEN** the repo is swept for user-facing `DataMend`, `datamend`, and `DATAMEND` occurrences
- **THEN** every hit is either renamed to DataMend/datamend or recorded in the compat allowlist with its reason

### Requirement: Compat identifiers stay byte-identical

The system SHALL NOT rename Python module paths (`backend.*`), the SQLite filename, MQTT topic roots, or API routes/fields as part of the rebrand.

#### Scenario: Imports, storage, and wire protocol unchanged

- **WHEN** the rebrand is applied
- **THEN** all existing imports resolve, the existing database file is used as-is, MQTT topics are unchanged, and API contracts are byte-identical
