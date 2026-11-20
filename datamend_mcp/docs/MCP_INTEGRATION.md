# DataMend x Model Context Protocol (MCP) - Integration Documentation

**Contributor:** Anshu Jadhav (Roll No. 10247) - branch `anshu`
**Seminar basis:** *Model Context Protocol (MCP) for AI Agents* (Subject guide: Jagruti Nagaonkar)

---

## 1. What this contribution does (in one paragraph)

DataMend is a Python library that repairs, validates, monitors and diagnoses data
for ML pipelines. Before this contribution, using it required writing Python code.
This package, `datamend_mcp/`, wraps DataMend as an **MCP server**. Any MCP-compatible
AI agent (such as Claude Desktop) can now *discover* DataMend's capabilities and
*call* them in plain English - "check prod.csv, fix it, and tell me if it drifted from
train.csv" - without custom glue code. Because the seminar's main finding was that
**standardisation does not guarantee security**, the server also ships a security
layer: a file sandbox, deny-by-default tool policy, tool-definition pinning, output
sanitisation against prompt injection, and an audit log.

The contribution is **additive**: one new folder, no existing file is modified, so it
cannot conflict with other contributors' work.

---

## 2. How it maps to the seminar

| Seminar topic | Where it appears in this contribution |
|---|---|
| Problem: custom integration per tool | One MCP server replaces hand-written glue for every agent/app |
| Architecture: Host / Client / Server / Tools / Resources / Prompts | `server.py` is the **Server**; 6 **Tools**, 2 **Resources**, 2 **Prompts**; `client_demo.py` is a **Client** |
| 6-step workflow (Connect-Discover-Select-Invoke-Execute-Return) | `client_demo.py` prints each step (see section 5) |
| Tool poisoning, rug pulls | Tool definitions are SHA-256 pinned (`tool_manifest.lock.json`); server and client both refuse on mismatch |
| Prompt / retrieval injection | `sanitize_text()` cleans every string derived from user data before it reaches the LLM |
| Authentication & authorization flaws | Deny-by-default policy, read-only mode, workspace sandbox; HTTP transport documented as localhost-only |
| Fine-grained access control / least privilege (future work) | `policy.json` per-tool permissions + limits |
| Verified tool identity / secure tool definitions (future work) | Hash pinning (a lightweight version of the ETDI idea) |
| Security benchmarking | Security unit tests (traversal, symlink, injection, poisoning detection) |
| Contract-driven MCP (future work) | DataContract tools + typed schemas + structured error contract |
| Performance / evaluation | Per-call timing in the audit log and in the demo client |

---

## 3. What is inside the zip

```
datamend_mcp/
|-- __init__.py              package marker + version
|-- __main__.py              enables:  python -m datamend_mcp
|-- config.py                reads environment variables (workspace, read-only, ...)
|-- policy.json              which tools are allowed + size/row/extension limits
|-- security.py              ALL defences (sandbox, sanitiser, policy, audit, pinning)
|-- adapters.py              the ONLY file that calls the datamend library
|-- tools.py                 tool logic (pure Python) + the @guarded decorator
|-- server.py                MCP server: registers tools/resources/prompts, CLI
|-- client_demo.py           demo MCP client: runs the 6-step workflow end to end
|-- requirements-mcp.txt     extra dependencies (the `mcp` SDK)
|-- README.md                quick start
|-- docs/MCP_INTEGRATION.md  this document
|-- examples/
|   |-- make_sample_data.py  creates messy prod.csv + clean train.csv
|   `-- claude_desktop_config.json   template for connecting Claude Desktop
`-- tests/
    |-- stub_datamend.py     stand-in for datamend (mirrors its documented API)
    |-- test_security.py     security-layer tests
    `-- test_tools.py        tool tests (flow, validation, attacks, audit)
