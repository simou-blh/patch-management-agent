import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from patch_agent.assessment_builder import build_assessment
from patch_agent.planner import build_plan

FIXTURES = Path(__file__).parent / "fixtures" / "assessment"
ORIGIN = {"uri": "https://repo.example.invalid/debian", "suite": "bookworm", "component": "main"}


def cache():
    return json.loads((FIXTURES / "advisory-cache-valid.json").read_text(encoding="utf-8"))


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def package(installed, source_name, source_version, candidates=()):
    return {
        "installed": installed,
        "source": {"name": source_name, "version": source_version} if source_name else None,
        "candidates": [
            {"version": version,
             "source": {"name": name, "version": source} if name else None,
             "origins": [ORIGIN]}
            for version, name, source in candidates
        ],
    }


def collection(packages, *, host="vm-01"):
    collected = timestamp()
    return {"schema_version": 1, "collected_at": collected, "targets": [host],
            "hosts": {host: {"status": "ok", "collected_at": collected,
                              "packages": packages, "error": None}}}


def assessment_for(evidence, advisory_cache=None):
    return build_assessment(evidence, advisory_cache or cache(), assessed_at=timestamp())


def test_plan_contains_patch_decision_and_validates():
    evidence = collection({"demo-package:amd64": package(
        "1:1.0-1", "demo-source", "1:1.0-1",
        [("1:1.0-2", "demo-source", "1:1.0-2")])})
    plan = build_plan(assessment_for(evidence), evidence, run_id="sprint2-run")
    assert plan["targets"] == ["vm-01"] and plan["canary"] == "vm-01"
    entry = plan["packages"][0]
    assert entry["action"] == "patch"
    assert entry["proposed_version"] == "1:1.0-2"
    assert entry["current_version"] == "1:1.0-1"
    assert entry["advisories"] == ["CVE-2026-0001"]


def test_plan_records_a_defer_when_no_package_is_actionable():
    evidence = collection({"clean-package:amd64": package("4.2-1", "clean-source", "4.2-1")})
    plan = build_plan(assessment_for(evidence), evidence, run_id="sprint2-run")
    entry = plan["packages"][0]
    assert entry["action"] == "defer"
    assert entry["proposed_version"] is None
    assert entry["advisories"] == []


def test_kernel_patch_is_converted_to_defer():
    advisory = cache()
    advisory["packages"]["linux-image-amd64"] = [
        {"id": "CVE-2026-0100", "status": "resolved",
         "fixed_version": "6.1.0-2", "urgency": "high"}
    ]
    evidence = collection({"linux-image-amd64:amd64": package(
        "6.1.0-1", "linux-image-amd64", "6.1.0-1",
        [("6.1.0-2", "linux-image-amd64", "6.1.0-2")])})
    plan = build_plan(assessment_for(evidence, advisory), evidence, run_id="sprint2-run")
    assert plan["packages"][0]["action"] == "defer"
    assert plan["packages"][0]["proposed_version"] is None


def test_plan_rejects_assessment_for_other_evidence():
    first = collection({"demo-package:amd64": package("1:1.0-1", "demo-source", "1:1.0-1")})
    second = collection({"clean-package:amd64": package("4.2-1", "clean-source", "4.2-1")})
    with pytest.raises(ValueError, match="different evidence"):
        build_plan(assessment_for(first), second, run_id="sprint2-run")


def test_canary_must_be_selected():
    evidence = collection({"demo-package:amd64": package("1:1.0-1", "demo-source", "1:1.0-1")})
    with pytest.raises(ValueError, match="canary"):
        build_plan(assessment_for(evidence), evidence, run_id="sprint2-run", canary="vm-02")


def test_failed_evidence_is_not_plannable():
    evidence = collection({"demo-package:amd64": package("1:1.0-1", "demo-source", "1:1.0-1")})
    evidence["targets"] = ["vm-01", "vm-02"]
    evidence["hosts"]["vm-02"] = {"status": "error", "collected_at": evidence["collected_at"],
                                   "packages": {}, "error": {"code": "down", "message": "down"}}
    with pytest.raises((ValueError, Exception)):
        build_plan(assessment_for(evidence), evidence, run_id="sprint2-run")
