---
title: How do we evaluate and demonstrate the validation claim?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []   # t01 closed 2026-11-19
---

## Question

Decide what proves "validation platform": the synthetic-fault evaluation (precision, recall, F1, false-alarm rate, detection latency, protected-extreme flag rate, all labelled synthetic) and how it reuses `docs/qc-evaluation-protocol.md`; platform-level measures (throughput, latency of a run); the live demo script on the Weather Union feed, including what happens when no rain falls; what the claim does NOT include (real-label accuracy). Output: the list of numbers and demos the spec promises.

Added 2026-11-19 (from the ML training session's design): when a trained score provider exists, its evaluation should include a held-out fault-type split (train with one or more fault kinds removed, test on them; all synthetic) and per-kind recall on strong faults (as `ml-service/qc/ceiling.py` does), to guard against the model learning the fault generator. Decide whether the platform's claim includes these or leaves them to the ML evaluation protocol.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner (Q1-Q6, all as recommended). Vocabulary: Conformance suite in `CONTEXT.md`. Builds on `docs/qc-evaluation-protocol.md` (budgets, architecture rule, bridge, normalization) and `ml-service/qc/faults.py`.

1. **Daily profile, headline numbers.** Evaluated on RF25 per-cell series with faults injected by the existing frozen generator (radius 0 for the single-gauge checks, footprint faults for the neighbour check), reported as SYNTHETIC. RF25 is not on every machine (it runs on Kaggle) and is itself interpolated from gauges. The ISD replay of real Indian stations is an unlabelled demonstration only (flag rates, no recall), run locally and never committed (WMO Resolution 40).
2. **Reading profile.** Two claims, kept apart: a conformance suite (each check fires on a minimal generated case and stays silent on a clean one; pass or fail only, never recall or precision) and an observed flag rate on the real Weather Union raw log, labelled "unlabelled flag rate, not a false-alarm rate". No recall or precision is claimed for the reading profile until real labelled data exists.
3. **Platform performance.** Time to validate a 200,000-row upload, live poll cycle time and peak memory, each measured on the target environment (Docker with a 512 MB cap; earlier measurement about 305 MiB idle) with the machine named. No target is promised before it is measured.
4. **Live demo.** The live feed panel (readings, verdicts, call budget; honestly mostly dry) plus an upload of a clearly labelled synthetic file with injected faults through the same pipeline so every check visibly fires; synthetic data is labelled on screen. The Weather Union raw log stays local and is used to settle the accumulation mode the first time it rains. The ISD replay is not shown publicly.
5. **Detection metrics (daily profile, synthetic).** As defined in the protocol: recall per fault kind and overall at the shipped thresholds (a flag means verdict SUSPECT; UNCERTAIN is reported as its own row, in neither the fault nor the clean denominator); false alerts per 1,000 clean cell-days; event recall and detection delay for stuck, repeat and drift; protected-extreme false-flag rate; precision-recall area over the rule score with no calibration claim. The rules are deterministic, so one run suffices (not three seeds). Intervals come from resampling whole years, none for fewer than 5 years. If a score provider exists, its results are reported separately at the frozen budgets (final 1.0, review 5.0), never mixed with the rule results. When a trained provider exists its evaluation also includes the held-out fault-type split and per-kind recall on strong faults (as in `ml-service/qc/ceiling.py`), all synthetic.
6. **Not claimed (a section in the spec).** Accuracy on real labels (none exist for India); any trained-model result until a real RF25 run exists; calibration of the rule score; precision or recall for the reading profile; the units and period of Weather Union's accumulation counter; the quality of Weather Union's data; that any single check or the layered approach is novel. "Real-time" means polling every 15 minutes with received-time stamps.
