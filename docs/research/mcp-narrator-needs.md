# What an MCP LLM narrator needs from a data platform, and how it is exposed (primary-source facts, 2026-11-19)

Question (ticket t03): how does a Model Context Protocol (MCP) based LLM narrator consume a data platform? Roles, how tools/resources/prompts are described, transports, typical input and size, auth and read-only expectations.

Scope: facts only, no design recommendation. Every claim is marked **[read]** (read directly on the cited official page in this session) or **[not verified]** (stated by the page only indirectly, inferred, or not found). Sources are the official MCP specification, official MCP docs and the official Python SDK docs (all on `modelcontextprotocol.io` / `py.sdk.modelcontextprotocol.io`).

**Revision caveat [read].** The "latest" specification URL resolved to revision **2026-07-28**. That revision is a breaking change from 2025-11-25 and earlier (stateless, no `initialize` handshake, no sessions, no GET stream). SDKs "adopt new protocol revisions on their own schedules" ([SDK page](https://modelcontextprotocol.io/docs/2026-07-28/sdk)), so a narrator built with an SDK may speak an older revision. Facts below are for 2026-07-28 unless stated; older-revision behaviour is only as described in this revision's backward-compatibility notes.

## 1. Server versus client roles

| Claim | Status | Source |
|---|---|---|
| MCP has three participants: **host** (the LLM application that initiates connections), **client** (a connector inside the host, one per server, 1:1), **server** (provides context and capabilities). | [read] | [Spec overview](https://modelcontextprotocol.io/specification/latest), [Architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture) |
| The host "coordinates AI/LLM integration"; the LLM lives on the host side, not in the server. | [read] | [Architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture) |
| Servers expose three primitives: **tools** (functions for the model to execute), **resources** (context and data), **prompts** (templated messages). The only client feature in this revision is elicitation. | [read] | [Spec overview](https://modelcontextprotocol.io/specification/latest), [Architecture overview](https://modelcontextprotocol.io/docs/learn/architecture) |
| Design principle: servers "should not be able to read the whole conversation"; the full conversation stays with the host. | [read] | [Architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture) |
| MCP "does not dictate how AI applications use LLMs or manage the provided context". | [read] | [Architecture overview](https://modelcontextprotocol.io/docs/learn/architecture) |
| Direction of calls: clients send requests, servers respond. In 2026-07-28 servers do not initiate JSON-RPC requests; server-needs-input flows (elicitation) are returned inside an `InputRequiredResult` and the client retries (Multi Round-Trip Requests). Sampling (server asks the client's LLM) and roots are deprecated in this revision; the docs say the protocol "does not define a replacement for requesting completions through the client". | [read] | [Architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture), [Architecture overview](https://modelcontextprotocol.io/docs/learn/architecture), [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) |
| Therefore, in MCP terms, a data platform that wants an LLM application to read its data is the **server** side (it exposes tools/resources); the LLM application (the narrator's host) holds the **client**. The spec does not say a server may only wrap a REST API, nor forbid it: a server "can be local processes or remote services". | Server-side exposure is [read]; "wrapping a REST API" as a pattern is [not verified] in the spec (no page prescribes it) | [Architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture) |
| Which party in the teammate's narrator is host/client is a fact about their code, not about the spec. | [not verified] (not in any source read) | n/a |

## 2. How tools, resources and prompts are described

### Tools
- Declared via the `tools` capability; discovered with `tools/list` (paginated, cacheable), invoked with `tools/call`. [read] ([Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools))
- A `Tool` has: `name`, optional `title`, `description` (the schema says it can be thought of as a "hint" to the model), `inputSchema`, optional `outputSchema`, optional `annotations`, optional `icons`, `_meta`. [read] ([Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), [Schema reference](https://modelcontextprotocol.io/specification/2026-07-28/schema))
- `inputSchema` is a JSON Schema object with `type: "object"` at the root, default dialect **JSON Schema 2020-12** when no `$schema`; a no-parameter tool should use `{ "type": "object", "additionalProperties": false }`. `outputSchema` is optional JSON Schema 2020-12 for `structuredContent`. [read]
- Tool names: SHOULD be 1-128 chars, ASCII letters, digits, `_`, `-`, `.`, unique within a server. [read]
- Results: unstructured `content` array (text, image, audio, `resource_link`, embedded `resource`) and/or `structuredContent` (any JSON value conforming to `outputSchema`). A tool returning structured content SHOULD also return the serialized JSON as a text block. If an `outputSchema` is given, servers MUST conform and clients SHOULD validate. [read]
- Errors: protocol errors (unknown tool, malformed request) as JSON-RPC errors; tool execution errors (API failures, input validation, business logic) as a normal result with `isError: true`, which clients SHOULD pass to the model to allow self-correction. [read]
- Tools are described as **model-controlled**; the spec says there SHOULD be a human in the loop able to deny invocations. [read]
- Servers MUST validate tool inputs, implement access controls, rate-limit and sanitize outputs. [read]
- Stateless design note: the protocol has no session; servers needing state across calls should return explicit handles that the model passes back (non-normative). [read]

### Resources
- Declared via `resources` capability; `resources/list`, `resources/read`, and URI-template parameterised `resources/templates/list` (RFC 6570). [read] ([Resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources))
- A resource has `uri`, `name`, optional `title`, `description`, `mimeType`, `size`; contents are `text` or base64 `blob`; optional annotations `audience`, `priority` (0.0-1.0), `lastModified`. [read]
- Resources are **application-driven**: the host decides how to include them (user selection, search, or automatic inclusion by heuristics or model choice); the protocol mandates no interaction model. [read]
- A missing resource MUST return JSON-RPC error `-32602`. Servers MUST validate URIs. [read]
- A tool may return `resource_link` items that are not guaranteed to appear in `resources/list`. [read]

### Prompts
- Declared via `prompts` capability; `prompts/list`, `prompts/get` with named arguments (`name`, `description`, `required`). Returns `messages` with `role` (`user` or `assistant`) and content (text, image, audio, resource link, embedded resource). [read] ([Prompts](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts))
- Prompts are **user-controlled** (the user explicitly selects them, e.g. as slash commands); "who decides when the prompt is used, not who authors its content". [read]

### Cross-cutting
- All three list operations may vary by the authorization presented on the request, but MUST NOT vary per connection. Lists support pagination and carry `ttlMs` and `cacheScope` caching hints. [read]
- Discovery: `server/discover` returns supported versions and capabilities and is optional; every request carries `_meta` with protocol version and client capabilities. [read] ([Architecture overview](https://modelcontextprotocol.io/docs/learn/architecture))

## 3. Transports and what they imply for a hosted backend

| Claim | Status | Source |
|---|---|---|
| Two standard transports: **stdio** and **Streamable HTTP**; custom transports are allowed if they preserve the JSON-RPC format and per-request metadata model. The deprecated HTTP+SSE transport (2024-11-05) should not be adopted by new implementations. | [read] | [Transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports), [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) |
| **stdio**: the client launches the server as a **subprocess**; newline-delimited JSON-RPC on stdin/stdout; stderr may carry logs; server MUST NOT write non-MCP data to stdout. Local servers "typically serve a single MCP client". | [read] | [stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio), [Architecture overview](https://modelcontextprotocol.io/docs/learn/architecture) |
| **Streamable HTTP**: the server is an independent process serving many clients behind one HTTP endpoint that accepts POST (e.g. `https://example.com/mcp`). Each JSON-RPC message is a separate POST; the reply is either `application/json` or a request-scoped SSE stream. Clients MUST send `Accept: application/json, text/event-stream`. | [read] | [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) |
| 2026-07-28 removed the GET stream endpoint and protocol-level sessions (`Mcp-Session-Id`); streams are not resumable (`Last-Event-ID` unsupported). A server supporting only this revision should answer GET/DELETE with 405 and ignore `Mcp-Session-Id`. | [read] | [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) |
| Required request headers on POST: `MCP-Protocol-Version`, `Mcp-Method` (and `Mcp-Name` for `tools/call`, `resources/read`, `prompts/get`); servers MUST reject header/body mismatch with 400 and error `-32020`. | [read] | same |
| Servers MUST validate the `Origin` header (403 if invalid); locally SHOULD bind to 127.0.0.1; SHOULD authenticate all connections. Servers SHOULD send `X-Accel-Buffering: no` on SSE responses so reverse proxies do not buffer. | [read] | same |
| Long-lived change notifications use a `subscriptions/listen` request whose response is an open SSE stream; servers are encouraged to emit keep-alive comment lines. | [read] | same |
| A stdio server must be launched by the client on the client's machine; a stdio server therefore cannot be "hosted" and reached remotely without a separate wrapper. This is an inference from the stdio definition. | [not verified] (inference; no page states it as such) | [stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio) |
| Render-specific behaviour (free-tier sleep, request timeouts, SSE idle limits, proxy buffering) was **not** researched; it is outside the MCP sources. | [not verified] | n/a |
| Python SDK deployment guidance: with 2026-07-28 clients "no session ID", so any worker can serve any request and no sticky sessions are needed; older clients (2025-11-25 and earlier) keep sessions in one worker's memory unless `stateless_http=True` (which disables elicitation/sampling back-channel and resumability). Behind a real hostname the default Host/Origin allowlist rejects requests (421/403) until `transport_security=` is configured. Behind a TLS-terminating proxy run uvicorn with `--proxy-headers`. | [read] | [Python SDK: Deploy](https://py.sdk.modelcontextprotocol.io/run/deploy/index.md) |
| A Python SDK MCP server can be mounted into an existing ASGI app (Starlette/FastAPI): `mcp.streamable_http_app()`, default path `/mcp`, and the host app must enter `mcp.session_manager.run()` in its lifespan. | [read] | [Python SDK: ASGI](https://py.sdk.modelcontextprotocol.io/run/asgi/index.md) |

## 4. What an explanation request needs as input, and how large

- The MCP specification defines **no** schema for "explanation requests", for a flagged-reading payload, for window sizes, thresholds or neighbours. What a narrator needs is defined by the narrator's own prompt and tool-use logic. **[not verified]** (searched the spec pages for tools, resources, prompts and schema; nothing domain-specific exists, as expected for a general protocol).
- What the protocol does provide for carrying such input: tool `arguments` validated by `inputSchema`; tool results as `structuredContent` (+ text) validated by `outputSchema`; resources addressed by URI or URI template (e.g. a per-record parameterised URI); and `resource_link` items inside tool results so the client can fetch bulk data separately. [read]
- Size: I found **no normative maximum size** for tool results, resource contents or text content in the specification pages read (tools, resources, prompts, and the schema reference, which was read in full across three fetches). The only numeric limits seen were `completion` values (max 100 items) and the tool-name length guidance (SHOULD be 1-128 chars). The effective limit is the host's model context window and the HTTP/proxy limits of the deployment, neither of which the spec defines. [read for "no limit found"; the effective limits themselves are [not verified]]
- Pagination exists for list operations (`cursor` / `nextCursor`), not for the content of a single `tools/call` result. [read] ([Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools))
- Python SDK: the return type annotation of a tool function becomes its `outputSchema`; object-like types (Pydantic models, TypedDicts, dataclasses, dicts) give a schema directly, scalars and lists are wrapped in `{"result": ...}`; returned values are validated against the schema before leaving the server and a mismatch becomes a tool error. [read] ([Python SDK: Structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/index.md))

## 5. Auth and read-only expectations

| Claim | Status | Source |
|---|---|---|
| Authorization is **optional** in MCP. Implementations on HTTP-based transports SHOULD follow the authorization spec; stdio implementations SHOULD NOT and "instead retrieve credentials from the environment". | [read] | [Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) |
| The HTTP authorization model: the MCP server is an OAuth 2.1 **resource server**, the MCP client an OAuth 2.1 client; servers MUST implement OAuth 2.0 Protected Resource Metadata (RFC 9728); clients MUST send RFC 8707 `resource`; tokens go in `Authorization: Bearer` on every HTTP request and MUST NOT be in the query string; servers MUST validate tokens were issued for them as audience; invalid/expired tokens get 401, insufficient scope 403 with `WWW-Authenticate`. | [read] | same |
| The architecture docs also state Streamable HTTP "supports standard HTTP authentication methods including bearer tokens, API keys, and custom headers" and "MCP recommends using OAuth". Whether a simple static bearer/API key is conformant to the authorization page without the OAuth discovery steps is not stated by the pages read. | Quote [read]; conformance question [not verified] | [Architecture overview](https://modelcontextprotocol.io/docs/learn/architecture) |
| Streamable HTTP servers SHOULD authenticate all connections; MUST validate `Origin`. | [read] | [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) |
| There is **no mandatory read-only mode** in the protocol. The tool schema offers an optional hint `annotations.readOnlyHint` ("If true, the tool does not modify its environment", default false), plus `destructiveHint` (default true), `idempotentHint` (default false), `openWorldHint` (default true). All are only **hints**: "Clients should never make tool use decisions based on ToolAnnotations received from untrusted servers", and the Tools page says clients MUST treat annotations as untrusted unless from trusted servers. Resources have no write concept in the protocol (`resources/read` only). | [read] | [Schema reference](https://modelcontextprotocol.io/specification/2026-07-28/schema), [Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), [Resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources) |
| Security principles: user consent before tool invocation, hosts must not send resource data elsewhere without consent; tool descriptions are untrusted unless from a trusted server; servers MUST validate inputs, rate limit, sanitize outputs. | [read] | [Spec overview](https://modelcontextprotocol.io/specification/latest), [Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) |
| Tool-result content is passed to a model by the client; the spec says clients SHOULD validate tool results before passing them to the LLM (prompt-injection-relevant). | [read] | [Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) |

## 6. SDKs (official)

- Tier 1 official SDKs: TypeScript, Python, C#, Go, Rust, Ruby; Tier 2 Java; Tier 3 Swift, PHP, Kotlin. [read] ([SDKs](https://modelcontextprotocol.io/docs/2026-07-28/sdk))
- Python SDK: `pip install "mcp[cli]"`, requires Python 3.11+, server class `MCPServer`, tools registered with `@mcp.tool()` and input schemas generated from type hints; `uv run mcp dev server.py` starts the MCP Inspector; transports stdio, Streamable HTTP and SSE. [read] ([Python SDK home](https://py.sdk.modelcontextprotocol.io/))
- Which SDK and revision the teammate's narrator uses was not available to me. [not verified]

## 7. Open points not answerable from these sources

1. Which revision (2026-07-28 vs 2025-11-25 or earlier) the narrator's client speaks, and whether it supports Streamable HTTP or only stdio.
2. Whether a static bearer token satisfies the narrator's client when talking to a remote server (client behaviour; not in the spec text read).
3. Effective payload limits (model context window, host tool-result truncation, hosting proxy limits).
4. Render hosting behaviour for POST/SSE (outside MCP sources).

## Sources read

- Specification (latest = 2026-07-28): [overview](https://modelcontextprotocol.io/specification/latest), [architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture), [transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports), [stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio), [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http), [tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), [resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources), [prompts](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts), [authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization), [schema reference](https://modelcontextprotocol.io/specification/2026-07-28/schema).
- Official docs: [architecture overview](https://modelcontextprotocol.io/docs/learn/architecture), [SDK list](https://modelcontextprotocol.io/docs/2026-07-28/sdk).
- Official Python SDK docs: [home](https://py.sdk.modelcontextprotocol.io/), [ASGI](https://py.sdk.modelcontextprotocol.io/run/asgi/index.md), [deploy](https://py.sdk.modelcontextprotocol.io/run/deploy/index.md), [structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/index.md).

Method note: pages were fetched through a summarising fetch tool, so quoted phrases were relayed by that tool; the page contents for the specification pages were returned in full text and the schema reference was read in three parts. Pages for the TypeScript SDK, the `2025-11-25` revision text, the security best-practices page and the Python SDK authorization page were not read.
