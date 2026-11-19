---
title: How does a registered model score station data on the server, and how is a candidate shadow-run?
labels: [wayfinder:grilling]
status: open
assignee:
parent: MAP
blocked_by: [t08-training-handoff-and-gate]
---

## Question

A champion today is registered and shown but changes no verdict or flag (`NOT_IMPLEMENTED` in `backend/app/api/pipeline.py`). Decide how it takes effect. Two parts. First, scoring: the label-fusion weights could be applied to the checks of a run directly (no grid needed), but scoring with the RF25 components needs the station-to-cell aggregation that ticket t07 found does not exist (the cell is about 25 km, most cells hold one station or none, aggregation error is unquantified). Decide which of the two is wanted first, where the aggregation lives, how its error is stated, and how a calibrated flag stays separate from the uncalibrated rule score (`AGENTS.md` section 7). Second, the shadow run in `docs/mlops-feedback-loop-spec.md` section 6: a candidate scores the stream silently beside the champion until the evidence is in; decide the evidence rule (the spec's 14 days and 200 disagreeing reviewed items are proposed, not confirmed) and whether a golden set of reviewed items that is never trained on is kept.
