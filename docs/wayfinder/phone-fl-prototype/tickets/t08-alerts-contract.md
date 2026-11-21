---
title: Is `/api/alerts` a new endpoint or a view over the existing ones, and what does it return?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

`/api/rainfall/stations`, `/api/places/locate` and the runs and evidence endpoints already exist. Decide whether the app needs a new location-aware alerts service (`backend/app/validation/alerts.py`) or can compose the existing calls; the response shape (SUSPECT alerts and a separate unverified list, evidence-v1 payload, the stored baseline explanation marked generated, the feed's time basis and unconfirmed units); radius and ordering; coordinates sent as query parameters and not logged; empty states (no gauges near, no open run, service waking). Read-only, no accounts, no admin token in the app.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner (Q1-Q6, all as recommended). Vocabulary: Gauge alert in `CONTEXT.md`.

1. **New endpoint.** `GET /api/alerts?lat=&lon=&radius_km=` backed by a new service, `backend/app/validation/alerts.py` (routes stay thin). It reuses the existing check, evidence and place code (`backend/app/geo.py` haversine, the station catalogue). No existing endpoint changes. The app makes one list call instead of about five.
2. **Source and staleness.** Only the latest run with `source == "live"` that is not synthetic. Uploads and synthetic runs never appear. The response carries `as_of` (last poll time); `state` is `stale` when the last poll is older than two poll intervals. A past rain-day run is labelled with its date and never presented as "now".
3. **Radius, order, counts.** Default radius 10 km, maximum 25 km, both tagged `assumed` (10 km is the platform's neighbour-check distance, itself assumed). Alerts are ordered by rule-score severity, then distance, capped at 20. Two arrays: `alerts` (SUSPECT) and `unverified` (UNCERTAIN, never mixed in). `gauges_in_range` is reported so "no alerts" differs from "no gauges near you".
4. **Explanation.** The list carries, per alert, the platform's one-line reason, the fired check names, `run_id` and `result_id`, and no explanations. On opening an alert the app calls the existing evidence endpoint, then the existing baseline `POST .../explain` for that row (the one existing write). The explanation is shown marked generated, beside the evidence. A narrator button appears only if `/api/validation/narrator` reports one connected (NOT IMPLEMENTED here).
5. **Location privacy.** The app rounds coordinates to 2 decimals (about 1 km) before sending. The server rejects finer precision, stores nothing and writes no coordinates to its own application logs. Platform logs may still hold the rounded query, so this is a mitigation, not a guarantee, and the docs say so.
6. **States and caveats.** Every normal condition returns 200 with `state` one of `ok`, `no_gauges_in_range`, `no_open_run`, `feed_off`, `stale`. Invalid coordinates return 422. Every response carries `prototype: true`, the feed's time basis (`received`), a units flag (`UNCONFIRMED`) and a coverage note (Mumbai only, 9 gauges). A free-tier cold start is handled in the app: a visible "service waking" state and retry (decided in the app-shape ticket).
7. **Tests (for the build slice).** Generated data or a mocked transport only: empty area, coordinates out of range or over-precise, no open run, feed off, stale feed, uploads and synthetic runs excluded, UNCERTAIN kept out of `alerts`, ordering and cap, radius limit.
