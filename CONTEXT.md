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

## Validation platform language

Terms for the rainfall time-series validation platform (the live gauge feed and uploaded series), settled in the wayfinder map `docs/wayfinder/rainfall-validation-platform`.

**Reading**:
One sub-daily gauge observation exactly as the provider reported it, with its intensity and its accumulation counter. Its units and counter period are stated only where the provider documents them.
_Avoid_: sample, packet

**Daily total**:
A gauge's rainfall for one rain day (03 UTC to 03 UTC), the same day definition as a cell-day. It is rolled up from readings or read directly from a daily source.

**Rain day**:
The 24 hours from 03 UTC on one date to 03 UTC on the next (08:30 to 08:30 IST), labelled by the date it ENDS, matching the IMD convention of rainfall recorded at 08:30 IST on that date.
_Avoid_: calendar day, UTC day

**Time basis**:
Whether a reading's time is when the gauge observed it (observed) or when the platform received it (received). The live Weather Union feed gives no timestamp, so its time basis is received, which makes gap checks weaker.

**Resolution profile**:
Which kind of series a validation run is on: readings or daily totals. The profile decides which checks apply.

**Check**:
One independent test of a reading or daily total that produces evidence. A check states what it needs (own history, neighbours, a grid); when the input cannot satisfy that, the run reports the check as not run, with the reason, never silently skipped.
_Avoid_: rule (a rule is one kind of check), detector

**Verdict**:
The platform's judgement of one reading or daily total: OK, SUSPECT, UNCERTAIN or NO_DATA. SUSPECT needs a violated rule or an internal inconsistency; disagreement with neighbours alone gives UNCERTAIN.
_Avoid_: anomaly, fault (a verdict is not a diagnosis)

**Rule score**:
A fixed-weight ordering of how suspicious a reading or daily total is, built from the checks that fired. It is uncalibrated and never a probability; severity (high, medium, low) is three documented bands of it. A calibrated flag is a different thing and exists only with a score provider and a clean-period false-alarm budget.
_Avoid_: confidence, probability

**Run**:
One validation of one input: an upload, or one rain day of the live feed. It records what was validated, with which settings and version, which checks ran and which did not and why, and every verdict. It is the unit that is stored, reported and exported.
_Avoid_: job, session

**Conformance suite**:
A set of minimal generated cases proving each check fires when it should and stays silent on a clean case. It reports pass or fail and is never presented as recall or precision.
_Avoid_: evaluation, benchmark (those need labelled data)

**Place lookup**:
A stateless mapping from a latitude and longitude to the RF25 cell that contains it, whether that cell is land, and its client region. It stores nothing. It is how a gauge is located in the grid and how a trained cell score is found for it.
_Avoid_: location (the old feature that also fetched model weather and stored places)

**Evidence**:
The structured facts behind one fired check: what was observed, the threshold and why it has that value, the readings or days the check looked at, the neighbours used, the time basis, and a basis tag on every number (measured, assumed or derived). Evidence is produced by the platform and never edited by an explainer.

**Explanation**:
A plain-language account of why a check fired, written from evidence. It is always marked generated, names its generator (the rule-based baseline or the narrator), and is shown beside the evidence, never instead of it.
_Avoid_: reason (the one-line reason inside evidence is the platform's own, not an explanation)

**Narrator**:
The teammate's LLM service that writes explanations from evidence. It is optional and external; the platform works with the baseline explainer alone.

**Unverified extreme**:
A heavy value at a gauge that has no neighbours or grid to confirm it. It is judged UNCERTAIN, never SUSPECT on magnitude alone. Distinct from an ambiguous extreme, which has neighbours showing ordinary rain.

**Score provider**:
An optional source of trained-component scores that adds a layer to a run. The platform runs fully on rules and statistics without one.

## Example dialogue

> **Dev:** "The spatial component flagged this cell-day. Could the cell's own value have leaked into the prediction?"
> **Domain expert:** "No. Everything inside the hidden disc is removed, so the prediction comes only from cells more than 2 away. If a synthetic fault is wider than the disc, though, the component partly sees it."
> **Dev:** "And the old two-direction model?"
> **Domain expert:** "That is the offline comparison. It sees the target and the future, so it never counts as a component."
