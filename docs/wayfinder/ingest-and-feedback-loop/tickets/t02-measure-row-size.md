---
title: Measure row size and compression on Tiger with generated data
labels: [wayfinder:task]
status: open
assignee:
parent: MAP
blocked_by: []
---

## Question

Facts the schema decision waits on, measured not assumed: bytes per row of the current run and result tables, and of a candidate lean hypertable (station, time, value, flags) with and without compression, for a generated 4-million-row series. Also ingest speed with COPY and the time to read one station-year. Needs the owner's OK to create and then drop test tables in the Tiger service (it holds no real data yet); use a separate schema and clean up after. Record the numbers and the Tiger plan used (free versus the trial).
