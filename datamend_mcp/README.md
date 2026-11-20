# datamend_mcp - MCP integration for DataMend

Lets any MCP-compatible AI agent (e.g. Claude Desktop) use DataMend's data-quality
pillars - score, repair, contract, validate, drift - through the Model Context
Protocol, with a built-in security layer.

Full documentation: [`docs/MCP_INTEGRATION.md`](docs/MCP_INTEGRATION.md)

Quick start (from the repo root):

    pip install -r datamend_mcp/requirements-mcp.txt
    python -m unittest discover -s datamend_mcp/tests -t .
    python -m datamend_mcp.examples.make_sample_data
    python -m datamend_mcp --write-lock
    python -m datamend_mcp.client_demo
