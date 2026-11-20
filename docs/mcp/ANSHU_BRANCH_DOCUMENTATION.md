# Anshu branch: MCP integration for DataMend

Author: Anshu Jadhav (seminar: *Model Context Protocol (MCP) for AI Agents*, guide: Jagruti Nagaonkar)
Scope: one new top-level folder `mcp-service/`, plus new docs and two new deploy files. **No existing file is modified**, so merging into `main` cannot conflict with the other contributors' work.

## 1. The problem this solves in DataMend

`README.md` and `AGENTS.md` describe an *AI narrator* "MCP-based, built by the AI implementation team" behind one interface (`NarratorExplainer` in `backend/app/validation/explain.py`). The platform side existed (the request/response contract `docs/contracts/narrator-request-v1.md`, the `explanations` table, the "Explain (AI)" button, the "Ask the AI" chat) but **the narrator itself was NOT IMPLEMENTED**: with `NARRATOR_URL` unset the chat answered "AI narrator not connected". `TODO.md` also lists "MCP hosting in the platform" as not built, and four facts were waiting on the AI team (MCP client revision and transport, token auth, payload limits, hosting).

This branch builds that other side, using what the seminar covered: a standard way for an AI application to reach external tools and data (MCP), with the security problems of that approach handled explicitly.

## 2. What was added

```
mcp-service/                         the whole contribution (standard library only, Python 3.10+)
  datamend_mcp/
    config.py                        settings from environment variables only
    client.py                        GET-only client of the DataMend REST API (token or email+password, re-login on expiry)
    tools.py                         12 read-only tools, 2 resources, 2 prompts, strict argument validation
    protocol.py                      MCP server core: JSON-RPC 2.0, initialize, tools/resources/prompts
    transports.py                    stdio transport and Streamable-HTTP (request/response) transport
    security.py                      sanitiser, tool-definition pinning, bearer check, rate limit, audit log
    mcp_client.py                    minimal MCP client (stdio child process or HTTP) + tool vetting
    narrator/agent.py                the narrator: grounded mode and LLM mode
    narrator/llm.py                  Anthropic Messages API call (urllib)
    narrator/app.py                  HTTP service: POST /narrate, GET /health
    __main__.py                      CLI: serve | narrator | manifest | tools
  tool_manifest.lock.json            pinned SHA-256 of every tool definition
  tests/                             69 tests + a fake DataMend API + a fake Anthropic API
  examples/                          demo client session, Claude Desktop config
  README.md, requirements.txt (nothing to install), .env.example, .gitignore
docs/mcp/ANSHU_BRANCH_DOCUMENTATION.md   this file
docs/mcp/GIT_PUSH_GUIDE.md               replace the anshu branch and push
docs/contracts/narrator-confirmation-v1.md   answers to the four open questions of narrator-request-v1
Dockerfile.mcp, docker-compose.mcp.yml   optional container deployment (override file; the existing compose file is untouched)
```

## 3. How it fits with `main`

```
 Browser (React dashboard)                      Anyone with an MCP client (Claude Desktop, MCP Inspector, IDE agent)
        |                                                         |
        v                                                         | MCP over stdio or HTTP (bearer token)
 DataMend backend (FastAPI)  ---POST NARRATOR_URL--->  NARRATOR  ---MCP--->  MCP SERVER  ---GET /api/validation/...--+
   validation, evidence, runs,   narrator-request-v1    (agent.py)  stdio     (protocol.py,                          |
   explanations table                                    grounded or LLM      read-only tools)                       |
        ^                                                                                                            |
        +------------------------------------------------------------------------------------------------------------+
```

* The platform is **unchanged**. It already POSTs to `NARRATOR_URL`; now something answers. You switch it on by setting two environment variables (`NARRATOR_URL`, `NARRATOR_TOKEN`).
* The narrator receives one `evidence-v1` payload (or a question) and returns `{text, contributions, model_id, confidence}`. The platform stores that in `explanations` with `generator: mcp-narrator`, `generated: true` and shows it with an "AI-generated" badge. **The narrator can never change a verdict, score or evidence** (rule 7 of `AGENTS.md`): it returns text only, and every tool it can call is read-only.
* The MCP server reads the platform through the same REST API the dashboard uses, so it sees exactly what a signed-in admin sees. It reuses the platform's sign-in (`ADMIN_TOKEN` as `X-Admin-Token`, or the admin email and password).

### 3.1 Flow of "Explain (AI)" on a flagged row