```

Generated at run time (not in the zip, git-ignored): `tool_manifest.lock.json`
(created by `--write-lock`), and the `mcp_workspace/` folder.

### File-by-file

**`adapters.py`** - the translation layer to DataMend. It loads files into pandas, calls
`datamend.repair / DataContract / validate / drift`, and converts the report objects
into small JSON-safe dictionaries (NaN becomes `null`, long lists are capped at 50
items, every string passes through the sanitiser). If your DataMend version names
something differently, this is the only file you edit.

**`security.py`** - the defences:
- `resolve_in_workspace()` - every path is resolved (including symlinks) and must stay
  inside the workspace; `../` traversal, outside absolute paths and null bytes are blocked.
- `safe_name()` - output and contract names may not contain slashes or `..`.
- `Policy` - deny-by-default list of tools; `write` tools can be switched off globally
  with `DATAMEND_MCP_READ_ONLY=1`; limits on file size, rows, columns and file types.
- `sanitize_text()` - strips hidden/zero-width/bidi characters, collapses whitespace,
  truncates, and redacts instruction-like text ("ignore previous instructions", fake
  `</system>` tags, ...). Applied to column names, category values, messages.
- `AuditLog` - JSON-lines record: timestamp, tool, arguments, status, duration. It never
  stores data contents.
- `fingerprint_tools / write_lock / verify_lock` - SHA-256 hash of every tool's name,
  description and input schema; detects changed, added or removed tools.

**`tools.py`** - the actual tools. `@guarded` wraps each one so that every call:
(1) is policy-checked, (2) runs, (3) converts any failure into a structured
`{"ok": false, "error_type": ..., "error": ...}` instead of a stack trace,
(4) is written to the audit log. It has no dependency on the MCP SDK, which is why it
is fully unit-tested.

**`server.py`** - thin FastMCP wrapper. Registers the tools, resources and prompts.
On startup it verifies the tool definitions against the lock file and **refuses to
start** if they differ. Logging goes to stderr because with stdio transport stdout
is the protocol channel.

**`client_demo.py`** - an MCP client that launches the server, discovers its tools,
verifies them against the lock (client-side pinning), runs a scripted workflow and
finally attempts a path-traversal attack to show it is blocked.

---

## 4. What the agent can do

### Tools
| Tool | Mode | What it does |
|---|---|---|
| `datamend_list_workspace` | read | Lists data files and saved contracts the agent may use |
| `datamend_score` | read | MendScore (0-100) + issue counts. Runs repair on an in-memory copy and discards it; nothing is written |
| `datamend_repair` | **write** | Repairs a dataset and writes a **new** file into `outputs/`; original is never modified; refuses to overwrite unless `overwrite=true` |
| `datamend_create_contract` | **write** | Learns a contract from clean training data, saves it under a name |
| `datamend_validate` | read | Validates a dataset against a saved contract; returns violations + severity |
| `datamend_drift` | read | PSI / KS / chi-square / JSD drift between training and production data |

### Resources
- `datamend://contracts/{name}` - JSON of a saved contract
- `datamend://audit/recent` - the 20 most recent tool calls

### Prompts
- `data_health_check(path)` - guided review: score, then repair if below 85
- `drift_investigation(train_path, prod_path)` - guided drift analysis and recommendation

---

## 5. How a request flows (the 6 MCP steps)

User says: *"Check prod.csv and fix it."*

```
 User -> HOST (Claude Desktop) -> MCP CLIENT --stdio--> datamend_mcp SERVER -> datamend -> files
                                                          |
                                      policy -> sandbox -> tool -> sanitise -> audit log
```

1. **Connect** - the client launches `python -m datamend_mcp` and initialises the session.
2. **Discover** - `list_tools` returns the six tools with their descriptions and schemas;
   the client compares them with the pinned lock file.
3. **Select** - the LLM picks `datamend_score`, then `datamend_repair` (in
   `client_demo.py` this is a scripted plan).
4. **Invoke** - the client sends `call_tool(name, arguments)`.
5. **Execute** - the server checks policy, resolves the path inside the sandbox, loads the
   file, calls DataMend, writes the result.
6. **Return** - a sanitised, size-capped JSON result goes back to the agent, and an audit
   entry is written.

---

## 6. Security model

| Threat | Example | Defence | Status |
|---|---|---|---|
| Path traversal / over-privilege | agent asks for `../../etc/passwd` | Workspace sandbox, symlink-safe | Tested |
| Unauthorised actions | agent tries to modify data | Per-tool policy, read-only mode, never overwrite originals | Tested |
| Tool poisoning / rug pull | a collaborator (or supply-chain attacker) edits a tool description to add hidden instructions | Hash pinning; server refuses to start; client verifies too | Tested (simulated) |
| Prompt injection via data | a CSV column named "Ignore previous instructions..." | Sanitiser redacts it; output also carries a "treat as data" notice | Tested |
| Resource exhaustion | giant file | File-size, row and column limits | Tested |
| Lack of accountability | "who ran what?" | Audit log | Tested |
| Unauthenticated remote access | HTTP transport exposed to a network | Default is stdio; HTTP binds to localhost only and has **no auth** | Documented limitation |

---

## 7. Setup and run

