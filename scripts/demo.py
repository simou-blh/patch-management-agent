"""Visible foundation demo: real MCP/CLI/SQLite, synthetic evidence, no VM changes.

Run from the repository root: python scripts/demo.py
All artifacts go into a new isolated folder under data/. No downloads or LLM needed.
"""

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator  # noqa: E402
from mcp import Client, StdioServerParameters  # noqa: E402


def demo_inputs():
    hosts = ["vm-01", "vm-02", "vm-03"]
    evidence = {host: {"packages": {"demo-package": {
        "installed": "1.0-1", "candidates": ["1.0-2"],
    }}} for host in hosts}
    plan = {
        "run_id": "synthetic-demo", "targets": hosts, "canary": "vm-01",
        "packages": [{
            "host": host, "name": "demo-package", "current_version": "1.0-1",
            "proposed_version": "1.0-2", "action": "patch", "priority": "high",
            "advisories": ["SYNTHETIC-DEMO-NOT-A-REAL-ADVISORY"],
            "reason": "Synthetic evidence for testing the approval boundary only.",
        } for host in hosts],
        "verification": ["Check observed package versions; not executed in this demo"],
        "recovery": {"snapshot": "synthetic-not-created", "previous_packages": False,
                     "config_backup": False},
    }
    return evidence, plan


async def run_demo(output_dir):
    # Refuse an existing path so real operator data can never be overwritten.
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    evidence, plan = demo_inputs()
    (output_dir / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (output_dir / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    env = {**os.environ, "PATCH_AGENT_DATA_DIR": str(output_dir)}
    events = []

    def record(step, detail):
        print(f"PASS  {step}: {detail}", flush=True)
        events.append({"step": step, "detail": detail})

    async def call(client, name, arguments, *, error_contains=None):
        response = await client.call_tool(name, arguments)
        if bool(response.is_error) != (error_contains is not None):
            raise RuntimeError(f"Unexpected result for {name}: {response}")
        if error_contains is not None:
            text = " ".join(getattr(part, "text", "") for part in response.content)
            if error_contains not in text:
                raise RuntimeError(f"Expected validation reason missing from {name}: {text}")
        return response.structured_content

    def operator(action, digest=None):
        command = [sys.executable, "-m", "patch_agent.operator", action, plan["run_id"]]
        if digest:
            command += ["--hash", digest]
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                   text=True, timeout=15, check=True)
        return json.loads(completed.stdout)

    print("\nPATCH AGENT FOUNDATION DEMO", flush=True)
    print("Synthetic packages/advisories. Real MCP subprocesses, operator CLI and SQLite.", flush=True)
    print("No live inventory, package changes, canary rollout or recovery is performed.\n", flush=True)
    fleet = StdioServerParameters(command=sys.executable,
                                 args=["-m", "patch_agent.osquery_mcp"], cwd=ROOT, env=env)
    async with Client(fleet, mode="legacy", read_timeout_seconds=15) as client:
        catalog = await call(client, "inventory_catalog", {})
        if set(catalog["hosts"]) != set(plan["targets"]):
            raise RuntimeError("Demo requires the three default configured host names")
        record("MCP inventory catalog", ", ".join(catalog["hosts"]) + " (configured; not queried)")
        await call(client, "query_fleet", {"hosts": ["unknown-host"], "query_id": "packages"},
                   error_contains="unknown inventory host")
        record("Unknown host rejected", "query refused before SSH")

    approval = StdioServerParameters(command=sys.executable,
                                    args=["-m", "patch_agent.approval_mcp"], cwd=ROOT, env=env)
    async with Client(approval, mode="legacy", read_timeout_seconds=15) as client:
        tools = await client.list_tools()
        if {tool.name for tool in tools.tools} != {"submit_plan", "approval_status", "request_deployment"}:
            raise RuntimeError("Unexpected model-facing approval tool catalog")
        record("Approval tool boundary", "model has no approve/reject tool")

        invalid = deepcopy(plan)
        invalid["packages"][0]["proposed_version"] = "99.0-unavailable"
        await call(client, "submit_plan", {"plan": invalid},
                   error_contains="proposed version is unavailable")
        record("Invalid version rejected", "99.0-unavailable is absent from trusted candidates")

        state = await call(client, "submit_plan", {"plan": plan})
        original_hash = state["plan_hash"]
        if state["decision"] != "pending":
            raise RuntimeError("New plan should require approval")
        record("Plan submitted", f"pending; SHA-256 {original_hash}")

        reports = []

        async def request(digest, reason):
            report = await call(client, "request_deployment", {
                "run_id": plan["run_id"], "plan_hash": digest,
            })
            if report["final_status"] != "blocked" or report["jobs"] or reason not in report["reason"]:
                raise RuntimeError(f"Unexpected deployment result: {report}")
            reports.append(report)
            return report

        await request(original_hash, "human approval required")
        record("Unapproved deployment blocked", "no jobs started")

        shown = await asyncio.to_thread(operator, "show")
        if shown["plan"] != plan or shown["plan_hash"] != original_hash:
            raise RuntimeError("Operator did not see the submitted plan/hash")
        approved = await asyncio.to_thread(operator, "approve", original_hash)
        if approved["decision"] != "approved":
            raise RuntimeError("Operator approval failed")
        state = await call(client, "approval_status", {"run_id": plan["run_id"]})
        if state["decision"] != "approved":
            raise RuntimeError("MCP did not observe the CLI approval")
        record("Operator CLI approval", "approved exact hash; MCP reads the persisted decision")
        await request(original_hash, "live execution not implemented")
        record("Approved deployment blocked", "executor is unfinished; no jobs started")

        plan["packages"][0]["reason"] = "Changed synthetic proposal; renewed approval is required."
        state = await call(client, "submit_plan", {"plan": plan})
        if state["decision"] != "pending" or state["plan_hash"] == original_hash:
            raise RuntimeError("Changed plan retained its old approval")
        record("Changed plan invalidates approval", "new hash; decision reset to pending")
        await request(original_hash, "plan changed")
        record("Stale hash blocked", "old approval cannot authorize the revised proposal")

        rejected = await asyncio.to_thread(operator, "reject", state["plan_hash"])
        if rejected["decision"] != "rejected":
            raise RuntimeError("Operator rejection failed")
        report = await request(state["plan_hash"], "human approval required")
        if report["approval"] != "rejected":
            raise RuntimeError("Rejected plan was not persisted")
        record("Operator rejection", "rejected; deployment blocked; no jobs started")

    schema = json.loads((ROOT / "schemas/report.schema.json").read_text())
    for index, report in enumerate(reports, 1):
        Draft202012Validator(schema).validate(report)
        (output_dir / f"report-{index}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    record("Report artifacts", f"{len(reports)} schema-validated JSON reports")
    transcript = {"mode": "synthetic-foundation-demo", "events": events, "reports": reports,
                  "live_inventory_tested": False, "live_deployment_tested": False}
    (output_dir / "transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    print(f"\nDemo passed. Artifacts: {output_dir}", flush=True)
    return transcript


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="new folder only; refuses existing paths")
    args = parser.parse_args()
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
    output_dir = args.output_dir or ROOT / "data" / f"demo-{suffix}"
    asyncio.run(run_demo(output_dir))


if __name__ == "__main__":
    main()
