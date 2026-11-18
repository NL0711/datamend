# Precipitation QC

Language for the precipitation quality-control work on RF25 gridded daily rainfall (`ml-service/`).

## Language

**Cell-day**:
One grid cell on one day; the unit that gets scored, labelled and flagged.

**Client**:
A fixed, compact group of grid cells that trains locally in the federated simulation: one of 8 groups of whole IMD sub-divisions (so a sub-division never mixes trained and unseen cells).
_Avoid_: site, station, tile, region

**Component**:
One independent source of evidence about a cell-day, producing its own score. There are four: spatial, temporal, slow and rules.
_Avoid_: branch, member, model (a component need not be a trained model)

**Spatial component**:
A trained predictor of a cell's rainfall from the same day's surrounding cells, with the hidden disc removed from its input.

**Hidden disc**:
The target cell plus every cell within 2 cells of it, which the spatial component never sees.
_Avoid_: blind spot (ambiguous about size), mask

**Temporal component**:
A trained predictor of a cell's rainfall on day t from that cell's own earlier days only.

**Slow component**:
An untrained score comparing a cell's trailing 30- and 90-day totals with its own climatology and with surrounding cells.

**Rules**:
Fixed physical and statistical checks that need no training.

**Offline comparison**:
The earlier models that read a whole window in both directions and see the target value. They are reported for comparison only and are not a component.
_Avoid_: baseline (reserved for the simple untrained or minimal references)

**Label tier**:
The provenance of an error label: expert-reviewed, historical flag, or synthetic fault. Results are never pooled across tiers. Only the synthetic tier is populated; the other two are reported as not available.

**Synthetic fault**:
A deliberate, recorded corruption of clean data, used as a controlled stress test.
_Avoid_: anomaly (also means a genuine climate extreme), injected anomaly

**Protected extreme**:
A connected group of cells all above their own heavy-rain threshold on the same day in uncorrupted data. It is plausible but unverified, is never corrupted, and the rate at which it is flagged is reported.

**Ambiguous extreme**:
A heavy value at a single cell with ordinary rain around it. It is neither protected nor an error; its flag rate is reported on its own.

**Case study**:
A documented, named heavy-rain event inside the test years, shown individually.

## Example dialogue

> **Dev:** "The spatial component flagged this cell-day. Could the cell's own value have leaked into the prediction?"
> **Domain expert:** "No. Everything inside the hidden disc is removed, so the prediction comes only from cells more than 2 away. If a synthetic fault is wider than the disc, though, the component partly sees it."
> **Dev:** "And the old two-direction model?"
> **Domain expert:** "That is the offline comparison. It sees the target and the future, so it never counts as a component."