1. Dashboard calls `POST /api/validation/runs/{run}/rows/{row}/explain {generator: "narrator"}`.
2. The platform builds `evidence-v1` for each fired check and POSTs `narrator-request-v1` to `NARRATOR_URL` (bearer token, 64 KB cap, 20 s timeout, 30 calls/min: all existing behaviour).
3. The narrator validates the request, sanitises every string in it, then:
   * **grounded mode**: calls MCP tools `get_row_context` and `get_row_reviews` and composes the text from the evidence plus those numbers (how many neighbouring readings at the same station were also flagged, what a human reviewer recorded);
   * **LLM mode**: sends evidence and the tool definitions to the model, which may call tools in a bounded loop before writing the answer.
4. The reply is cut to 4000 characters, wrapped in the contract's shape, and returned. If anything fails the narrator answers a non-200 status; the platform then stores nothing and tells the user the narrator did not answer (the contract's own rule).

### 3.2 Flow of "Ask the AI" (chat)

Same, with `kind: "chat"`. Run-level questions arrive with `context.run_headline` and `context.run_not_run`. In grounded mode the narrator answers only what those numbers or an MCP tool answer exactly (not-run list, headline numbers, flag patterns, the selected row); any other question gets HTTP 501 rather than an invented answer, which is the repo's "do not fake functionality" rule. With `ANTHROPIC_API_KEY` set the model answers freely, grounded by tool results.

## 4. MCP concepts, as implemented

| Seminar slide | In this code |
|---|---|
| Host (AI application running the agent) | the narrator process, or Claude Desktop / an IDE when a person connects their own client |
| Client (maintains the MCP connection) | `mcp_client.py` (`StdioMcpClient`, `HttpMcpClient`) |
| Server (exposes tools/resources) | `protocol.py` + `transports.py`, started by `python -m datamend_mcp serve` |
| Tools (executable functions) | `tools.py`: 12 read-only tools, each with a JSON Schema |
| Resources (external data/context) | `datamend://guidelines/narration`, `datamend://contracts/evidence-v1` |
| Prompts (reusable templates) | `explain_flag`, `triage_run` |
| Workflow: Connect, Discover, Select, Invoke, Execute, Return | `initialize`, `tools/list`, the model's tool choice, `tools/call`, handler issuing a GET, result returned as text + `structuredContent` |
| "Build the integration once, expose it through MCP" | the same 12 tools serve the narrator, Claude Desktop and any other client unchanged |

## 5. Tools

| Tool | What it returns | Platform endpoint |
|---|---|---|
| `list_runs` | recent runs with headline numbers | `GET /api/validation/runs` |
| `get_run_summary` | headline, checks that did not run (with reasons), input issue counts | `GET /runs/{id}` (trimmed: the large `report` is dropped) |
| `list_flagged_rows` | page of rows (max 50), filter by verdict, check, station | `GET /runs/{id}/rows` |
| `get_row_evidence` | original row, issues, each fired check with reason and evidence | `GET /runs/{id}/rows/{row}` |
| `get_evidence_v1` | the `evidence-v1` payloads the narrator explains | `GET .../evidence` |
| `get_row_context` | the same station's rows before and after | `GET .../context` |
| `summarize_flag_patterns` | counts by verdict, severity, check, station; top stations and station/check pairs. **Computed here by counting**, no model | pages of `GET /runs/{id}/rows` |
| `get_overview`, `get_station_cycle`, `get_review_summary`, `get_row_reviews` | cross-run overview, per-station check/flag/audit cycle, review decisions (labelled reviewer opinions, not ground truth) | matching GETs |
| `locate_place` | RF25 cell, land or sea, client region | `GET /api/places/locate` |

Arguments are validated before anything is requested (integers only for ids, bounded page sizes, enums for verdicts, no extra keys), so a model cannot put a path or an unbounded request into a call.

## 6. Security design (threats from the seminar)

