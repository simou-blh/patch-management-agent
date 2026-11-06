"""Model-facing tools. Approval/rejection deliberately exist only in operator.py."""

import json
from typing import Any

from jsonschema import ValidationError
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from patch_agent.approval import data_directory, local_store

mcp = MCPServer("Patch approval facade")


@mcp.tool(structured_output=True)
def submit_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate and store a proposal against operator-collected candidate evidence."""
    evidence_path = data_directory() / "evidence.json"
    if not evidence_path.is_file():
        raise ToolError("operator-collected evidence.json is required; see docs/interfaces.md")
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError("operator evidence file could not be read as JSON") from exc
    try:
        return local_store().submit(plan, evidence)
    except ValidationError as exc:
        raise ToolError("plan does not match schemas/plan.schema.json") from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(structured_output=True)
def approval_status(run_id: str) -> dict[str, Any]:
    """Return the exact plan, its hash, and the operator's decision."""
    try:
        return local_store().status(run_id)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(structured_output=True)
def request_deployment(run_id: str, plan_hash: str) -> dict[str, Any]:
    """Record a blocked deployment request. This foundation cannot start jobs."""
    try:
        return local_store().request_deployment(run_id, plan_hash)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
