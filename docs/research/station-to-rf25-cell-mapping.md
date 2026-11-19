# Station to RF25 cell mapping: what the repo does and what the data shows

Date: 2026-11-19. Question source: ticket `docs/wayfinder/ingest-and-feedback-loop/tickets/t07-station-to-cell-mapping.md`. **That file does not exist in this repository** (not on the current branch, not in the shared checkout, not in any commit); the question below was taken from the task wording: how station data maps onto grid cells today, RF25 cell size against Indian station spacing, what happens with several or zero stations per cell, and what is known about aggregation error.

Tags: **READ** = read in a file of this repo on this date (path given). **MEASURED** = computed in this task from repo files (method given in section 6). **NOT VERIFIED** = not checked against a primary source here. No design recommendations are made.

## 1. Cell definition and station-to-cell lookup in the repo

- RF25 grid: 129 x 135 cells, 0.25 degree step, latitude 6.5 + 0.25*row (row 0 south), longitude 66.5 + 0.25*col, 4,964 land cells. READ: `ml-service/qc/configs/base.yaml` (grid block), `backend/app/places/grid.py`.
- Cell size in km: 0.25 degree of latitude is 27.8 km; 0.25 degree of longitude is 27.5 km at 8 N, 26.1 km at 20 N, 24.5 km at 28 N, 22.8 km at 35 N. MEASURED (111.195 km per degree, the constant used in `grid.py` and `uk/gridding.py`).
- Whether a grid coordinate is the cell centre or a corner in IMD's file is not stated in any repo document; `backend/app/places/grid.py` treats the node as the centre of the 0.25 x 0.25 square (READ, a docstring statement). NOT VERIFIED against IMD.
- The only point-to-cell function that exists is `grid.cell_of(lat, lon)`: `(round((lat-6.5)/0.25), round((lon-66.5)/0.25))`, i.e. the single cell whose square contains the point; it raises `GridError` outside the domain. `lookup.locate` adds the land flag and client region from `ml-service/qc/assets/client_map.json`. READ: `backend/app/places/grid.py`, `lookup.py`. `grid.cells_for(lat, lon, radius_km)` returns every cell overlapping a box around a place, at most 40 cells. READ.
- There is no code anywhere that turns several station values into one cell value for India. `rainfall/daily.py` produces a per-station daily total on the 03 UTC to 03 UTC day (same day definition as IMD/RF25), and `ml-service/qc/station.py` scores a single station from its own history. READ: `backend/app/rainfall/daily.py`, `ml-service/qc/station.py`, `docs/qc-multires-pipeline-spec.md` section 7 ("a scorer that works on one station ... because the RF25-trained spatial models need grid neighbours" is listed as NOT BUILT there; `station.py` was added later and is a one-station scorer, not calibrated).
- `backend/app/places/scores.py` defines a `ScoreProvider` keyed by `(row, col, day)`, one file per cell; no score files exist. READ.

## 2. How RF25 itself was made from stations (the only station-to-cell method documented)

- READ (secondhand: `docs/research/operational-rainfall-qc-primary-sources.md`, which cites Pai et al. 2014, MAUSAM 65(1), local copy `ref_paper_MAUSAM.pdf`, and says it re-checked it; I did not open the PDF): inverse-distance weighting (Shepard 1968), for each grid point a minimum of 1 and a maximum of 4 nearest stations within 1.5 degrees (about 167 km); the paper's own station count is inconsistent (6955 vs 6995); about 3,500 gauges per day on average, ranging 1,450 to 3,900; 1,450 in 1901, about 3,100 per day from 1951, later about 1,900 per day (wording flagged UNVERIFIED in that file).
- READ (same file): RF25 carries no QC flags and no uncertainty field; the paper states the grid is a smoothed estimate so grid values are not station values; the file found no statement quantifying interpolation error (marked "UNVERIFIED as absent" there).
- READ: `docs/PROJECT_OVERVIEW_MODEL.md` s3 and `docs/qc-system-spec.md` s2 state that neighbouring cells share gauges and are therefore not independent.
- READ: `docs/qc-multires-pipeline-spec.md` s7 says RF25 is partly built from these gauges, so RF25 climatology at a station's cell is not independent of that station. NOT VERIFIED which gauges overlap with ISD stations or Weather Union (no overlap check exists in the repo).
- IMD gridding details beyond the above ("Directional effects and barriers" and Rajeevan et al. 2006) were not read by anyone in the repo. NOT VERIFIED.

## 3. The UK study: the one place where stations are mapped to cells in code

READ: `ml-service/qc/uk/gridding.py`, `qc/uk/build.py`, `qc/configs/uk.yaml`.

