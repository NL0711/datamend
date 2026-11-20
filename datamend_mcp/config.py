"""Runtime configuration, read from environment variables.

Environment variables
---------------------
DATAMEND_MCP_WORKSPACE     Folder the server may read/write (default: ./mcp_workspace)
DATAMEND_MCP_POLICY        Path to a policy JSON file (default: bundled policy.json)
DATAMEND_MCP_READ_ONLY     1/true -> all "write" tools are disabled
DATAMEND_MCP_REQUIRE_LOCK  1/true -> refuse to start if tool_manifest.lock.json is missing
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    workspace: Path
    policy_path: Path
    lock_path: Path
    read_only: bool = False
    require_lock: bool = False

    @property
    def outputs_dir(self) -> Path:
        return self.workspace / "outputs"

    @property
    def contracts_dir(self) -> Path:
        return self.workspace / "contracts"

    @property
    def audit_path(self) -> Path:
        # Hidden folder: never listed to the agent, never an allowed data extension.
        return self.workspace / ".audit" / "audit.jsonl"

    @classmethod
    def from_env(cls) -> "Config":
        workspace = Path(os.environ.get("DATAMEND_MCP_WORKSPACE", "mcp_workspace")).resolve()
        policy = Path(os.environ.get("DATAMEND_MCP_POLICY", PACKAGE_DIR / "policy.json")).resolve()
        return cls(
            workspace=workspace,
            policy_path=policy,
            lock_path=PACKAGE_DIR / "tool_manifest.lock.json",
            read_only=_flag("DATAMEND_MCP_READ_ONLY"),
            require_lock=_flag("DATAMEND_MCP_REQUIRE_LOCK"),
        )
