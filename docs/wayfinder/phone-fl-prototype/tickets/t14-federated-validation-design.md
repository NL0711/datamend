---
title: What is the federated validation task: clients, model, labels and where the phones fit?
labels: [wayfinder:grilling]
status: open
assignee:
parent: MAP
blocked_by: [t13-federated-weather-qc-research]
---

## Question

Redesign the federated part around data validation and anomaly detection, not rain prediction. Decide: who the clients are (data custodians or station groups, as `ml-service/qc` already simulates with IMD sub-division groups, versus phones) and why federation is justified (raw station data that custodians cannot share, per the research ticket); the model (a temporal anomaly or fault detector over a gauge's own history plus gauge-context inputs: temperature, humidity, wind and their changes, time of day; the existing QC components in `ml-service/qc` are the reference); labels (synthetic fault benchmark and protected extremes per `docs/qc-evaluation-protocol.md`; no real fault labels exist); what the verdict the model feeds is (it must stay an optional score provider, the rule score and a calibrated flag never mixed, the narrator never changing a verdict); where the 3 real phones fit (on-device training of a validator over cached public gauge data is mechanics only; the app's job stays gauge alerts); what survives from the closed tickets (update protocol and Worker, simulated clients as simulated custodians, polled gauges, evaluation rules need rewriting for fault-detection metrics) and what is superseded (the rain-soon model, the barometer inputs, the 1-minute window design).
