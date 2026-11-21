"""Talks to a running DataMend MCP server the way a client would: initialize, list tools, call two of them.

    python examples/demo_session.py            (platform running on DATAMEND_BASE_URL, token in DATAMEND_ADMIN_TOKEN or email+password)
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datamend_mcp.mcp_client import default_stdio_client, vet_tools          # noqa: E402
from datamend_mcp import security as sec                                      # noqa: E402
from datamend_mcp.__main__ import DEFAULT_LOCK                                # noqa: E402

c = default_stdio_client(timeout=20)
try:
    info = c.connect()
    print("server:", info["serverInfo"]["name"], info["serverInfo"]["version"], "| protocol", info["protocolVersion"])
    tools = vet_tools(c.list_tools(), sec.load_lock(str(DEFAULT_LOCK)))
    print(f"{len(tools)} tools verified against the pinned lock:", ", ".join(t["name"] for t in tools))
    runs = json.loads(c.call_tool("list_runs", {"limit": 3})["text"])["data"]["runs"]
    print("runs:", [(r["id"], r["label"], r["status"]) for r in runs])
    if runs:
        p = json.loads(c.call_tool("summarize_flag_patterns", {"run_id": runs[0]["id"]})["text"])["data"]
        print("flag patterns of run", runs[0]["id"], "->", json.dumps(p, indent=2))
finally:
    c.close()
