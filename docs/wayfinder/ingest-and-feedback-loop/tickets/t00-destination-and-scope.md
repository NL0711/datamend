---
title: Destination and scope (chart-time decisions)
labels: [wayfinder:grilling]
status: closed
parent: MAP
blocked_by: []
---

## Question

What does this map find its way to, and how does it relate to what exists?

## Resolution (2026-11-20, owner accepted the recommended answer to each of six questions)

1. **Destination:** a locked spec and ordered slices, not the build. The one-day demo is the current build (sign-in, replay, map, checks, evidence, review loop), deployed and verified.
2. **Existing spec:** extend `docs/mlops-feedback-loop-spec.md`. Keep the ladder, gate, shadow rule, leakage rules and audit sampling; replace the simulated India reviewer with the owner as a real reviewer using AI help. UK replay stays separate.
3. **Where training runs:** offline (Kaggle or a GPU machine) from a dataset snapshot the platform exports. The server holds the label store, registry, scoring and promotion gate; the platform imports the artifact after the gate.
4. **Sources in v1:** rainfall station sources only, one adapter per source, a licence check recorded before first use. Start with CWC hourly telemetry and the existing ISD replay.
5. **AI role:** AI explains and proposes corrections, stored as proposals. Only what the reviewer accepts becomes a label or a stored correction. Raw data is never overwritten; unreviewed AI output is never treated as truth.
6. **Station to model:** map stations to RF25 cells and aggregate, labelled derived; scoring is at cell-day level; the mapping error is stated wherever results appear.