- Command `python -m qc uk-grid --config qc/configs/uk.yaml` (`cmd_uk_grid` calls `build_grid`) grids MIDAS station values onto a UK grid and writes RF25-format NetCDF, so the pipeline reads it unchanged.
- The UK grid is **not** 0.25 degree: 15 x 39 cells at 0.1 degree (about 11 km), 49.9-51.3 N, -5.8 to -2.0 E. The spacing is marked OPEN in the config.
- Method: for every cell, the stations within `search_radius_km` = 35 (OPEN), at most `max_gauges` = 4 with a finite value that day, weight 1/d^2 with d floored at 1 km, distances by equirectangular approximation. `neighbour_table` keeps up to 24 candidate stations per cell, nearest first. These differ from RF25's published 1.5 degree radius (READ above); the code comment says the aim is "the way RF25 was made".
- Zero stations in range, or none with a value that day: the cell is NaN (`np.where(tot > 0, ..., nan)`), written as fill value -999, i.e. missing. Same code path for one station (the cell takes that station's value, weight cancels) and for up to four (weighted mean). A station is never assigned to "its" cell only: it feeds every cell within 35 km where it is among the four nearest with a value.
- Labels: a cell-day is labelled bad if a hand-corrected station that fed the ORIGINAL cell value changed the cell value by more than 0.001 mm; cells whose value changed without a manual correction feeding them are excluded (not scored, not clean). `docs/mlops-feedback-loop-spec.md` s3b states "a bad station spreads over several cells". READ.
- The UK reader is documented as untested on real files and only a Devon subset was downloaded (READ: `docs/mlops-feedback-loop-spec.md` s3b). No UK grid has been built in this repo's data folder (not checked in this task beyond the config; NOT VERIFIED whether any exists elsewhere).

## 4. What the spatial and temporal components need from neighbours

READ: `ml-service/qc/configs/base.yaml`, `qc/neighbours.py`, `qc/untrained.py`, `qc/models.py`, `qc/context.py`.

- Ring lookup: for each land cell, the land cells at Euclidean distance r_in < d <= r_out (in cells); off-grid, off-land or not-allowed neighbours are -1 and gather as NaN.
- Defaults: hidden radius 2 cells (nothing within it is read; about 55 km); spatial patch radius 6 cells (a 13 x 13 patch, about 330 km across); slow comparison ring 2 to 4 cells; neighbour baseline radius 6 cells; temporal component uses the cell's own previous 30 days only. UK config: hidden radius 1, patch radius 3, slow ring up to 3.
- The spatial net takes a value channel and a validity channel and multiplies the hidden disc by zero inside `forward`; the neighbour baseline and slow comparison treat NaN neighbours as unusable, and with no usable neighbour the score is 0 ("no evidence"). The temporal GRU and plain GRU also take a validity channel.
- All of these were developed on a dense, complete field: every land cell has a value every day in RF25. The code does not state a minimum number of valid neighbours. NOT VERIFIED how scores behave when only a small fraction of cells carry values (no such run exists; nothing has run on real RF25, per `docs/qc-multires-pipeline-spec.md`).
- A cell value comparison requires each station value to be a cell value; the 4 homogeneous regions and 36 sub-divisions are aggregated from cells (`regions.py`), not from stations. READ.

## 5. Station spacing against the cell size (India)

All numbers MEASURED from the two catalogue files with the repo's own `grid.cell_of`, 111.195 km per degree, land mask from `client_map.json` (4,964 land cells). Method in section 6.

**IMD-named catalogue** `backend/app/places/data/imd_stations.csv`. READ: `backend/app/places/imd.py` gives its source as "NOAA NCEI isd-history.csv (Indian stations, station metadata only)", so it is the NOAA ISD list of Indian stations, not IMD's own gauge network. It lists 541 stations in the RF25 domain.

| quantity | value |
|---|---|
| stations on RF25 land cells / on non-land cells | 507 / 34 |
| distinct cells occupied; land cells occupied | 495; 464 (9.3% of 4,964) |
| stations per occupied cell (1, 2, 3, 4) | 454, 37, 3, 1 cells |
| share of stations that share a cell with another | 16.1% |
| nearest-neighbour distance km: min / p10 / median / mean / p90 / max | 0.0 / 5.8 / 41.4 / 42.8 / 82.0 / 256.1 |
| share of stations with a neighbour closer than 27.8 km | 37.5% |
| land cells with zero stations in the cell | 4,500 of 4,964 |
| land cells with no catalogue station within 1.5 degree (about 167 km) / at least 4 within it | 148 / 4,557 |
| land cell to nearest station km: median / p90 / max | 40.2 / 86.7 / 337.6 |
| stations whose `last_data` is 2025-01-01 or later | 383 of 541 |

Caveats: this is a metadata catalogue (first and last data dates), not a count of stations that report rainfall. Per `docs/qc-multires-pipeline-spec.md` s7, of 369 Indian ISD files for 2022, 349 had some liquid-precipitation data but only 11.7% of records did; 343 stations had at least one 03 UTC 24-hour total (READ, spec). The land-cell counts above therefore overstate coverage by rainfall-reporting stations. ISD has no data after 24-25 August 2025 (READ, spec s7). Non-US ISD data must not be redistributed (WMO Resolution 40): these figures use coordinates only.

**Weather Union catalogue** `backend/app/rainfall/data/weather_union_stations.csv`: 580 stations in 30 cities; device type 1 = automated weather system (313), type 2 = rain gauge (267) (MEASURED; matches `docs/RAINFALL_LIVE_FEED.md`, READ). All 580 fall inside the domain.

| quantity | all 580 | the 267 rain gauges |
|---|---|---|
| on land cells / non-land cells | 561 / 19 | not computed |
| distinct cells occupied | 90 (88 land, 1.8% of land cells) | 79 |
| stations per occupied cell | 1 station: 28 cells; 2: 10; 3: 9; 4: 4; up to 41 in one cell (row 88, col 43) | 1: 30 cells; 2: 14; 3: 10; up to 16 |
| share of stations sharing a cell with another | 95.2% | not computed |
| nearest-neighbour distance km: median / p90 / max | 2.9 / 6.3 / 115.3 | not computed |
| land cells with no station within 1.5 degree | 2,587 of 4,964 | not computed |

Notes: the catalogue lists stations within cities, so almost all are spaced a few km apart, much closer than the 25 to 28 km cell. Rain-gauge stations (type 2) are in 29 cities. Rain-gauge density in Weather Union is a city-scale network, not a national network.

IMD's own gauge network (about 3,100 to 3,500 stations per day in RF25, section 2) is not in the repo as coordinates. NOT VERIFIED: its spacing; not measured here.

## 6. What happens with several or zero stations in a cell

- In the repo's India code: nothing is defined. `cell_of` returns one cell per point and no aggregation of station values per cell exists (section 1).
- Measured occupancy (section 5): with the ISD list, 454 of 495 occupied cells have exactly one station and 4,500 of 4,964 land cells have none; with Weather Union, 95% of stations share their cell, up to 41 stations in one cell, and 98% of land cells have none.
- In the UK code (section 3): several stations in range are inverse-distance averaged (up to 4); none in range gives a missing cell.
- In RF25 itself (section 2): 1 to 4 stations within 1.5 degree; whether a grid point with no station within 1.5 degree is filled or left missing is not stated in anything read. NOT VERIFIED. The 122 of 4,964 land cells that are in no IMD sub-division (READ: `docs/qc-multires-pipeline-spec.md` s9) is a different matter (boundary file coverage).
- Coastal points: 34 of 541 ISD stations and 19 of 580 Weather Union stations fall on cells that are not land in the RF25 mask (MEASURED); for the places lookup, `describe_cell` reports `is_land` false for them (READ), and the spec records that Chennai's cell is sea in RF25 (READ: spec s9).

Method for section 5 (MEASURED): script run once in the scratchpad (not committed), importing `backend.app.places.grid` for `cell_of`, `in_domain` and `client_map`; nearest-neighbour distance by equirectangular approximation from each station to every other; land-cell distances from the cell centre lat/lon to every station. Duplicated coordinates give distance 0.0.

## 7. Aggregation error (point gauge versus a 25 km cell mean)

- In the repo: no document quantifies point-to-cell representativeness error for rainfall. A text search of `docs/`, `ml-service/qc` and `backend/app` for representativeness, upscaling, point-to-pixel and scale mismatch found no relevant hits (MEASURED by search, not a guarantee of absence).
- READ (secondhand, above): Pai et al. 2014 describes RF25 as a smoothed estimate where grid values are not station values; no interpolation error is quantified in the extracted text.
- READ: `docs/research/multires-models-evaluation-live-source.md` line 158 gives an opinion, not a source, that merged or satellite fields are smoother than RF25.
- Pai et al. 2014 also compares IMD4 with APHRODITE (monsoon bias +0.84 mm/day) and IMD3 (about 1.5% on the all-India annual mean) (READ, secondhand); these are grid-to-grid differences, not station-to-cell.
- Literature on areal reduction of daily point rainfall, kriging or IDW cross-validation error, or gauge-to-grid comparison was **not searched and is NOT VERIFIED**; no citation is given here. The repo's one case with real station-versus-grid comparison is the UK work, which has not run on real files (READ).
- READ: `docs/qc-multires-pipeline-spec.md` s7: RF25 contains the gauges, so a comparison of a station against its own cell's RF25 value is not independent.

## 8. Gaps

- The ticket file t07 and its parent folder `docs/wayfinder/ingest-and-feedback-loop/` are absent from the repository.
- No IMD gauge coordinates, no list of which stations fed RF25 on which day, and no RF25 files are in this worktree (RF25 is fetched from Kaggle by `scripts/fetch_rf25.py`; not run here).
- No check was made of whether ISD or Weather Union stations coincide with IMD gauges that fed RF25.
- Literature on aggregation error: not searched, not verified.
