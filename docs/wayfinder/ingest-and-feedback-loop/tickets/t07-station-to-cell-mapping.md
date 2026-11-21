---
title: How do station points map onto RF25 cells for scoring?
labels: [wayfinder:research]
status: closed
assignee: research subagent (2026-11-20)
parent: MAP
blocked_by: []
---

## Question

Facts needed before the model hand-off is designed: how the existing code grids station data (the UK path `qc uk-grid` uses inverse-distance), what the RF25 cell size is against typical station spacing in India, what happens when several stations fall in one cell or none do, which RF25 components need neighbour cells, and how large the aggregation error is likely to be (from the repository and cited literature). Capture findings in a Markdown file; mark claims read or not verified; no recommendations.

## Resolution (2026-11-20)

Findings are on the local, unpushed branch `research/station-to-cell` (commit ee1034c, file `docs/research/station-to-rf25-cell-mapping.md`; every claim tagged read, measured or not verified). Facts the hand-off ticket depends on:

- No India station-to-cell aggregation exists in code. `backend/app/places/grid.py::cell_of` only returns the cell containing a point. The UK path (`qc uk-grid`) is the only gridding: inverse-distance weighting, 1/d squared, up to 4 gauges within 35 km, on a 0.1 degree grid; an empty cell is missing.
- An RF25 cell is about 22.8 to 27.8 km on a side. IMD built RF25 by inverse-distance weighting of 1 to 4 gauges within 1.5 degrees (read through the repo's research note, not the paper). No error field exists.
- The ISD station list covers 541 stations in 464 land cells, 9.3% of the 4,964 land cells; 454 occupied cells hold one station. Median distance from a land cell to its nearest station is 40 km. Only about 12% of ISD records carry rainfall, so rainfall coverage is thinner.
- Weather Union has 580 stations (267 rain gauges) in 30 cities, occupying 90 cells (1.8% of land cells); 95% of its stations share a cell with another; 98% of land cells have none.
- The spatial component uses a 13 by 13 patch with a hidden radius of 2 cells; the neighbour baseline radius is 6. They were built for complete fields; sparse-field behaviour was never run, and nothing has run on real RF25.
- Aggregation error between a point gauge and a 25 km cell mean is not quantified anywhere in the repository, and the literature was not searched. RF25 comes from the same kind of gauges, so station-versus-own-cell comparisons are not independent.
