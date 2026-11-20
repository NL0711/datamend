"""Demo MCP *client* showing the six-step MCP workflow end to end.

    1 Connect -> 2 Discover -> 3 Select -> 4 Invoke -> 5 Execute -> 6 Return

Here "Select" is a scripted plan; inside Claude Desktop the LLM makes that choice.
The client also *pins* the server's tool definitions against the lock file
before using any tool (defence against tool poisoning / rug pulls).

Usage:
    python -m datamend_mcp.examples.make_sample_data          # creates sample files
    python -m datamend_mcp.client_demo                        # runs the demo
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import PACKAGE_DIR
from .security import verify_lock


def _payload(result: Any) -> Dict[str, Any]:
    """Extract the JSON dict from a CallToolResult (works across SDK versions)."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured.get("result", structured) if set(structured) == {"result"} else structured
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    return {}


async def run(workspace: Path) -> int:
    env = {**os.environ, "DATAMEND_MCP_WORKSPACE": str(workspace)}
    params = StdioServerParameters(command=sys.executable, args=["-m", "datamend_mcp"], env=env)

    async def call(session: ClientSession, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.perf_counter()
        res = _payload(await session.call_tool(name, args))
        ms = (time.perf_counter() - t0) * 1000
        print(f"   -> {name}({args})  [{ms:.0f} ms]  ok={res.get('ok')}")
        return res

    print("1. CONNECT  - starting datamend MCP server over stdio")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("2. DISCOVER - listing tools")
            listed = (await session.list_tools()).tools
            for t in listed:
                print(f"   - {t.name}")
            lock = PACKAGE_DIR / "tool_manifest.lock.json"
            if lock.exists():
                problems = verify_lock(listed, lock)
                if problems:
                    print("   !! Tool definitions do not match the pinned lock file:")
                    for p in problems:
                        print("      ", p)
                    return 1
                print("   tool definitions match the pinned lock file (no tampering detected)")
            else:
                print("   (no lock file found - run: python -m datamend_mcp --write-lock)")

            print("3. SELECT   - plan: list files -> score -> repair -> contract -> validate -> drift")
            print("4-6. INVOKE / EXECUTE / RETURN")
            files = await call(session, "datamend_list_workspace", {})
            print("   files:", [f["path"] for f in files.get("data", {}).get("files", [])])
            s = await call(session, "datamend_score", {"path": "prod.csv"})
            print("   MendScore:", s.get("data", {}).get("mend_score"))
            r = await call(session, "datamend_repair", {"path": "prod.csv", "overwrite": True})
            print("   repaired ->", r.get("data", {}).get("output"))
            await call(session, "datamend_create_contract",
                       {"train_path": "train.csv", "contract_name": "demo", "overwrite": True})
            v = await call(session, "datamend_validate", {"path": "prod.csv", "contract_name": "demo"})
            print("   contract passed:", v.get("data", {}).get("passed"))
            d = await call(session, "datamend_drift", {"train_path": "train.csv", "prod_path": "prod.csv"})
            print("   drifted columns:", d.get("data", {}).get("drifted_columns"))

            print("\nSecurity check: attempt a path-traversal attack ...")
            bad = await call(session, "datamend_score", {"path": "../../etc/passwd"})
            print("   blocked:", bad.get("ok") is False, "-", bad.get("error"))
    return 0


def main() -> int:
    workspace = Path(os.environ.get("DATAMEND_MCP_WORKSPACE", "mcp_workspace")).resolve()
    return asyncio.run(run(workspace))


if __name__ == "__main__":
    raise SystemExit(main())
