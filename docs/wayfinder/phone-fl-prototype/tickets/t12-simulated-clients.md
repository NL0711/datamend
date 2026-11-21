---
title: How are many simulated clients generated, run and kept honest next to the 3 real phones?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

The owner asked (2026-11-19) to add many simulated clients to the prototype (the 3 real phones stay). Decide: what they are for (convergence at 50 or 100 clients, uneven client data sizes and class balance, dropouts, a poisoned-update test of the norm clip and version check); how their windows are generated and what makes the generator defensible (it can only be synthetic, so what does it model, and what does it deliberately not claim); how many, and where they run (a laptop script against the Worker's real HTTP API versus in-process); and the honesty rules. Constraints already settled and to be kept: every simulated client, update and result is labelled synthetic wherever it appears; simulated updates never enter the real weights lineage and never count in any reported rain-skill metric (the evaluation rules say synthetic data is for tests and mechanics only); the app and the docs never present simulated convergence as evidence about real rain prediction; the device count shown for real results stays the number of real phones. Also to settle: whether `ml-service/qc/federated.py` (a single-machine simulation of 8 clients on RF25 data) is reused, extended or left alone, and whether the Worker needs a flag to keep simulated lineages separate.

## Progress (2026-11-19, ticket still open)

Owner chose data sources **B (physically motivated synthetic) and C (real monsoon station replay)** for the simulated clients, and not A (planted-signal synthetic, which is circular; it stays only as a unit-test fixture). Results from either are always labelled synthetic (B) or station-pressure proxy (C); simulated updates never enter the real weights lineage; nothing simulated counts toward a rain-prediction claim.

Availability check for C (NOAA ISD station list and the 2024 files for two Mumbai stations, downloaded to a scratch folder outside the repo, never committed; counts are from a crude parse and must be re-done when a loader is built):
- Station list: 430030 Chhatrapati Shivaji Maharaj Intl (VABB, Santacruz), 1944-01-01 to 2025-08-24; 430570 Bombay / Colaba, 2004-12-28 to 2025-08-24. ISD has no data after August 2025, so the 2025 monsoon is covered only to 24 August.
- 2024, VABB: 19,399 records, of which about 2,774 carry sea-level pressure and about 753 carry a liquid-precipitation group. 2024, Colaba: 1,275 records (about 3-hourly), all with sea-level pressure, about 341 with a precipitation group.
- Consequences: pressure is effectively hourly to 3-hourly, so the real replay can test a 3-hour pressure tendency (the WMO quantity), NOT the 10, 20 and 30 minute short pressure change the phone model uses; it is a separate proxy study with its own feature set, not a test of the phone model. A precipitation group present means rain was reported; its absence does not prove a dry period, so labels need care (unresolved, decided when the loader is written). Non-US ISD data must stay local and uncommitted (`AGENTS.md` section 6).

Still to decide in this ticket: how many simulated clients, where they run, what the physically motivated generator models, how the real replay is split across clients, and the poisoned-update test.

Also open from the model discussion, to be settled with the owner before the build: the net size (about 900 parameters, about 2,800, or a small temporal model), which phone-measured inputs the 3 phones actually have, and the nearest-gauge context decision; t05 is to be reopened with a dated addendum and t06's payload length updated once these are answered.

## Resolution (2026-11-19, confirmed by the owner; Q1 to Q6 as recommended)

Evidence base: `docs/research/federated-update-protocol.md` (federated averaging, norm clipping and what it does not stop) and the ISD availability check above. The net size and the phone-measured inputs are still open (below), so every size in the simulation is read from the model spec, not hard-coded.

1. **Purpose.** On synthetic data from generator B: federated versus local-only versus pooled training; uneven clients (data sizes, class balance, per-client sensor bias); dropouts; poisoned updates against the norm clip and version check. The real ISD replay (C) is a separate proxy study with its own 3-hour-tendency features, never a test of the phone model.
2. **Scale.** 50 simulated clients as the main run, sweeps at 10 and 100; 50 rounds; 20% of clients sampled per round; 3 seeds per setting; the spread across seeds is reported. The 3 real phones stay on their own lineage.
3. **Generator B.** Slow synoptic trend, tropical twice-daily swing (about 1 hPa), sensor noise, a fixed per-client bias of 1 to 2 hPa, occasional step artefacts; rain onset more likely as pressure falls, with a 0 to 60 minute lag and a per-client base rate. Every parameter is tagged `assumed`, documented and seed-fixed. **A null control is mandatory**: the same pipeline on data whose labels are independent of pressure must report no advantage over the baselines; if it does, the pipeline has a leak.
4. **Where they run.** The sweeps run in-process (fast, many seeds); a small run (10 clients, 5 rounds) goes through the real Cloudflare Worker's HTTP API as an integration test. Simulated lineage IDs start with `sim-`; the real phones' tokens are rejected on them and simulated clients are rejected on the real lineage. At 50 clients over 50 rounds the free daily request limit is not a concern (arithmetic, not measured).
5. **Code.** `ml-service/qc/federated.py` (the RF25 simulation) is left alone. New code in `ml-service/fed-sim/`: a small NumPy reference of the phone model and its training step, which also tests the phone's and the Worker's arithmetic so all three agree. It imports nothing from `backend/`.
6. **Poisoning and results.** 10% and 20% of clients poison with four attacks: a scaled update (x100), a sign flip, random noise, and a label flip trained honestly on wrong labels. The norm clip should stop the first three; the label flip will pass and the report says so, with robust aggregation PLANNED. Results are stored as experiment records (model, parameters, data version, seeds, metrics) under `ml-service/fed-sim/results/`, labelled synthetic; nothing goes in the app and no per-phase write-ups are written.

**Rules kept:** everything from this ticket is labelled synthetic (B) or station-pressure proxy (C) wherever it appears; simulated updates never enter the real weights lineage; nothing simulated counts toward a rain-prediction claim.

**Not settled here:** the net size, which sensors the 3 phones have, and the nearest-gauge context decision (see above); when they are answered, t05 is reopened with a dated addendum and t06's payload length is updated.
