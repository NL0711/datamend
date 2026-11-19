---
title: What does an MCP LLM narrator need from the platform, and how is it exposed?
labels: [wayfinder:research]
status: closed
assignee: research subagent (2026-11-19)
parent: MAP
blocked_by: []
---

## Question

Facts needed before the evidence contract can be designed: how does a Model Context Protocol (MCP) based LLM narrator consume a data platform? Establish from the MCP specification and official docs: server versus client roles (does the narrator host an MCP server that calls our REST API, or does our platform host one exposing tools/resources?); how tools, resources and prompts are described (JSON schemas); transports (stdio, streamable HTTP) and what that implies for a Render-hosted backend; what an explanation request typically needs as input (the flagged reading, its surrounding window, thresholds, neighbours) and how large that may be; auth and read-only expectations. Capture findings as a Markdown file with sources; no recommendations about our design.

## Resolution (2026-11-19)

Findings are on the local branch `research/mcp-narrator-needs` (commit 15ef875, file `docs/research/mcp-narrator-needs.md`, 105 lines, every claim marked read or not verified; branch not pushed, throwaway). Facts the contract ticket depends on:

- A platform that exposes data to an LLM app is the MCP **server** side (tools, resources, prompts); the LLM app holds the client. Which side the teammate's narrator is, is not in the spec.
- Tools carry a JSON Schema `inputSchema`, optional `outputSchema`, `structuredContent` results and `readOnlyHint`/`destructiveHint` annotations (hints are untrusted). Resources are addressed by URI or URI template.
- Transports: stdio is a local subprocess (not remotely hostable); Streamable HTTP is one POST endpoint and can mount into FastAPI. The latest spec revision (2026-07-28) is stateless and breaks from earlier ones.
- MCP defines no schema for a flagged reading, window, thresholds or neighbours, and no normative size limit.
- Auth is optional (OAuth 2.1 on HTTP); no read-only mode is mandated.

Open facts only the teammate can supply: client spec revision and transport, whether a static bearer token is accepted, effective payload limits, behaviour on Render hosting (not researched).
