import pytest
from datetime import datetime, timezone


@pytest.fixture(autouse=True)
def evidence_policy(monkeypatch):
    # Test-only lifetime; operators must choose their own policy explicitly.
    monkeypatch.setenv("PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS", "300")


@pytest.fixture
def evidence():
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    targets = ["vm-01", "vm-02", "vm-03"]
    return {"schema_version": 1, "collected_at": timestamp, "targets": targets,
            "hosts": {name: {"status": "ok", "collected_at": timestamp, "error": None,
                "packages": {"curl:amd64": {"installed": "7.88.1-10",
                    "source": {"name": "curl", "version": "7.88.1-10"},
                    "candidates": [{"version": "7.88.1-10+deb12u1",
                        "source": {"name": "curl", "version": "7.88.1-10+deb12u1"},
                        "origins": [{"uri": "https://repo.example.invalid/debian",
                                     "suite": "bookworm-security", "component": "main"}]}]}}}
                for name in targets}}


@pytest.fixture
def plan():
    return {
        "run_id": "test-run", "targets": ["vm-01", "vm-02", "vm-03"], "canary": "vm-01",
        "packages": [{"host": host, "name": "curl:amd64", "current_version": "7.88.1-10",
                      "proposed_version": "7.88.1-10+deb12u1", "action": "patch", "priority": "high",
                      "advisories": ["TEST-ADVISORY"], "reason": "Synthetic test fixture; not live security evidence"}
                     for host in ("vm-01", "vm-02", "vm-03")],
        "verification": ["installed package versions match the approved plan"],
        "recovery": {"snapshot": "ready", "previous_packages": True, "config_backup": True},
    }
