## Why

The dashboard ships dark-only (hardcoded navy/slate surfaces), decorates views with dozens of lucide icons, and brands the product inconsistently ("DataMend" in 40+ files across UI, API, docs, and scripts). The product is DataMend and should look and read like it: light, clean, and consistently named.

## What Changes

- **Light mode:** the dashboard renders a light theme by default — light page/cards/table surfaces, dark-on-light text, preserved severity/status color semantics with accessible contrast. No dark-mode toggle in this change (single theme, done well).
- **Icon reduction:** decorative lucide icons are removed from content views (cards, tables, dossiers, status strips); navigation-bar icons stay. Text buttons replace icon+text action buttons outside the nav bar (including the triage actions).
- **DataMend rebrand:** every user-facing occurrence of the project name ("DataMend", "DataMend", "datamend" in display strings, titles, README, run scripts, API metadata, emails, package display name) becomes DataMend/datamend with consistent casing rules. Code module paths (`backend.*`), the SQLite filename, and MQTT topic roots stay unchanged for import/storage/wire compatibility and are documented as such.

## Capabilities

### New Capabilities

- `light-theme`: light-mode dashboard covering all views, shared components, charts, and status/severity semantics.
- `icon-discipline`: icon usage limited to the navigation bar; content views use typography and color, not decorative icons.
- `datamend-rebrand`: consistent DataMend naming across all user-facing surfaces plus docs, scripts, and metadata.

### Modified Capabilities

- None (existing specs in `openspec/specs/` describe backend behavior untouched by this change).

## Impact

- Affected code: `frontend/src/**` (views, design-system components, `index.css`, `tailwind.config.js`, `index.html`), `frontend/package.json` display name, backend API metadata/title strings (`main.py`, `config.py`), `README.md`, `run.bat`, `docker-compose.yml` labels, `docs/**`, user-facing strings in backend log/response messages where they name the product.
- Untouched: Python module paths, DB schema/filenames, MQTT topics, API routes and schemas, ML behavior, tests asserting behavior (tests asserting display strings updated where they hardcode the old name).
- Risk: visual regressions across many views — mitigated by token-based restyle plus `tsc` + production build verification.
