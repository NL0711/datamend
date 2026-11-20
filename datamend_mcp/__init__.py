"""datamend_mcp - a Model Context Protocol (MCP) server for datamend.

Exposes datamend's data-quality pillars (score, repair, contract, validate,
drift) as MCP tools so any MCP-compatible AI agent can use them, wrapped in a
security layer (workspace sandbox, tool policy, audit log, tool pinning).
"""

__version__ = "0.1.0"
