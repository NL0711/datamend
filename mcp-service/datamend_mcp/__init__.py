"""DataMend MCP service (Anshu's contribution).

Two parts, both outside the platform's ``backend/`` package (they import nothing from it and talk to it only over its REST API):

* an MCP server that exposes DataMend's validation results to any MCP client as READ-ONLY tools, resources and prompts;
* the AI narrator service that the platform's ``NARRATOR_URL`` seam was waiting for (docs/contracts/narrator-request-v1.md). It is an MCP
  client of the server above.

Standard library only: nothing here needs a pip install.
"""
__version__ = "0.1.0"
SERVER_NAME = "datamend-mcp"
