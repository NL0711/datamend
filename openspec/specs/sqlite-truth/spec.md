# sqlite-truth — SQLite as Default Storage

SQLite (`sqlite+aiosqlite`) is the declared default storage and operations
database for development, demo, and tests; PostgreSQL/TimescaleDB is the
opt-in production path. Source change: task4-parity-closeout.

## ADDED Requirements

### Requirement: SQLite is the default storage and operations database

The system SHALL run its full default path — ingest, inference persistence, anomaly history, sensor health, alerts, and operator feedback — on SQLite via `sqlite+aiosqlite` with no external database required.

#### Scenario: Fresh clone runs end to end on SQLite

- **WHEN** a developer follows the README with only the default configuration
- **THEN** backend start, observation ingest, anomaly query, health query, and feedback submit all succeed against the local SQLite file

### Requirement: Configuration and docs tell one SQLite story

The system SHALL declare SQLite as the development and demo database in `config.py` defaults, `.env.example`, and user-facing docs, with PostgreSQL/TimescaleDB documented strictly as the opt-in production path.

#### Scenario: Docs and defaults agree

- **WHEN** a developer reads the environment template and database docs
- **THEN** SQLite is presented as the default and TimescaleDB as the optional production upgrade with its own setup steps

### Requirement: No supported flow requires PostgreSQL

The system SHALL NOT require a PostgreSQL server for any supported development, demo, or test flow, and Timescale-specific DDL MUST stay fenced to the PostgreSQL path.

#### Scenario: Default test suite passes without Postgres

- **WHEN** the supported test suite runs with no database server available
- **THEN** all database-backed tests pass against SQLite
