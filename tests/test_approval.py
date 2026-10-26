import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from patch_agent.approval import ApprovalStore, plan_hash, validate_plan


@pytest.mark.parametrize("change", [
    lambda p: p["targets"].append("unknown"),
    lambda p: p.update(canary="unknown"),
    lambda p: p["packages"][0].update(name="unknown"),
    lambda p: p["packages"][0].update(proposed_version="unavailable"),
    lambda p: p["packages"][0].update(current_version="stale"),
    lambda p: p["packages"][0].update(action="shell"),
    lambda p: p["packages"][0].update(command="reboot"),
    lambda p: p["packages"].append(copy.deepcopy(p["packages"][0])),
])
def test_invalid_plan_is_rejected(plan, evidence, change):
    change(plan)
    with pytest.raises((ValueError, ValidationError)):
        validate_plan(plan, evidence)


def test_approval_is_bound_to_reviewed_hash(tmp_path, plan, evidence):
    store = ApprovalStore(tmp_path)
    original = store.submit(plan, evidence)
    assert store.request_deployment(plan["run_id"], original["plan_hash"])["jobs"] == []
    store.decide(plan["run_id"], original["plan_hash"], "approved")
    # Equivalent key order preserves approval; a changed reason invalidates it.
    assert store.submit(dict(reversed(list(plan.items()))), evidence)["decision"] == "approved"
    plan["packages"][0]["reason"] = "Changed proposal"
    revised = store.submit(plan, evidence)
    assert revised["decision"] == "pending"
    with pytest.raises(ValueError, match="plan changed"):
        store.decide(plan["run_id"], original["plan_hash"], "approved")
    assert "changed" in store.request_deployment(plan["run_id"], original["plan_hash"])["reason"]


@pytest.mark.parametrize("decision", [None, "approved", "rejected"])
def test_all_requests_remain_blocked_and_recorded(tmp_path, plan, evidence, decision):
    store = ApprovalStore(tmp_path)
    state = store.submit(plan, evidence)
    if decision:
        store.decide(plan["run_id"], state["plan_hash"], decision)
    # A new process/store instance must see the operator decision.
    report = ApprovalStore(tmp_path).request_deployment(plan["run_id"], state["plan_hash"])
    schema = json.loads(Path("schemas/report.schema.json").read_text())
    Draft202012Validator(schema).validate(report)
    assert report["final_status"] == "blocked" and report["jobs"] == []
    with store.connect() as db:
        persisted = json.loads(db.execute("SELECT report FROM requests").fetchone()[0])
    assert persisted == report
    if decision == "approved":
        assert "not implemented" in report["reason"]


def test_kernel_is_deferred(plan, evidence):
    package = plan["packages"][0]
    package["name"] = "linux-image-amd64"
    evidence["vm-01"]["packages"][package["name"]] = {"installed": package["current_version"],
                                                            "candidates": [package["proposed_version"]]}
    with pytest.raises(ValueError, match="kernel"):
        validate_plan(plan, evidence)


def test_plan_hash_ignores_object_key_order(plan):
    assert plan_hash(plan) == plan_hash(dict(reversed(list(plan.items()))))


def test_evidence_cannot_expand_inventory_scope(plan, evidence):
    evidence["unknown"] = evidence["vm-01"]
    plan["targets"].append("unknown")
    with pytest.raises(ValueError, match="unknown target"):
        validate_plan(plan, evidence)
