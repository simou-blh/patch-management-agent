"""Run with python -m patch_agent.osquery_mcp (stdio)."""

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from patch_agent.osquery import QUERIES, collect, load_hosts

mcp = MCPServer("Patch fleet inventory")


@mcp.tool(structured_output=True)
def inventory_catalog() -> dict[str, Any]:
    """List permitted host names and fixed query IDs; no arbitrary SQL."""
    return {"hosts": list(load_hosts()), "queries": list(QUERIES)}


@mcp.tool(structured_output=True)
async def query_fleet(hosts: list[str], query_id: str) -> dict[str, Any]:
    """Collect one fixed read-only query, with separate results/errors for each host."""
    try:
        return await collect(hosts, query_id)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
