---
title: What does the federated-update literature say about aggregation, poisoned updates and the single-client case?
labels: [wayfinder:research]
status: closed
assignee: research agent (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []
---

## Question

From primary sources (original papers, framework docs), cover: FedAvg and what it reduces to with one client; update validation (norm clipping, anomaly screening of updates); secure aggregation and differential privacy (only to know what to label PLANNED); what update formats and sizes are used in mobile settings; evidence on federated learning from phone sensor data. Output: `docs/research/federated-update-protocol.md`. Do not make novelty claims (`AGENTS.md` section 5).

## Resolution (2026-11-19)

Findings are in `docs/research/federated-update-protocol.md` (most papers read as full text; Flower docs through a summarising fetch tool; items marked UNVERIFIED or DERIVED there). A fact-finding result, not a decision.

- FedAvg weights each client by its example count over the total. With one client the weight is 1, so the "global" model is that client's locally trained model: plain fine-tuning (DERIVED from the formula, not stated in the paper). Averaging works best from shared initial weights.
- Norm clipping is the standard update check, but it can be evaded and is a sanity check, not security. Robust aggregators (median, trimmed mean, Krum) need several clients per round: inapplicable with one device, so PLANNED.
- Secure aggregation and differential privacy are meaningless with one client: NOT IMPLEMENTED or PLANNED. The app must not say "private", "securely aggregated" or "differentially private"; it may say raw readings stay on the phone and only weights leave.
- Updates are full weights or a clipped delta of the same size; Google reports kilobytes to tens of megabytes. Compression is unnecessary at kilobyte scale.
- No source on barometer or rain-onset federated learning. The closest sensor evidence is human-activity recognition, simulated on a GPU rather than trained on phones.
- `ml-service/qc/federated.py` is a single-machine simulation with a weighted state-dict average and no update validation, so server-side update checks are NOT IMPLEMENTED anywhere in the repo.
- Open: update size (depends on the architecture), a clip bound (must be measured), whether device attestation is usable on a free tier, Flower's single-client behaviour.
