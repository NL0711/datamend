---
title: Destination and scope (chart-time decisions)
labels: [wayfinder:grilling]
status: closed
parent: MAP
blocked_by: []
---

## Question

What does this map find its way to, and what is the platform's scope?

## Resolution (2026-11-19, user answers to the chart-time grilling)

1. **Destination:** a locked spec of the platform (scope, architecture, vocabulary, slice list), not the build.
2. **Core job:** take a rainfall time series (file upload or the live gauge feed), run layered validation, return per-reading flags with reasons plus a run-level quality report. Gauge-health trends, correction and alerts are later and out of scope.
3. **Output:** per reading a verdict (`OK / SUSPECT / UNCERTAIN / NO_DATA`, as in the live scorer), the checks that fired, a severity and a structured evidence payload; per run counts by check, completeness, a quality grade, and an export (JSON and CSV first).
4. **Explainability boundary:** the teammate builds an MCP-based LLM narrator for AI explainability and nothing else. We define the Explainer interface and the evidence schema, and ship a rule-based baseline.
5. **Legacy app:** remove all temperature, pressure and humidity code (rainfall only); it is a slice in the spec, after the new platform shell exists.
6. **Justification:** validation-quality metrics (precision, recall, false-alarm rate) on synthetic faults, labelled synthetic, plus a live demo on the gauge feed. UK real labels stay in the separate MLOps phase.
