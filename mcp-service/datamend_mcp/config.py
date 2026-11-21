"""Settings, read from the environment only (never from a tracked file). Secrets are never logged."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Tuple
from urllib.parse import urlparse


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None or v == "" else v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # --- how the MCP server reaches the DataMend platform (its REST API) ---
    datamend_base_url: str = "http://localhost:8000"
    datamend_read_token: str = ""           # PREFERRED: the platform's EVIDENCE_API_TOKEN, a read-only credential (GET under /api/validation/ and /api/places/ only)
    datamend_admin_token: str = ""          # ADMIN_TOKEN of the platform, OR the email and password below (wider access than this server needs)
    datamend_admin_email: str = ""
    datamend_admin_password: str = ""
    datamend_timeout_s: float = 15.0

    # --- the MCP server itself ---
    mcp_http_host: str = "127.0.0.1"        # loopback by default; set 0.0.0.0 only behind a proxy that adds TLS
    mcp_http_port: int = 8765
    mcp_bearer_token: str = ""              # REQUIRED for the HTTP transport (stdio is local and needs none)
    mcp_allowed_origins: Tuple[str, ...] = ()     # browser Origins allowed (DNS-rebinding guard); empty = no browser origin accepted
    mcp_rate_per_minute: int = 120
    mcp_audit_log: str = "data/mcp_audit.jsonl"
    mcp_manifest_lock: str = ""             # path of tool_manifest.lock.json; empty = the one shipped next to the package
    mcp_enforce_manifest: bool = True       # refuse to serve a tool whose definition differs from the lock

    # --- the narrator service ---
    narrator_host: str = "127.0.0.1"
    narrator_port: int = 8790
    narrator_bearer_token: str = ""         # the platform's NARRATOR_TOKEN; empty = no auth (local demo only)
    narrator_mcp_url: str = ""              # connect to a remote MCP server over HTTP; empty = start the server as a child process (stdio)
    narrator_mcp_token: str = ""
    narrator_max_tool_steps: int = 6
    narrator_timeout_s: float = 18.0        # under the platform's 20 s timeout
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    narrator_llm_model: str = "claude-sonnet-5-5"

    def validate_url(self) -> None:
        p = urlparse(self.datamend_base_url)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise ValueError("DATAMEND_BASE_URL must be an http or https URL")


def load() -> Settings:
    e = os.environ.get
    origins = tuple(o.strip() for o in (e("MCP_ALLOWED_ORIGINS", "") or "").split(",") if o.strip())
    return Settings(
        datamend_base_url=(e("DATAMEND_BASE_URL") or "http://localhost:8000").rstrip("/"),
        datamend_read_token=e("DATAMEND_READ_TOKEN", "") or "",
        datamend_admin_token=e("DATAMEND_ADMIN_TOKEN", "") or "",
        datamend_admin_email=e("DATAMEND_ADMIN_EMAIL", "") or "",
        datamend_admin_password=e("DATAMEND_ADMIN_PASSWORD", "") or "",
        datamend_timeout_s=_float("DATAMEND_TIMEOUT_S", 15.0),
        mcp_http_host=e("MCP_HTTP_HOST") or "127.0.0.1",
        mcp_http_port=_int("MCP_HTTP_PORT", 8765),
        mcp_bearer_token=e("MCP_BEARER_TOKEN", "") or "",
        mcp_allowed_origins=origins,
        mcp_rate_per_minute=_int("MCP_RATE_PER_MINUTE", 120),
        mcp_audit_log=e("MCP_AUDIT_LOG") or "data/mcp_audit.jsonl",
        mcp_manifest_lock=e("MCP_MANIFEST_LOCK", "") or "",
        mcp_enforce_manifest=_bool("MCP_ENFORCE_MANIFEST", True),
        narrator_host=e("NARRATOR_HOST") or "127.0.0.1",
        narrator_port=_int("NARRATOR_PORT", 8790),
        narrator_bearer_token=e("NARRATOR_BEARER_TOKEN", "") or "",
        narrator_mcp_url=e("NARRATOR_MCP_URL", "") or "",
        narrator_mcp_token=e("NARRATOR_MCP_TOKEN", "") or "",
        narrator_max_tool_steps=_int("NARRATOR_MAX_TOOL_STEPS", 6),
        narrator_timeout_s=_float("NARRATOR_TIMEOUT_S", 18.0),
        anthropic_api_key=e("ANTHROPIC_API_KEY", "") or "",
        anthropic_base_url=(e("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/"),
        narrator_llm_model=e("NARRATOR_LLM_MODEL") or "claude-sonnet-5-5",
    )
