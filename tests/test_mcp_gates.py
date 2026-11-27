import asyncio
from datetime import datetime, timezone
import json

from mcp import Client

from patch_agent.approval_mcp import mcp as approval_server
from patch_agent.assessment_builder import build_assessment
from patch_agent.preflight import REQUIRED_CHECKS


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def cache():
    return {
        "schema_version": 1, "fetched_at": timestamp(),
        "source": {"name": "debian-security-tracker",
                   "uri": "https://security-tracker.debian.org/tracker/data/json"},
        "release": "bookworm",
        "packages": {"curl": [{"id": "CVE-2026-0001", "status": "resolved",
                                "fixed_version": "7.88.1-10+deb12u1", "urgency": "high"}]},
    }


def preflight(targets):
    now = timestamp()
    checks = [{"id": check, "status": "pass", "detail": "ok", "data": {}}
              for check in REQUIRED_CHECKS]
    host = {"status": "ready", "collected_at": now, "checks": checks,
            "backup": {"status": "verified", "detail": "ok", "files": []},
            "recovery_artifacts": {"status": "verified", "detail": "ok", "artifacts": []},
            "blocking": [], "error": None}
    return {"schema_version": 1, "collected_at": now, "targets": list(targets),
            "hosts": {name: dict(host) for name in targets}}


def publish(directory, *, assessment=None, preflight_doc=None, evidence=None):
    if evidence is not None:
        (directory / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    if assessment is not None:
        (directory / "assessment.json").write_text(json.dumps(assessment), encoding="utf-8")
    if preflight_doc is not None:
        (directory / "preflight.json").write_text(json.dumps(preflight_doc), encoding="utf-8")


def submit(plan):
    async def scenario():
        async with Client(approval_server, raise_exceptions=True) as client:
            return await client.call_tool("submit_plan", {"plan": plan})
    return asyncio.run(scenario())


def test_mcp_submission_uses_operator_gates(tmp_path, monkeypatch, plan, evidence):
    monkeypatch.setenv("PATCH_AGENT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PATCH_AGENT_REQUIRE_GATES", "1")
    assessment = build_assessment(evidence, cache(), assessed_at=timestamp())
    publish(tmp_path, assessment=assessment, preflight_doc=preflight(plan["targets"]),
            evidence=evidence)
    result = submit(plan)
    assert not result.is_error
    assert result.structured_content["decision"] == "pending"


def test_mcp_submission_requires_gates_when_policy_is_set(tmp_path, monkeypatch, plan, evidence):
    monkeypatch.setenv("PATCH_AGENT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PATCH_AGENT_REQUIRE_GATES", "1")
    publish(tmp_path, evidence=evidence)
    result = submit(plan)
    assert result.is_error
    assert "assessment.json is required" in str(result.content)


def test_mcp_submission_rejects_a_plan_mismatching_the_assessment(
        tmp_path, monkeypatch, plan, evidence):
    monkeypatch.setenv("PATCH_AGENT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PATCH_AGENT_REQUIRE_GATES", "1")
    assessment = build_assessment(evidence, cache(), assessed_at=timestamp())
    assessment["results"][0]["decision"]["proposed_version"] = "7.88.1-10+deb12u2"
    publish(tmp_path, assessment=assessment, preflight_doc=preflight(plan["targets"]),
            evidence=evidence)
    result = submit(plan)
    assert result.is_error
    assert "does not match" in str(result.content)
