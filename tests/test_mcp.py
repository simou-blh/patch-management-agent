import asyncio
import json
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters
import pytest

from patch_agent.approval_mcp import mcp as approval_server
from patch_agent.osquery_mcp import mcp as fleet_server


def test_actual_mcp_catalog_has_no_approval_tool():
    async def scenario():
        async with Client(approval_server, raise_exceptions=True) as client:
            tools = await client.list_tools()
            assert {t.name for t in tools.tools} == {"submit_plan", "approval_status", "request_deployment"}
        async with Client(fleet_server, raise_exceptions=True) as client:
            result = await client.call_tool("inventory_catalog", {})
            assert not result.is_error
            assert set(result.structured_content["hosts"]) == {"vm-01", "vm-02", "vm-03"}
            rejected = await client.call_tool("query_fleet", {"hosts": ["unknown"], "query_id": "packages"})
            assert rejected.is_error
            assert "unknown inventory host" in rejected.content[0].text

    asyncio.run(scenario())


@pytest.mark.parametrize("module,expected", [
    ("patch_agent.osquery_mcp", {"inventory_catalog", "query_fleet"}),
    ("patch_agent.approval_mcp", {"submit_plan", "approval_status", "request_deployment"}),
])
def test_stdio_legacy_client_handshake(module, expected):
    # Exercise the subprocess entrypoint and legacy MCP transport used by hosts.
    async def scenario():
        params = StdioServerParameters(command=sys.executable, args=["-m", module])
        async with Client(params, mode="legacy", read_timeout_seconds=15) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == expected

    asyncio.run(scenario())


@pytest.mark.parametrize("name", ["fleet", "approval"])
def test_opencode_configured_launch_command(name):
    # Test the exact module arguments OpenCode uses.
    config = json.loads(Path("opencode.json").read_text())
    command = config["mcp"]["servers"][name]["command"]

    async def scenario():
        params = StdioServerParameters(command=sys.executable, args=command[1:])
        async with Client(params, mode="legacy", read_timeout_seconds=15) as client:
            tools = await client.list_tools()
            assert len(tools.tools) == (2 if name == "fleet" else 3)

    asyncio.run(scenario())
