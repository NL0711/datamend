---
title: How do AI proposals, reviewer decisions, corrections and labels relate?
labels: [wayfinder:grilling]
status: open
assignee:
parent: MAP
blocked_by: [t01-storage-schema]
---

## Question

Define the data model and rules for the reviewer loop: what an AI proposal contains and where it is stored (separately, marked generated); what an accepted correction is (the original value is kept, the corrected one stored beside it with who, when and why); how a reviewer decision becomes a label with its tier (real reviewer, synthetic, simulated, never pooled); the random audit sample of unflagged data and its weighting so the model does not only learn to agree with itself; how "needs follow-up" and "unsure" are treated; and what the review screen must show for model-derived flags.
