---
title: What are the CWC hourly rainfall data terms and file shape?
labels: [wayfinder:research]
status: closed
assignee: research subagent (2026-11-20)
parent: MAP
blocked_by: []
---

## Question

Read only, no downloads. For the National Water Data Portal dataset "Rainfall (Telemetry - Hourly), Central Water Commission" (`nwdp.nwic.gov.in/dataset/rainfall-cwc-telemetry-hourly`): the text of its copyright policy and disclaimer and any licence or reuse and redistribution terms (can we store and show derived flags, can we redistribute rows); the documented columns, whether stations carry coordinates, station counts per state, update frequency, whether there is an API and its limits. Capture findings with sources in a Markdown file; mark every claim read or not verified; no recommendations.

## Resolution (2026-11-20)

Findings are on the local, unpushed branch `research/cwc-terms` (commit 847b5c2, file `docs/research/cwc-hourly-rainfall-terms-and-shape.md`); the pages were read through a summarising tool, so quotes are fragments. Facts later tickets depend on:

- The resource page says "License: Other (Open)" with no licence name or URL; the dataset page states none; the footer says "© 2025 NWIC All Rights Reserved." (read)
- The portal Copyright Policy allows reproduction of site material free of charge in any format without specific permission, if reproduced accurately, not used in a derogatory or misleading context, and the source is prominently acknowledged. Third-party-marked material is excluded. (read)
- Nothing read mentions storing or redistributing derived data (flags, scores, aggregates). Not verified that the policy covers the dataset CSVs; the linked National Water Data Policy PDF was not readable.
- The Disclaimer gives no warranty on accuracy; CWC validates its own data; users should verify. (read)
- Shape: 83 CSVs, one per state or UT per period (1991-2020: 28, 2021-2025: 28, 2026-2030: 27), named `rainfall_tel_hr_cwc_<state>_<period>.csv`; fields named in the description are timestamp, station id, geographic hierarchy, rainfall value; last update 2026-11-19 00:41 UTC, no update frequency stated; CSV, TSV, JSON and XML downloads; an API exists but no endpoint, auth or limits were found.
- Not verified: column names, units, time zone, quality flags, station coordinates, station counts, a data dictionary, API limits. The next ticket (one real file) settles the shape.

The licence for storing and showing derived flags is still unclear: ask the portal (NWIC) in writing before relying on it.
