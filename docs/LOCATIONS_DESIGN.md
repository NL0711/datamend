# Locations feature: system design (v1)

Status: design for a first version built inside the existing web app (2026-11-17). Everything marked **NOT IMPLEMENTED** is outside v1.

## 1. Goal

A user adds a place (a name, or latitude and longitude). The app maps it to the 0.25-degree RF25/ERA5 grid cells it covers and shows, per cell:

1. recent weather: temperature, relative humidity, pressure, rainfall (last 7 days, hourly);
2. a **weather anomaly**: is today unusual for this cell and day of the year (against a seasonal normal)?
3. a **data-QC flag**: do the numbers look like a data fault rather than weather, with the reasons;
4. a slot for the scores of our trained models (`ml-service/qc`), shown as "not available" until saved scores exist.

First place: **Mumbai**, 4 cells at 19.0 N / 19.25 N and 72.75 E / 73.0 E, all in held-out client region 6 (a region the rainfall models never trained on).

## 2. Requirements

**Functional**
- F1 Add, list, view and delete locations. Mumbai is present from the start.
- F2 Name or coordinates in; cells out, with each cell's land/sea status and client region.
- F3 Per-cell current values and a 7-day hourly series.
- F4 Per-cell weather anomaly (z against the day-of-year normal; rainfall by wet-day percentiles).
- F5 Per-cell data-QC flag with reasons: physical range, hourly jump, stuck values, disagreement with the other cells of the location.
- F6 One classification per cell: `consistent`, `genuine_event_likely`, `possible_data_fault`, `uncertain`.
- F7 A pluggable place for trained-model scores.

**Non-functional**
- One user at a time to a few dozen; locations of 1 to about 30 cells. Status call under 3 s when cached, under 10 s on a cold fetch.
- Never invent data: when a source, a normal or a model score is missing, the response says so (`null` plus a reason), and the UI shows it.
- Polite to the free Open-Meteo API: cache, batch coordinates, no polling loop.

**Constraints**
- Existing stack: FastAPI, async SQLAlchemy on SQLite, React/Vite/TypeScript with recharts and lucide.
- No new infrastructure (no queue, no Redis). One process.
- No trained ERA5 or rainfall model artifacts are available locally yet.

## 3. High-level design

```
 Browser (React)                       FastAPI (backend/app)
 ┌──────────────────┐    REST     ┌────────────────────────────────────────────┐
 │ Locations tab    │────────────▶│ api/locations.py  (routes, validation)      │
 │  - location list │             │        │                                    │
 │  - add form      │             │        ▼                                    │
 │  - cell grid     │             │ locations/service.py (orchestration)        │
 │  - 7-day chart   │             │   ├─ grid.py       lat/lon → cells, land,   │
 └──────────────────┘             │   │                client, held-out         │
                                  │   ├─ openmeteo.py  geocode, recent series,  │
                                  │   │                30-year daily history    │
                                  │   ├─ normals.py    day-of-year mean/sd      │
                                  │   ├─ anomaly.py    weather anomaly          │
                                  │   ├─ qc.py         range/step/stuck/buddy   │
                                  │   └─ scores.py     ScoreProvider (files)    │
                                  │        │                                    │
                                  │        ▼                                    │
                                  │ SQLite: locations, location_cells,          │
                                  │         cell_normals, cell_series_cache     │
                                  └───────────────┬────────────────────────────┘
                                                  │ httpx (cached)
                                  Open-Meteo: geocoding, forecast (past_days),
                                              archive (1991-2020 daily)
 Static input: ml-service/qc/assets/client_map.json (land mask and client id per cell)
 Later: saved model scores  data/location_scores/<row>_<col>.json
```

**Data flow for `GET /api/locations/{id}/status`**
1. Load the location and its cells (or compute them on creation).
2. Ensure normals exist for each cell. If not, fetch 1991-2020 daily history once, compute the day-of-year mean and sd (15-day circular smoothing), store them.
3. Fetch the recent hourly series for all cells in **one** Open-Meteo call (multi-coordinate), unless a cache entry younger than 10 minutes exists.
4. Per cell: daily aggregates, anomaly, QC checks; then the cross-cell (buddy) comparison; then the classification.
5. Attach model scores if a score file exists, otherwise `model_status: "not_available"`.

## 4. Design decisions

**D1. A cell is a grid square, but the data is a point.** Open-Meteo snaps a requested coordinate to its own model grid. For (19.0, 72.75) it returned (19.016, 72.870): a point, not the 0.25-degree mean. The response therefore carries `grid_point` (what was actually returned) next to the cell centre, and the UI says "value at the nearest model grid point". Two cells can resolve to the same point; this is shown, not hidden.

**D2. Normals come from the same provider as the live values.** Open-Meteo archive (ERA5-based) 1991-2020, daily mean temperature, mean relative humidity, mean surface pressure, rainfall sum. Using the RF25 rainfall climatology against an Open-Meteo rainfall value would mix two products with different biases.

