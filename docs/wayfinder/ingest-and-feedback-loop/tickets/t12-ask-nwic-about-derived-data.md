---
title: Ask the National Water Data Portal in writing about storing derived data
labels: [wayfinder:task]
status: open
assignee: owner (the question must come from the owner)
parent: MAP
blocked_by: []
---

## Question

Ticket t03 found that the CWC hourly rainfall resource is marked "Other (Open)" with no licence name, that the portal's copyright policy allows free reproduction with accurate use and prominent source credit, and that nothing covers storing or redistributing derived data. The platform already stores CWC hours, derived rain-day totals, flags and reviewer labels, and can send a snapshot of derived station data to a private Kaggle notebook (`backend/app/pipeline/kaggle_trigger.py`). The owner writes to NWIC asking: may derived flags, scores and aggregates be stored and shown in a research tool; may they be shared with a training service; may rows be redistributed; and what is the time zone and zero-hour convention of the files (so the IST and omitted-zeros assumptions in `backend/app/pipeline/cwc.py` can be confirmed or corrected). Record the reply and its date here. Until then every job and snapshot carries the assumption text.
