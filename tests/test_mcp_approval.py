import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from mcp import Client, StdioServerParameters
from jsonschema import Draft202012Validator

from patch_agent.approval import ApprovalStore
from patch_agent.approval_mcp import mcp as approval_server

ROOT = Path(__file__).resolve().parent.parent
REPORT_SCHEMA = json.loads((ROOT / "schemas/report.schema.json").read_text(encoding="utf-8"))


def write_evidence(directory, evidence):
    (Path(directory) / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")


def test_in_process_approval_lifecycle_is_isolated_and_operator_owned(
        tmp_path, monkeypatch, plan, evidence):
    monkeypatch.setenv("PATCH_AGENT_DATA_DIR", str(tmp_path))
    write_evidence(tmp_path, evidence)

    async def scenario():
        async with Client(approval_server, raise_exceptions=True) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {"submit_plan", "approval_status", "request_deployment"}
            assert not any("approve" in name or "reject" in name for name in names)
            inputs = {tool.name: set((tool.input_schema or {}).get("properties", {}))
                      for tool in tools.tools}
            assert inputs["submit_plan"] == {"plan"}
            assert inputs["approval_status"] == {"run_id"}
            assert inputs["request_deployment"] == {"run_id", "plan_hash"}
            for properties in inputs.values():
                assert "data_dir" not in properties

            submitted = await client.call_tool("submit_plan", {"plan": plan})
            assert not submitted.is_error
            state = submitted.structured_content
            assert state["decision"] == "pending"
            assert re.fullmatch(r"[a-f0-9]{64}", state["plan_hash"])

            status = (await client.call_tool(
                "approval_status", {"run_id": plan["run_id"]})).structured_content
            assert status["plan"] == plan
            assert status["plan_hash"] == state["plan_hash"]
            assert status["decision"] == "pending"

            blocked = (await client.call_tool(
                "request_deployment",
                {"run_id": plan["run_id"], "plan_hash": state["plan_hash"]})).structured_content
            Draft202012Validator(REPORT_SCHEMA).validate(blocked)
            assert blocked["final_status"] == "blocked"
            assert blocked["jobs"] == []
            assert "human approval required" in blocked["reason"]

            # The operator CLI is the only decider; a fresh store instance must see it.
            ApprovalStore(tmp_path).decide(plan["run_id"], state["plan_hash"], "approved")
            assert ApprovalStore(tmp_path).status(plan["run_id"])["decision"] == "approved"

            status = (await client.call_tool(
                "approval_status", {"run_id": plan["run_id"]})).structured_content
            assert status["decision"] == "approved"

            blocked = (await client.call_tool(
                "request_deployment",
                {"run_id": plan["run_id"], "plan_hash": state["plan_hash"]})).structured_content
            assert blocked["final_status"] == "blocked"
            assert blocked["jobs"] == []
            assert "live execution not implemented" in blocked["reason"]

    asyncio.run(scenario())
    assert (tmp_path / "approvals.sqlite").is_file()


def test_subprocess_approval_server_honors_env_configured_store(tmp_path, plan, evidence):
    write_evidence(tmp_path, evidence)
    env = {**os.environ, "PATCH_AGENT_DATA_DIR": str(tmp_path)}

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "patch_agent.approval_mcp"],
            env=env,
            cwd=ROOT,
        )
        async with Client(params, mode="legacy", read_timeout_seconds=15) as client:
            submitted = await client.call_tool("submit_plan", {"plan": plan})
            state = submitted.structured_content
            assert state["decision"] == "pending"

            decision = subprocess.run(
                [sys.executable, "-m", "patch_agent.operator", "approve",
                 plan["run_id"], "--hash", state["plan_hash"]],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30, check=True,
            )
            assert "approved" in decision.stdout

            status = (await client.call_tool(
                "approval_status", {"run_id": plan["run_id"]})).structured_content
            assert status["decision"] == "approved"

            blocked = (await client.call_tool(
                "request_deployment",
                {"run_id": plan["run_id"], "plan_hash": state["plan_hash"]})).structured_content
            assert blocked["final_status"] == "blocked"
            assert blocked["jobs"] == []

    asyncio.run(scenario())
