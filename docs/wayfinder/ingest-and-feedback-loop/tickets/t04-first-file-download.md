---
title: What does one real CWC file look like?
labels: [wayfinder:task]
status: closed
assignee: owner approved, agent downloaded (2026-11-20)
parent: MAP
blocked_by: []
---

## Question

With the owner's explicit permission (name the file, source and size first), download one small state-year CWC hourly CSV into a scratch folder outside the repo, never commit it, and record its columns, row count, time zone, missing-value codes, station id and coordinate fields, and gaps. Resolved when the shape is written down and the file's licence status is noted.

## Resolution (2026-11-20)

Downloaded `rainfall_tel_hr_cwc_tr_2021_2025.csv` (Tripura, 619,754 bytes) from the National Water Data Portal into a scratch folder outside the repo; it is not committed. Measured with a throwaway script:

- **Columns:** SlNo, Station, Agency, State LGD Code, State, District LGD Code, District, Tehsil, Block, Village, River, Basin, Tributary, Subtributary, SubSubtributary, Local River, Latitude, Longitude, Data Acquisition Time (`dd-mm-yyyy hh:mm`, time zone not stated), Telemetry Hourly Rainfall (mm). Every station has coordinates.
- **Size:** 4,354 rows, 5 stations, 2021-01-12 to 2025-12-08. No duplicate (station, time) rows, no unparseable times or values.
- **Only non-zero hours are present:** the smallest value is 0.5 mm and the share of zeros is 0. A missing hour therefore cannot be read as dry or as missing, so completeness and "dry" neighbour checks cannot run on this file as they are.
- **Suspicious values:** 59 hourly values above 100 mm and a maximum of 423 mm in one hour; real in places or a unit or stage error, not decided here.
- **Coverage is patchy:** station row counts range from 128 to 1,939; one station stops in 2021; the median gap is 1 to 5 hours.
- **Licence:** still only "Other (Open)" with no name (see the terms ticket); ask the portal before storing derived flags.
