---
title: What does prior work say about federated learning for weather-station data validation and anomaly detection, and who could be the clients?
labels: [wayfinder:research]
status: closed
assignee: research agent (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

The owner chose (2026-11-19) to drop the phone barometer (the connected phone has none) and asked for another way to fit federated learning to data validation and anomaly detection. From primary sources, establish: (1) prior work on federated learning for weather or hydrometeorological station quality control and for sensor or time-series anomaly detection (models used, how clients are partitioned, labels, results, limits), so no novelty claim is made without a citation (`AGENTS.md` section 5); (2) which real data custodians in India (and elsewhere) hold gauge or weather-station data they cannot or will not share raw (IMD automatic weather stations and rain gauges, state networks, universities, commercial networks such as Weather Union, NOAA ISD), and what the sharing restrictions actually say (WMO Resolution 40, licences, terms), since that is the one genuine reason to federate; (3) which physical-consistency checks between rain, humidity, temperature and wind are used in operational QC, because those would be the inputs a gauge-context validator learns from (the gauge's own rain history is a legitimate input for validation, unlike for rain prediction, where it would leak the label). Output: `docs/research/federated-weather-qc-prior-work.md`. Feeds the redesign ticket.

## Resolution (2026-11-19)

Findings are in `docs/research/federated-weather-qc-prior-work.md` (read 2026-11-19; several pages returned 403 so some items are snippet-only; unverified items are marked there). A fact-finding result, not a decision.

- **Prior work exists for each ingredient, so no novelty claim.** FedLGAN (PeerJ CS 2023) federates a GAN plus LSTM for anomaly detection and repair on real hydrological telemetry from 4 stations (anomalies were injected noise; F1 0.788; non-IID data not tested). FedLSTM (Khan et al. 2024) does temperature with injected faults. A 2026 arXiv overview treats each station as a client and lists anomaly detection as a task. No primary source was found that federates rain-gauge or weather-station QC on real fault labels with custodians as clients (not found in the searches run, not proof of absence).
- **Correction to an earlier claim in this map:** the research does not support "custodians cannot share raw data" as a general statement. WMO Resolution 40 only allows conditions on commercial re-export of the additional data tier; the NOAA ISD readme says non-US ISD data "cannot be redistributed"; IMD's data-supply procedure says data "must not be shared with third parties" and its AWS portal was reportedly restricted in 2025 (newspaper quotes, not the replies). Weather Union is a free API whose terms were not opened (UNVERIFIED), not a "cannot share" custodian. No text found says anything about model weights or updates leaving a custodian, so whether any custodian would permit updates is unknown.
- **Consistency checks used operationally** (from a secondary 2004 WMO draft, HadISD, MADIS and others): dewpoint not above air temperature; gust not below mean wind; precipitation with zero duration or with zero cloud cover is suspect unless below gauge resolution; supersaturation; present weather against accumulated precipitation. All opened operational rules are fixed logic, and **no humidity-versus-rain or wind-versus-rain rule was found in any source opened**, so a learned rain-versus-humidity validator would not be an established operational check.
- Open: whether any custodian would let updates leave; Weather Union terms, the IMD tariff, state and university networks; whether Resolution 40 is withdrawn after WMO's 2021 data policy; the owning WMO documents (No. 305, 8, 100) were not opened.
