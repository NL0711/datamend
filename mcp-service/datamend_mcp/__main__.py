"""Command line: ``python -m datamend_mcp <command>``.

serve [--transport stdio|http]   run the MCP server (default stdio)
narrator                         run the narrator HTTP service (the platform's NARRATOR_URL points at it)
manifest [--write|--check]       print, write or verify the pinned tool-definition hashes (tool_manifest.lock.json)
tools                            print the tool names and descriptions
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, security as sec
from .tools import Registry

DEFAULT_LOCK = Path(__file__).resolve().parents[1] / "tool_manifest.lock.json"


def _lock_path(cfg: config.Settings) -> str:
    return cfg.mcp_manifest_lock or str(DEFAULT_LOCK)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="datamend_mcp", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    sub.add_parser("narrator")
    m = sub.add_parser("manifest")
    g = m.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    sub.add_parser("tools")
    a = ap.parse_args(argv)
    cfg = config.load()
    reg = Registry()

    if a.cmd == "tools":
        for t in reg.listing():
            print(f"{t['name']:26} {t['description']}")
        return 0
    if a.cmd == "manifest":
        listing = reg.listing()
        if a.write:
            sec.write_lock(_lock_path(cfg), listing)
            print(f"wrote {_lock_path(cfg)}")
        elif a.check:
            try:
                sec.verify_manifest(listing, sec.load_lock(_lock_path(cfg)))
            except (sec.SecurityError, OSError, ValueError) as e:
                print(f"MISMATCH: {e}", file=sys.stderr)
                return 1
            print("tool definitions match the pinned lock")
        else:
            print(json.dumps(sec.manifest(listing), indent=2))
        return 0

    lock = None
    if cfg.mcp_enforce_manifest:
        try:
            lock = sec.load_lock(_lock_path(cfg))
        except (OSError, ValueError, sec.SecurityError) as e:
            print(f"datamend-mcp: cannot read the tool lock ({e}). Run: python -m datamend_mcp manifest --write, or set MCP_ENFORCE_MANIFEST=false", file=sys.stderr)
            return 2

    if a.cmd == "serve":
        from .protocol import McpServer
        from . import transports
        server = McpServer(cfg, registry=reg, lock=lock)
        if a.transport == "stdio":
            transports.serve_stdio(server)
        else:
            transports.serve_http(server, cfg.mcp_http_host, cfg.mcp_http_port)
        return 0
    if a.cmd == "narrator":
        from .mcp_client import HttpMcpClient, default_stdio_client
        from .narrator.agent import Narrator
        from .narrator.app import serve
        client = HttpMcpClient(cfg.narrator_mcp_url, cfg.narrator_mcp_token, cfg.narrator_timeout_s) if cfg.narrator_mcp_url else default_stdio_client(timeout=cfg.narrator_timeout_s)
        serve(cfg, Narrator(cfg, client, lock=lock))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
