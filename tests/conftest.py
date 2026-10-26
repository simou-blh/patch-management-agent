import pytest


@pytest.fixture
def evidence():
    return {name: {"packages": {"curl": {"installed": "7.88.1-10", "candidates": ["7.88.1-10+deb12u1"]}}}
            for name in ("vm-01", "vm-02", "vm-03")}


@pytest.fixture
def plan():
    return {
        "run_id": "test-run", "targets": ["vm-01", "vm-02", "vm-03"], "canary": "vm-01",
        "packages": [{"host": host, "name": "curl", "current_version": "7.88.1-10",
                      "proposed_version": "7.88.1-10+deb12u1", "action": "patch", "priority": "high",
                      "advisories": ["TEST-ADVISORY"], "reason": "Synthetic test fixture; not live security evidence"}
                     for host in ("vm-01", "vm-02", "vm-03")],
        "verification": ["installed package versions match the approved plan"],
        "recovery": {"snapshot": "ready", "previous_packages": True, "config_backup": True},
    }
