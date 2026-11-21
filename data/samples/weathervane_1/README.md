# Weathervane-1

A synthetic weather-fault benchmark made by DataMend. **Everything in it is synthetic**: the readings come from the project's seeded simulator
(diurnal temperature, pressure and humidity physics plus noise) and the faults are injected on purpose by the simulator's own injector. It
contains no measurement from a real station, so it says how DataMend's checks behave on this simulator, not how accurate they are on real data.

- File: `weathervane_1.csv` (17,280 rows). Rebuild it with `python scripts/make_weathervane.py` (seed 7; the same seed gives the same file).
- Stations: the six simulator stations KTLX, KOKX, KAMX, KATX, KFWS, KDMX. One reading a minute for two days from 2026-06-01 00:00 UTC.
- Timeline: the first six hours are clean. After that each station gets each of the eight fault kinds once, in turn, spaced so events do not overlap.

| column | meaning |
|---|---|
| `timestamp`, `station_id` | UTC time and station |
| `temperature_c`, `pressure_hpa`, `humidity_pct` | the reading as stored; empty = the source sent nothing (a DROPOUT), never filled in |
| `source` | `simulator` (the source label every stored reading carries) |
| `injected_fault` | ground truth, synthetic: the fault kind the injector applied to THIS reading, empty otherwise |
| `datamend_verdict` | what DataMend's rule checks said: `OK`, `UNCERTAIN` or `SUSPECT` (causal: only earlier readings of the station were used) |
| `datamend_rule_score` | the uncalibrated rule score (not a probability) |
| `datamend_checks_fired` | the checks that fired, `;`-separated |

Fault rows: SPIKE 12, DRIFT 360, FROZEN 240, NOISE_BURST 60, DROPOUT 30, MULTIVARIATE_INCONSISTENCY 30, METEOROLOGICAL_EXTREME 30, DATA_CORRUPTION 18;
16,500 rows carry no label.

## What DataMend's checks did on it (derived from the file, one pass, one seed)

- First six hours (2,160 clean rows): 0 flagged.
- Per fault kind, rows flagged UNCERTAIN or SUSPECT: SPIKE, DROPOUT, DATA_CORRUPTION, MULTIVARIATE_INCONSISTENCY, METEOROLOGICAL_EXTREME all flagged (the
  METEOROLOGICAL_EXTREME rows only as UNCERTAIN, never SUSPECT: a genuine extreme is not called a fault); FROZEN 198 SUSPECT of 240 rows; NOISE_BURST 50 of 60;
  DRIFT 258 of 360 (always UNCERTAIN, never SUSPECT; the slow start of a drift is not caught).
- **A weakness this file shows:** 283 of the 14,340 clean-labelled rows after the first fault were flagged (mostly `level_shift`: 265). They are mostly readings
  right after a fault ends, when the station's history still holds the fault. The label marks only the disturbed readings, so these count as false alarms here
  (about 20 per 1,000 clean-labelled rows after faults began, against 0 in the clean first six hours). The earlier S4 evaluation (0 false alarms in 86,400
  clean readings) used fault-free runs and does not show this.

Not a validation set for the Keras model score (that needs 288 readings per window and is "not validated"), and no accuracy claim should be made from one seed.
