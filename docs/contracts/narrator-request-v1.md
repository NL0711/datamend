# Narrator request and response, version 1 (PROPOSAL, awaiting the AI team's confirmation)

Status: **proposed by the platform side; NOT confirmed by the AI implementation team.** Nothing on the narrator side is built or assumed to exist. Until `NARRATOR_URL` is set the platform says "AI narrator not connected" and shows the rule-based baseline.

The narrator may use MCP internally. The platform does not host MCP in v1 (NOT IMPLEMENTED). The narrator can never change a verdict, score or evidence; its text is stored separately and always shown as AI-generated beside the measured evidence.

## Request (platform to narrator)

`POST {NARRATOR_URL}` with `Content-Type: application/json` and, if `NARRATOR_TOKEN` is set, `Authorization: Bearer <token>`. Body at most 64 KB.

```json
{
  "schema": "narrator-request-v1",
  "kind": "explain",
  "evidence": { "...": "one evidence-v1 payload (docs/contracts/evidence-v1.schema.json)" },
  "question": "optional free text from a user (chat); absent for a plain explanation",
  "context": { "run_headline": { "...": "optional: the run's measured headline numbers" } }
}
```

`kind` is `explain` (a button press) or `chat` (a user question). In a chat the evidence is the selected row's, or absent when the user asked about the run in general (then `context.run_headline` is present).

## Response (narrator to platform), HTTP 200

```json
{
  "text": "plain text, at most 4000 characters, no markup is rendered",
  "contributions": [{ "check": "counter_jump", "note": "why this check mattered" }],
  "model_id": "the narrator's own model or version string",
  "confidence": null
}
```

`confidence` is optional and, if present, is the narrator's own number; the platform shows it labelled as the narrator's and computes none of its own.

## What the platform does with it

- stores the reply in the `explanations` table (`generator: mcp-narrator`, `generated: true`, plus the question for a chat);
- renders `text` as plain text with an "AI-generated" badge, never as HTML;
- on a timeout (default 20 s), a non-200 status or a body that does not match this shape, stores nothing and tells the user the narrator did not answer.

## Facts only the AI team can supply (to confirm before building the other side)

1. The MCP client revision and transport their narrator uses.
2. Whether a static bearer token is acceptable.
3. Their real payload limits (the 64 KB cap and 4000-character reply are our design choices).
4. How they host it (a free Render tier sleeps, so a first request may be slow).