```bash
# from the repository root (after copying the datamend_mcp/ folder in)
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .                                          # or: pip install datamend
pip install -r datamend_mcp/requirements-mcp.txt

# 1. unit tests (no MCP SDK needed)
python -m unittest discover -s datamend_mcp/tests -t . -v

# 2. create sample data in ./mcp_workspace
python -m datamend_mcp.examples.make_sample_data

# 3. pin the tool definitions (do once, commit the resulting lock file)
python -m datamend_mcp --write-lock

# 4. run the end-to-end demo client
python -m datamend_mcp.client_demo
```

### Connect Claude Desktop
Copy `examples/claude_desktop_config.json` into Claude Desktop's config (Settings ->
Developer -> Edit Config), replace the `/ABSOLUTE/PATH/...` entries, restart Claude
Desktop, then ask: *"List the files in the datamend workspace, score prod.csv and repair it."*

### Environment variables
| Variable | Meaning | Default |
|---|---|---|
| `DATAMEND_MCP_WORKSPACE` | folder the server may touch | `./mcp_workspace` |
| `DATAMEND_MCP_POLICY` | custom policy JSON | bundled `policy.json` |
| `DATAMEND_MCP_READ_ONLY` | `1` disables write tools | off |
| `DATAMEND_MCP_REQUIRE_LOCK` | `1` refuses to start without a lock file | off |

---

## 8. Design decisions

- **Additive, single folder** - no existing file is touched; trivial to review and to revert.
- **Adapter pattern** - only `adapters.py` knows DataMend's API.
- **Logic separate from MCP wiring** - `tools.py`/`security.py` do not import the MCP SDK, so
  they are testable without it.
- **Originals are immutable** - repair always writes a new file in `outputs/`.
- **Fail closed** - unknown tool, bad path, changed tool definition: denied, not guessed.
- **Structured errors** - the agent always receives `{ok, error_type, error}`, never a traceback.
- **`datamend_score` is read-only** - it reuses the repair engine on a copy so the agent can
  inspect health without any write permission.
- **`trace` (FailureTrace) is deliberately not exposed** - it needs a trained model object, and
  loading model files (pickle/joblib) from an agent-controlled path is a code-execution risk.
  Exposing it safely would need a model registry with signed artefacts (future work).

---

## 9. Testing status and honest limitations

**Verified in development:**
- 38 unit tests pass. They cover the security layer fully and the tools against a
  **stub** of DataMend that follows its public documented API.
- The server's startup lock logic was exercised: writing the lock, verifying it, and
  refusing to start after a tool description was tampered with.

**Not verified by the author - please run these on your machine:**
- Running against the **real** `mcp` SDK and the **real** DataMend (neither was installable
  where this was built). If something breaks, it will most likely be in `adapters.py`
  (attribute names on DataMend's report objects) or a version difference in `mcp`.
- `strategy` values: `auto` and `median` appear in DataMend's docs; `mean`/`mode` are
  allowed by `STRATEGIES` in `tools.py` but should be confirmed against your version.

**Design limitations:**
- Injection filtering is a heuristic tripwire, not a guarantee. The real protection is
  that tools return only small, structured, capped values.
- Hash pinning detects *changes*; it does not prove *who* wrote a tool (that needs signatures).
- No authentication on the HTTP transport. Keep stdio, or add auth before exposing it.
- Tools are synchronous; a very large dataset blocks the server while it runs.

---

## 10. Future work

1. Signed tool definitions (public-key verification) instead of hash pinning.
2. OAuth-based authentication for remote HTTP deployment.
3. Safe `datamend_trace` using a registry of signed model artefacts.
4. Async / chunked processing using DataMend's chunked repair for very large files.
5. A small MCP benchmark (in the style of MCP-Bench) measuring task success and latency.

---

## 11. Git: adding this to the `anshu` branch

```bash
git clone https://github.com/NL0711/datamend.git
cd datamend
git fetch --all
git branch -a                          # does origin/anshu already exist?

# if it exists:
git checkout -b anshu origin/anshu
# if it does not:
git checkout -b anshu

# unzip datamend_mcp.zip into the repo root so you get ./datamend_mcp/
git status                             # should show only the new datamend_mcp/ folder

printf "\n# MCP integration runtime files\nmcp_workspace/\n" >> .gitignore

git add datamend_mcp .gitignore
git commit -m "feat(mcp): add MCP server integration with security layer"
git push -u origin anshu
```
Then open a Pull Request `anshu -> main` on GitHub (or tell the maintainer the branch is
ready to merge). If `main` moved on: `git pull --rebase origin main` and push again.
