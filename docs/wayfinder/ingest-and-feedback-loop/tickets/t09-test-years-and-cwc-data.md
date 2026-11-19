---
title: May CWC data from 2018 to 2025 be used to train and judge the label-fusion model?
labels: [wayfinder:grilling]
status: open
assignee:
parent: MAP
blocked_by: []
---

## Question

The snapshot leaves out the locked test years 2018 to 2025 by default (`backend/app/pipeline/snapshot.py::LOCKED_TEST_YEARS`), the rule that protects the RF25 test pass. The one real CWC file measured (Tripura 2021 to 2025) lies wholly inside those years, so by default no snapshot can be made from it. Decide: is the lock about the RF25 gridded data only (then CWC station data of those years may train and validate the label-fusion model, which is a different model on a different source), or does it cover any data from those years? If it applies, which years of CWC data are usable (2026 only, or 2018 to 2025 kept as a test set for this model)? Record the decision in `docs/qc-evaluation-protocol.md` if the protocol changes.
