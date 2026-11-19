---
title: Does the Locations feature stay, and is it trimmed to precipitation only?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

The legacy inventory found that the Locations feature (place to RF25 cells, Open-Meteo values, weather anomaly against normals, data-QC flags, buddy check, Locations tab) is itself temperature, humidity and pressure plus precipitation. The destination is rainfall only. Decide: does Locations stay as part of the platform (a way to point the validator at a place), get trimmed to precipitation, or go; what its role is next to the live gauge feed and uploads; and what happens to its four shared database tables. Surfaced by the closed ticket on the legacy inventory.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner (Q1-Q4, all as recommended). Vocabulary: Place lookup in `CONTEXT.md`.

1. **What stays.** Option B: a stateless place lookup (`locate(lat, lon)`) plus the `ScoreProvider` seam, in a new `backend/app/places` package. It returns the RF25 cell, its land/sea status and its client region. It stores nothing. Run reports use it to add cell and region to each station's section, and the optional trained layer uses it to find a gauge's cell score.
2. **What goes.** The four tables (`locations`, `location_cells`, `cell_normals`, `location_series_cache`), the Locations tab, the Open-Meteo client, the day-of-year normals and weather-anomaly code, and the temperature/pressure/humidity QC. The precipitation checks that Locations had are covered by the check catalogue (see the ticket on validation checks).
3. **Open-Meteo is dropped from the platform.** It is a weather model product, not an observation, so no model product is ever labelled as an observation. Gauges (Weather Union, uploads, the ISD replay) are the only inputs. A model-based reference, if ever wanted, starts as a new ticket.
4. **Region returned.** The client region comes from the committed `ml-service/qc/assets/client_map.json`. The IMD sub-division is returned only when the boundary file (`sd_boundary_rainfall.json`, fetched by script, not committed, licence unstated) is present locally, otherwise "not available". It is not shipped to deployments in v1.
5. **When and how.** The removal is a slice after the new platform views exist, so the app has no gap. Order inside the slice: move the lookup and its tests into `backend/app/places`, then delete the old Locations code, tables and tab. `docs/LOCATIONS_DESIGN.md` and `docs/LOCATIONS_MODEL_SCORES_PLAN.md` are marked superseded and kept as history. The Mumbai preset becomes a documented example and a test fixture, not a stored preset.
