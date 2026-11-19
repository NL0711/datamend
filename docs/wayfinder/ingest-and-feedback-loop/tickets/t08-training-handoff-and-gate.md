---
title: How does a training snapshot leave the platform and a model come back?
labels: [wayfinder:grilling]
status: open
assignee:
parent: MAP
blocked_by: [t06-reviewer-workflow-and-proposals, t07-station-to-cell-mapping]
---

## Question

Decide the hand-off: the dataset snapshot format and its time cut (training earlier, validation later, never the future, never test years), the leakage rules for station-derived cells, how the offline run is triggered and logs its metrics (MLflow or a table in the platform), the artifact import and registry (champion and challenger), the promotion gate and shadow rule on this data, and how a rejected candidate or a rollback is recorded.
