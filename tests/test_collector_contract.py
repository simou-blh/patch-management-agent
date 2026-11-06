import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import ValidationError

from patch_agent.approval import ApprovalStore
from patch_agent.evidence import validate_evidence_contract

ROOT = Path(__file__).resolve().parent.parent
PARTIAL = ROOT / "tests/fixtures/evidence/partial-error.json"

# Freshness/host-completeness details live in test_evidence_readiness.py.
# This test checks that approval also applies the readiness gate.


def test_partial_host_collection_is_valid_diagnostics_but_not_approval_evidence(
        tmp_path, plan):
    collection = json.loads(PARTIAL.read_text(encoding="utf-8"))
    validate_evidence_contract(collection)
    # Match the plan's requested scope so failure is specifically the failed host.
    plan["targets"] = ["vm-01", "vm-02"]
    plan["packages"] = [p for p in plan["packages"] if p["host"] in plan["targets"]]

    assert collection["hosts"]["vm-01"]["status"] == "ok"
    failed = collection["hosts"]["vm-02"]
    assert failed["status"] == "error"
    assert failed["packages"] == {}
    assert failed["error"]["code"]
    assert failed["error"]["message"]

    store = ApprovalStore(tmp_path)
    with pytest.raises(ValueError, match="inspection failed"):
        store.submit(plan, collection)
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 0


@pytest.mark.parametrize("failure", ["stale", "future", "stale_host", "legacy", "failed", "missing_host"])
def test_approval_rejects_unready_evidence_before_persisting(tmp_path, plan, evidence, failure):
    if failure in {"stale", "future"}:
        timestamp = "2000-01-01T00:00:00Z" if failure == "stale" else "2100-01-01T00:00:00Z"
        evidence["collected_at"] = timestamp
        for host in evidence["hosts"].values():
            host["collected_at"] = timestamp
    elif failure == "stale_host":
        evidence["hosts"]["vm-02"]["collected_at"] = "2000-01-01T00:00:00Z"
    elif failure == "legacy":
        evidence = evidence["hosts"]
    elif failure == "failed":
        evidence["hosts"]["vm-02"].update(status="error", packages={},
            error={"code": "timeout", "message": "Synthetic inspection failed"})
    else:
        del evidence["hosts"]["vm-02"]
    store = ApprovalStore(tmp_path)
    with pytest.raises((ValueError, ValidationError)):
        store.submit(plan, evidence)
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 0


def test_approval_requires_operator_age_policy(tmp_path, plan, evidence, monkeypatch):
    monkeypatch.delenv("PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS")
    with pytest.raises(ValueError, match="PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS"):
        ApprovalStore(tmp_path).submit(plan, evidence)


def test_approval_cannot_guess_architecture_from_unqualified_binary_name(tmp_path, plan, evidence):
    plan["packages"][0]["name"] = "curl"
    with pytest.raises(ValueError, match="unknown package"):
        ApprovalStore(tmp_path).submit(plan, evidence)


def test_candidates_from_another_architecture_do_not_authorize_patch(tmp_path, plan, evidence):
    packages = evidence["hosts"]["vm-01"]["packages"]
    packages["curl:arm64"] = deepcopy(packages["curl:amd64"])
    packages["curl:amd64"]["candidates"] = []
    with pytest.raises(ValueError, match="proposed version is unavailable"):
        ApprovalStore(tmp_path).submit(plan, evidence)
