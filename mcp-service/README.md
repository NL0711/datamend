# DataMend MCP service

Model Context Protocol (MCP) for DataMend. Two parts, both **outside** `backend/` (they import nothing from it and talk to the platform only through its REST API):

1. **MCP server** (`python -m datamend_mcp serve`): exposes the platform's validation results to any MCP client as 12 **read-only** tools, 2 resources and 2 prompts.
2. **AI narrator** (`python -m datamend_mcp narrator`): the service that the platform's `NARRATOR_URL` seam was waiting for (`docs/contracts/narrator-request-v1.md`). It is an MCP *client* of the server above.

Python 3.10+, **standard library only**: nothing to install. Full write-up: [`docs/mcp/ANSHU_BRANCH_DOCUMENTATION.md`](../docs/mcp/ANSHU_BRANCH_DOCUMENTATION.md).

```
 dashboard "Explain" / "Ask the AI"            any MCP client (Claude Desktop, Inspector, an IDE)
          |                                                  |
   DataMend backend  --POST NARRATOR_URL-->  narrator  --MCP-->  MCP server  --GET /api/...-->  DataMend backend
   (unchanged)          narrator-request-v1    (this)    stdio|HTTP   (this, read-only)              (unchanged)
```

## Quick start

```powershell
# 1. platform running as usual (python -m uvicorn backend.app.main:app --port 8000), then in another terminal:
cd mcp-service
copy .env.example .env                      # or set the variables in your shell
$env:DATAMEND_READ_TOKEN = "<the platform's EVIDENCE_API_TOKEN>"   # preferred: read-only. Or DATAMEND_ADMIN_TOKEN, or DATAMEND_ADMIN_EMAIL + DATAMEND_ADMIN_PASSWORD (admin: wider than needed)
python -m datamend_mcp tools                # list the tools
python examples/demo_session.py             # a client session against the server (needs the platform and a run)
python -m datamend_mcp narrator             # start the narrator on http://127.0.0.1:8790/narrate
```

Connect the platform to the narrator (in the platform's `.env`, then restart it):

```
NARRATOR_URL="http://127.0.0.1:8790/narrate"
NARRATOR_TOKEN="<same value as NARRATOR_BEARER_TOKEN of the narrator>"
```

Dashboard: open a run, select a flagged row and press **Explain (AI)** (the button appears once the narrator is connected), or use the **Ask the AI** chat. Setting the URL from the dashboard's Settings page instead needs `NARRATOR_ALLOW_PRIVATE=true` on the platform for a localhost address.

With Docker: `docker compose -f docker-compose.yml -f docker-compose.mcp.yml up --build` (see the header of that file; not run where this was written).

## The two narrator modes

| | Grounded (default, no key) | LLM (`ANTHROPIC_API_KEY` set) |
|---|---|---|
| `explain` | text composed from the evidence **plus** the row's neighbours and reviews fetched through MCP | a model writes it and may call the MCP tools (at most `NARRATOR_MAX_TOOL_STEPS`) |
| `chat` | answers only: not-run list, headline numbers, flag patterns, the selected row; anything else gets HTTP 501 (the platform shows "the narrator did not answer") | free-form, grounded by tool results |
| `model_id` | `datamend-mcp-grounded-v1` | `datamend-mcp-narrator/<model>` |

`GET /health` shows the mode. **LLM mode sends evidence and tool results to a third party (Anthropic).** Do not enable it for data you may not redistribute (the NOAA ISD replay, WMO Resolution 40; CWC derived data, licence unconfirmed).

## Tools (all read-only; each issues GET requests only)

`list_runs`, `get_run_summary`, `list_flagged_rows`, `get_row_evidence`, `get_evidence_v1`, `get_row_context`, `summarize_flag_patterns`, `get_overview`, `get_station_cycle`, `get_review_summary`, `get_row_reviews`, `locate_place`.
Resources: `datamend://guidelines/narration`, `datamend://contracts/evidence-v1`. Prompts: `explain_flag`, `triage_run`.

## Security controls (what each one is for)

| Threat (seminar) | Control | Where |
|---|---|---|
| Over-broad access | no write tool exists; server refuses to start if a tool is not `readOnlyHint`; only `/api/` GETs | `tools.py`, `client.py`, `security.assert_read_only` |
| Rug pull / tool squatting | tool definitions hashed and pinned in `tool_manifest.lock.json`; server and narrator client refuse a changed, missing or extra tool | `security.verify_manifest`, `mcp_client.vet_tools` |
| Tool poisoning | descriptions scanned for instruction-like text; poisoned tools dropped | `security.scan_definition` |
| Prompt / retrieval injection | every string from an uploaded file is cleaned, capped and instruction-like phrases replaced and reported in `security_flags`; results carry a "this is data" notice; narrator wraps input in `<untrusted_*>` | `security.sanitize_value`, `agent.py` |
| Authentication | constant-time bearer token (HTTP refuses to start without one), Origin allow-list | `transports.py` |
| Abuse / accountability | rate limit, 48 KB result cap, 1 MB body cap, audit log (`data/mcp_audit.jsonl`, secrets redacted) | `security.py` |

If you change a tool on purpose, regenerate the lock and commit it: `python -m datamend_mcp manifest --write` (check: `--check`).

## Tests

```powershell
cd mcp-service
python -m unittest discover -s tests -t .     # 69 tests, about 20 s; pytest works too
```

They run against `tests/fake_datamend.py` (same paths and JSON shapes as `backend/app/api/validation.py`) and `tests/fake_anthropic.py` (the Messages API shapes). One test (`PlatformContractTests`) runs the platform's own `NarratorExplainer` against the narrator and is skipped unless the backend's dependencies are installed.

## What is not done or not verified

- Not run against the real backend, the official MCP SDK, Claude Desktop or the MCP Inspector, nor the live Anthropic API, nor Docker (no network or daemon where this was written). Verify with `npx @modelcontextprotocol/inspector python -m datamend_mcp serve` and the platform contract test.
- The MCP protocol layer is a small implementation of the spec (tools, resources, prompts; stdio and request/response HTTP). Not offered: server-sent streams, sessions, sampling, resource subscriptions, OAuth.
- The injection filter is pattern based and can be bypassed; it removes the cheap routes and records the rest. It is not a guarantee against a model following hostile text.
- No accuracy or quality of the explanations is claimed; LLM mode has not been evaluated.