**D3. Two separate ideas of "anomaly", always labelled.**
- *Weather anomaly*: the value is unusual for the cell and day of year. Needs no model.
- *Data-QC flag*: the value looks like a data fault. v1 uses rule and statistics checks mirroring the "untrained" experts of `qc.multivar` (range, step, stuck), plus a buddy check across the cells of the location. This is explicitly **not** the trained gradient-boosted or neural experts; it says so in `qc.method`.

**D4. Genuine event versus fault by agreement.** A large anomaly seen by most cells of the location together is `genuine_event_likely` (a coherent weather event); the same anomaly in one cell while the others are normal is `possible_data_fault`. With about 4 cells this is a weak check, and the response reports how many cells it compared.

**D5. Rainfall is not a z-score.** It is zero-inflated and skewed. The anomaly is a wet-day percentile class (`dry`, `normal`, `heavy` above the cell's 95th wet-day percentile, `very_heavy` above the 99th), computed from the same 1991-2020 daily history.

**D6. Model scores are a plug-in, not a stub.** `ScoreProvider.get(cell, date)` returns real scores from files written by the ml-service pipeline, or `None`. v1 ships a file-based provider and the file format; no scores are generated or faked.

**D7. No websocket or alert integration in v1.** The existing `AnomalyEvent` and the websocket stream are keyed on `Station`. A cell is not a station. Mapping each cell to a virtual station is a possible v2; doing it in v1 would put grid data into the station health and fleet statistics.

**D8. SQLite and an in-process cache table.** Normals are rebuilt rarely and live in a table; the recent series is a 10-minute cache row per location. No Redis.

## 5. Data model

```
locations      id PK, name, latitude, longitude, radius_km, preset (bool), created_at
location_cells id PK, location_id FK, cell_row, cell_col, lat, lon,
               is_land (bool), client (int|null), held_out (bool)
cell_normals   cell_row, cell_col  (PK), source, period, built_at,
               temp_mean/sd, rh_mean/sd, pres_mean/sd (JSON arrays of 366),
               rain_wet_p95, rain_wet_p99, rain_wet_frac_by_doy (JSON)
cell_series_cache  location_id PK, fetched_at, payload JSON
```
Grid constants (same as `ml-service/qc/configs/base.yaml`): latitude 6.5 + 0.25 i for i in 0..128, longitude 66.5 + 0.25 j for j in 0..134; row 0 is the southernmost row.

## 6. API (all under `/api`)

| Method and path | Purpose |
|---|---|
| `POST /locations` | Body `{name, latitude?, longitude?, radius_km?}`. Geocodes the name if no coordinates. Returns the location and its cells. |
| `GET /locations` | List. |
| `GET /locations/{id}` | One location with cells. |
| `DELETE /locations/{id}` | Remove. Presets can be removed too. |
| `GET /locations/{id}/status` | Current values, anomalies, QC flags, classification, model status, `as_of`, `source`, `limitations`. |
| `GET /locations/{id}/series?days=7` | Hourly series per cell for the charts. |

Errors: 404 unknown id; 422 invalid input or a point outside the grid (6.5-38.5 N, 66.5-100 E); 502 with a plain message when Open-Meteo is unreachable (the UI keeps the last good response); partial results return what exists, with per-cell `status: "error: ..."`.

## 7. Caching, errors, retry

- Recent series: one row per location, 10 minutes. Stale data is returned with `stale: true` if the refresh fails.
- Normals: built once per cell, kept until the build code version changes.
- Open-Meteo calls: 10 s timeout, 2 retries with backoff (same style as `external_source.py`), one batched call per location.

## 8. Scale and reliability

- Cells per request about 4 to 30; one Open-Meteo call. A fresh location costs one archive call (30 years of daily values) plus one forecast call.
- The free API allows about 10,000 calls a day; v1 stays far below it. If many users add many places, move to a scheduled batch (fetch every 30 minutes for watched locations) and read from the table.
- Single process, so no failover. Reliability comes from caching and from degrading to "unavailable" instead of failing.
- Monitoring: log each external call with its latency (existing logging setup). **NOT IMPLEMENTED**: metrics endpoint, alerting.

## 9. Trade-offs

| Choice | Gain | Cost |
|---|---|---|
| Open-Meteo for everything | One free source, same variables as the app's external source, no keys | Values are model output at a point, not station observations; anomalies found are anomalies of that feed |
| Rule and statistics QC in v1 | Works now, honest, transparent reasons | Weaker than the trained experts; a smooth model feed rarely shows faults at all |
| Buddy check across few cells | Separates a coherent event from a one-cell oddity | Fewer than about 4 cells make it unreliable (reported) |
| No station-style alerts | Keeps fleet statistics clean | No push notifications for locations yet |
| Normals cached in SQLite | Fast status calls | One slow first request per new cell |

## 10. What I would revisit as it grows

1. Plug in trained-model scores once the Kaggle runs produce them (the interface exists).
2. Compare cells with real station observations where AWS stations exist nearby; this is the first real test of any ERA5-trained detector.
3. Virtual stations per cell to reuse alerts and the websocket.
4. A scheduled batch fetch and a data-table read path when more than a few locations are watched.
5. Neighbourhood resolution: 28 km cells cannot show differences inside a city.
6. Protection of genuine heat waves and cold spells (not built in the models either).
