---
title: Which validation checks does the platform run on a rainfall time series?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

Which checks make up the platform's layered validation of one rainfall series, and which of them are rules, statistics or trained models? Start from what exists: the live scorer (`backend/app/rainfall/scorer.py`: negative, ceiling, jump, frozen, intensity/counter mismatch, neighbour check) and the `ml-service/qc` components (spatial, temporal, slow, rules). Decide: the check catalogue and its layers; which checks need neighbours or a long history and so apply only in some inputs (single gauge, gauge network, grid); how a genuine extreme is told from a fault; whether trained components are part of the platform or an optional plug-in.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner (Q1-Q7, all as recommended). Vocabulary is in `CONTEXT.md` ("Validation platform language").

1. **One check catalogue.** Each check declares what it needs (own history of N days, neighbours, a grid). A run executes the checks its input satisfies and lists the others as "not run: <reason>"; nothing is skipped silently.
2. **Two resolution profiles, `reading` and `daily`.** Readings are rolled up into daily totals (03 UTC to 03 UTC); the daily layer is where climatology and any score provider live. Monthly and yearly validation stay in the offline `ml-service` work.
3. **Genuine extreme versus fault at one gauge.** Magnitude alone never makes a verdict SUSPECT (except above the physical ceiling or an internal inconsistency); a heavy value without neighbours is an unverified extreme, judged UNCERTAIN. Confirmation comes only from neighbours or a grid (protected extreme: 4 or more connected cells).
4. **Trained components are an optional plug-in** behind a score provider. The platform runs fully on rules and statistics; trained scores add a layer, and are NOT IMPLEMENTED in the platform until a real RF25 run exists (none exists today).
5. **Two kinds of score, never mixed.** Default output is a rule score (fixed-weight ordering of suspicion, uncalibrated, never shown as a probability) plus a verdict. A calibrated flag appears only when a score provider is present and a clean-period false-alarm budget exists. UI and exports name which one a number is.
6. **v1 check catalogue.**
   - reading: missing or all-null (NO_DATA), negative value, intensity above a physical ceiling, counter jump, counter reset (informational), frozen non-zero intensity, intensity above zero with a flat counter, neighbour check (isolated wet or dry).
   - daily: impossible value (negative or above 1,000 mm), repeated positive value on consecutive days, own-climatology upper tail (gamma on the gauge's own earlier wet days, reported "not run" until 30 wet days exist), neighbour check on daily totals.
   - both: input-integrity checks (decided in the input-contract ticket).
   - excluded from v1: the slow 30/90-day component (needs an RF25 climatology) and the trained spatial and temporal models (score-provider layer only).
   - every threshold is recorded as a design choice, uncalibrated.
7. **Consequence for the legacy removal.** `scipy` stays (the climatology check needs it). `scikit-learn`, `torch`, `shap`, `pyod`, `statsmodels` and `paho-mqtt` still go. The two single-gauge scorers (`backend/app/rainfall/scorer.py`, `ml-service/qc/station.py`) are merged into this catalogue in a build slice; the ISD parser remains an input adapter.
