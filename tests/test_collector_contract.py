import json
from pathlib import Path

import pytest

from patch_agent.approval import ApprovalStore
from patch_agent.evidence import validate_evidence_contract

ROOT = Path(__file__).resolve().parent.parent
PARTIAL = ROOT / "tests/fixtures/evidence/partial-error.json"

# Freshness/completeness rejection is intentionally not tested here: no max-age or
# completeness rule exists yet. It belongs to the operator collector (plan.md
# S1.2b/S1.3) and is recorded as a blocker in docs/validation.md.


def test_partial_host_collection_is_valid_diagnostics_but_not_approval_evidence(
        tmp_path, plan):
    collection = json.loads(PARTIAL.read_text(encoding="utf-8"))
    validate_evidence_contract(collection)

    assert collection["hosts"]["vm-01"]["status"] == "ok"
    failed = collection["hosts"]["vm-02"]
    assert failed["status"] == "error"
    assert failed["packages"] == {}
    assert failed["error"]["code"]
    assert failed["error"]["message"]

    store = ApprovalStore(tmp_path)
    with pytest.raises(ValueError):
        store.submit(plan, collection)
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 0
