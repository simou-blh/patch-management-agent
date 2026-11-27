from datetime import datetime, timezone

import pytest

from patch_agent.approval import validate_plan
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


def assessment_for(evidence):
    return build_assessment(evidence, cache(), assessed_at=timestamp())


def preflight(targets, *, status="ready", age_seconds=0):
    collected = datetime.now(timezone.utc).timestamp() - age_seconds
    collected_at = datetime.fromtimestamp(collected, timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")
    checks = [{"id": check, "status": "pass", "detail": "ok", "data": {}}
              for check in REQUIRED_CHECKS]
    host = {
        "status": status, "collected_at": collected_at, "checks": checks,
        "backup": {"status": "verified", "detail": "ok", "files": []},
        "recovery_artifacts": {"status": "verified", "detail": "ok", "artifacts": []},
        "blocking": [] if status == "ready" else ["candidates"],
        "error": None,
    }
    return {"schema_version": 1, "collected_at": collected_at,
            "targets": list(targets), "hosts": {name: dict(host) for name in targets}}


def test_assessment_gate_accepts_matching_plan(plan, evidence):
    validate_plan(plan, evidence, assessment=assessment_for(evidence))


def test_assessment_gate_rejects_version_mismatch(plan, evidence):
    assessment = assessment_for(evidence)
    assessment["results"][0]["decision"]["proposed_version"] = "7.88.1-10+deb12u2"
    with pytest.raises(ValueError, match="does not match the assessed decision"):
        validate_plan(plan, evidence, assessment=assessment)


def test_assessment_gate_rejects_unassessed_package(plan, evidence):
    plan["packages"][0]["name"] = "other:amd64"
    with pytest.raises((ValueError, KeyError)):
        validate_plan(plan, evidence, assessment=assessment_for(evidence))


def test_preflight_ready_allows_plan(plan, evidence):
    validate_plan(plan, evidence, preflight=preflight(plan["targets"]))


def test_preflight_not_ready_blocks_plan(plan, evidence):
    with pytest.raises(ValueError, match="preflight blocks"):
        validate_plan(plan, evidence, preflight=preflight(plan["targets"], status="not_ready"))


def test_stale_preflight_blocks_plan(plan, evidence):
    with pytest.raises(ValueError, match="stale"):
        validate_plan(plan, evidence, preflight=preflight(plan["targets"], age_seconds=600))


def test_preflight_targets_must_match_plan(plan, evidence):
    with pytest.raises(ValueError, match="targets"):
        validate_plan(plan, evidence, preflight=preflight(["vm-01"]))


def test_both_gates_accept_the_plan(plan, evidence):
    validate_plan(plan, evidence, assessment=assessment_for(evidence),
                  preflight=preflight(plan["targets"]))