| Threat | What was built | Test |
|---|---|---|
| Over-broad access (least privilege) | There is **no write tool**. `assert_read_only` makes the server refuse to start if any tool lacks `readOnlyHint`. The client can only issue GET to `/api/` paths. | `StartupGuardTests`, `test_only_get_requests_reach_the_platform` |
| Rug pull / tool squatting | Each tool's name, description, schema and annotations are hashed into `tool_manifest.lock.json`. The server refuses to start if a definition differs; the narrator's MCP client does the same for a remote server and raises if a tool is changed, extra or missing. | `ManifestTests`, `PinnedToolTests` |
| Tool poisoning | Tool descriptions (and parameter descriptions) are scanned for instruction-like text; poisoned or non-read-only tools are dropped before a model sees them. | `test_poisoned_description_scanned`, `test_vet_tools_drops_poisoned_and_non_read_only` |
| Prompt / retrieval injection | Station ids, notes and reasons come from uploaded files. Every string is stripped of control, zero-width and bidirectional characters, capped, and instruction-like phrases are replaced with a marker and reported in `security_flags`. Tool results carry a notice that strings are data. The narrator wraps its input in `<untrusted_*>` tags and tells the model so. | `test_hostile_station_id_is_neutralised_and_flagged`, `test_hostile_evidence_cannot_reach_the_answer` |
| Authentication flaws | HTTP transport refuses to start without `MCP_BEARER_TOKEN`; constant-time comparison; Origin allow-list (DNS-rebinding guard); the narrator checks its own bearer token (the platform's `NARRATOR_TOKEN`). | `HttpTransportTests`, `test_auth_and_size` |
| Abuse and accountability | Rate limits, result size cap (48 KB), body caps (1 MB / 64 KB), JSON-lines audit log of every tool call with secrets redacted. | `test_rate_limit`, `test_audit_log_written_without_secrets` |
| Runaway agent | At most `NARRATOR_MAX_TOOL_STEPS` tool rounds and an overall 18 s deadline (under the platform's 20 s); unknown tool names are refused. | `test_runaway_tool_loop_is_stopped`, `test_unknown_tool_request_is_refused_to_the_model` |

**Limits.** The sanitiser is pattern based and can be bypassed. It removes the cheap routes; it does not make a language model immune to hostile text. The server reads with the platform's admin credential, so it has the same read access as a signed-in admin; there are no per-user scopes (the platform has one admin account). In LLM mode evidence and tool results are sent to Anthropic, which matters for data you may not redistribute (the NOAA ISD replay under WMO Resolution 40; CWC derived data with an unconfirmed licence).

## 7. Honesty status (same convention as the rest of the repo)

Built and tested here (69 tests, standard library, generated data, local fake servers): the MCP protocol core, both transports, all tools and their argument validation, the DataMend client including sign-in and re-login, every security control above, the narrator in both modes over a real stdio child process (including its restart when the process dies), the narrator HTTP contract.

**Not verified:**
* the real backend (its dependencies could not be installed where this was written). The tests use `tests/fake_datamend.py`, written from the routes and return shapes in `backend/app/api/validation.py`. Run the real stack once before merging.
* `PlatformContractTests` (runs the platform's own `NarratorExplainer` against the narrator) was **skipped**; it runs automatically once `pip install -r requirements.txt` is done at the repo root.
* interoperability with the official MCP SDK, Claude Desktop and the MCP Inspector (the protocol layer is a small implementation of the spec). Check with `npx @modelcontextprotocol/inspector python -m datamend_mcp serve` from `mcp-service/`.
* the live Anthropic API (the tests use a local stand-in with the same message shapes). The model name is configurable (`NARRATOR_LLM_MODEL`, default `claude-sonnet-5-5`).
* Docker image and compose override were not built or run.
* **No claim is made about the quality or accuracy of the explanations**; LLM mode has not been evaluated, and grounded mode is rules plus counts, not a language model.

**Not built:** server-sent streams and sessions on the HTTP transport, MCP sampling and elicitation, resource subscriptions, OAuth, per-user scopes, a dashboard page for the narrator, any write tool (by design).

## 8. Running it

See `mcp-service/README.md` (quick start, environment variables, Docker). In short: start the platform, start `python -m datamend_mcp narrator` in `mcp-service/`, set `NARRATOR_URL=http://127.0.0.1:8790/narrate` and `NARRATOR_TOKEN` in the platform's `.env`, restart the platform, open a flagged row and press **Explain (AI)**.

## 9. For the person merging into `main`

Nothing to resolve: only new files. Optional one-line additions, left out of this branch on purpose so they cannot conflict with other people's edits:

* `TODO.md`, after slice 12: `- [x] 13. (Anshu) MCP: read-only DataMend MCP server and the AI narrator in mcp-service/ (69 tests on fake servers; NOT VERIFIED against the real backend, the official MCP SDK or a live model; see docs/mcp)`.
* `README.md`, "What is in the repo" table: `| mcp-service/ | MCP server (read-only tools over the REST API) and the AI narrator behind NARRATOR_URL. See mcp-service/README.md. |` and change "The narrator itself is NOT IMPLEMENTED here" to point to it.
* `docs/contracts/narrator-request-v1.md`: the status line can now link `narrator-confirmation-v1.md`.

## 10. Possible next steps

A narrator status panel in the dashboard Settings; per-user scopes once the platform has accounts; an MCP-Bench-style evaluation of tool selection on the synthetic Anomaly lab runs (the lab injects known faults, so the narrator's answers could be scored); streaming responses; running the official SDK server side by side to confirm interoperability.
