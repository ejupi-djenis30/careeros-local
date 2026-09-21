"""Console-only frozen MCP launcher; stdout belongs exclusively to JSON-RPC."""

from backend.automation.mcp_server import main

if __name__ == "__main__":
    raise SystemExit(main())
