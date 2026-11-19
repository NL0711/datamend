---
title: What is the evidence schema and the Explainer/MCP contract with the teammate?
labels: [wayfinder:grilling]
status: closed
assignee: NL0711 (claimed 2026-11-19, closed 2026-11-19)
parent: MAP
blocked_by: []   # t01 and t03 closed 2026-11-19
---

## Question

Decide the seam between our platform and the teammate's MCP LLM narrator: the evidence payload attached to each flag (check name, threshold, observed value, window, neighbours used, whether a number is assumed or measured); the `Explainer` interface (input, output: text, contributions, confidence) and the rule-based baseline we ship; what is exposed (REST, MCP tools, or both) and who hosts it; read-only guarantees; how the narrator's output is labelled in the UI so a generated explanation is never shown as a measured value. Include a short agreement the teammate can build against.

Added 2026-11-19 (from the ML training session's design): the optional score provider (trained layer, see the closed ticket on validation checks) may return per-fault-type scores (for example scale, drift, zeroed) and an ensemble-disagreement value. Decide whether the evidence payload carries them, so the narrator can say which component drove a flag; they exist only when a trained model has run, never invented by the baseline.

## Resolution (2026-11-19, confirmed by the owner)

Settled with the owner (Q1-Q8, all as recommended). Vocabulary is in `CONTEXT.md` (Evidence, Explanation, Narrator). Builds on the closed tickets on checks, input contract, results and the MCP research.

1. **Evidence per fired check.** Fields: `check`, `layer`, `profile`; `observed` (value, unit); `threshold` (value and why, for example "design choice, uncalibrated"); `window` (the readings or days looked at, each with its `row_ref`, capped at the last 24 readings or 14 days, with a link to the rest); `neighbours` (station ids, distances, their values) when used; `time_basis`; `reason` (one plain sentence). Every number carries a `basis` tag: `measured`, `assumed` (for example mm units on the live feed) or `derived`, so an assumption is never presented as a measurement.
2. **Explainer interface.** `explain(flag, evidence) -> Explanation { text, contributions[], model_id, generated: true }`. The platform ships a rule-based baseline that fills a template from the evidence. The narrator is a second implementation of the same interface. The platform computes no confidence for an explanation; the narrator may add its own, labelled as its own. Narrator output is NOT IMPLEMENTED until the teammate delivers.
3. **Exposure.** Option A: read-only REST endpoints plus a versioned JSON Schema and examples are the contract; the teammate hosts the MCP layer as a server wrapping them. The platform does not host MCP in v1 (NOT IMPLEMENTED; FastAPI could mount it at `/mcp` later). This avoids the open transport, token and Render facts until the teammate answers them.
4. **Trained-model evidence.** When a score provider ran, evidence gets a `provider` block: per-fault-type scores, ensemble disagreement, `calibrated` true or false, `label_tier: synthetic`. Without a provider the block is absent; the baseline never invents it.
5. **Storage and labelling of explanations.** A separate `explanations` table linked to (run, `row_ref`, fired check): `text`, `generator` (`baseline-rules` or `mcp-narrator`), `model_id`, `created_at`, `generated: true`. The UI always shows the measured evidence beside any explanation and puts an "AI-generated" badge on the narrator's text. The narrator can never change a verdict, score or evidence.
6. **Requesting an explanation.** Option A for v1: the UI's "Explain" button calls the platform, which calls a configurable `NARRATOR_URL` with the evidence (one request and response with a fixed schema) and stores the reply. If `NARRATOR_URL` is unset the UI says "AI narrator not connected" and shows the baseline. The narrator may use MCP internally. A pull model (the narrator reads evidence through our REST endpoints and posts back) can be added later. This request and response shape is the interface the teammate must confirm.
7. **Read-only and auth.** Evidence endpoints are GET-only; the only write is storing an explanation. One static bearer token per environment for the narrator, rate-limited. Evidence responses are capped at 64 KB with a `next` link for more. These numbers are design choices to confirm with the teammate.
8. **Versioning.** `docs/contracts/evidence-v1.schema.json` with examples; additive changes only within v1; a breaking change becomes v2 with both served during a transition.
9. **Facts only the teammate can supply (from the research ticket), to confirm before building:** their client's MCP revision and transport, whether a static bearer token is accepted, the real payload limits, and Render hosting behaviour.
