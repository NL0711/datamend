## 1. Light theme foundation

- [x] 1.1 Flip the `datamend` Tailwind palette and `--sg-*` CSS variables to the light scale (page, surfaces, borders, text)
- [x] 1.2 Tune severity/status hues for light-background contrast (deepened text on tinted chips)
- [x] 1.3 Convert hardcoded dark hexes in all views and shared components to tokens or light values
- [x] 1.4 Restyle charts (gridlines, tooltips, series) and scrollbars for light surfaces

## 2. Icon discipline

- [x] 2.1 Remove decorative lucide icons from content views, keeping `App.tsx` tab navigation icons
- [x] 2.2 Convert TriageActions and other content action buttons to text-only, preserving payloads and behavior
- [x] 2.3 Verify no stray lucide imports remain outside the navigation bar (sweep + `tsc`)

## 3. DataMend rebrand

- [x] 3.1 Rename user-facing strings in the frontend (views, `index.html` title, package display name)
- [x] 3.2 Rename user-facing strings in backend metadata, logs, and messages (`main.py` title, `config.py`, responses)
- [x] 3.3 Rename project name in README, run.bat, compose labels, and docs
- [x] 3.4 Record the compat allowlist (module paths, DB filename, MQTT topics, API paths) and verify byte-identical behavior

## 4. Verification

- [x] 4.1 Run `npx tsc --noEmit` and the production build clean
- [x] 4.2 Sweep for legacy dark hexes and user-facing SkyGuard strings; clear or allowlist every hit
- [x] 4.3 Smoke every dashboard tab and the triage round-trip; run the backend test subset for regressions
