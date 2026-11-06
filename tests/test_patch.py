import importlib.util
from pathlib import Path

import pytest
import yaml

from patch_agent.debversion import compare_versions, parse_version
from patch_agent.patch import validate_patch_contract

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "playbooks/library/patch_packages.py"

spec = importlib.util.spec_from_file_location("patch_packages_module", MODULE_PATH)
patch_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch_module)

INSTALLED_TEXT = (
    "curl\t7.88.1-10\tamd64\n"
    "libc6:amd64\t2.36-9+deb12u4\tamd64\n"
    "demo-package\t1.0-1\tall\n"
)

CANDIDATES = {
    "curl": {"7.88.1-10+deb12u1": {"amd64"}, "7.88.1-10": {"amd64"}},
    "demo-package": {"1.0-2": {"all"}, "1.0-1": {"all"}},
}

EXPECTATION_PATCH = {
    "name": "curl",
    "architecture": "amd64",
    "expected_installed": "7.88.1-10",
    "target_version": "7.88.1-10+deb12u1",
    "action": "patch",
}

EXPECTATION_DEFER = {
    "name": "demo-package",
    "architecture": "all",
    "expected_installed": None,
    "target_version": None,
    "action": "defer",
}


def envelope(result):
    return {
        "schema_version": 1,
        "collected_at": result["collected_at"],
        "target": "vm-01",
        "canary": True,
        "packages": result["packages"],
        "summary": result["summary"],
        "error": result["error"],
    }


def test_parse_version_orders_debian_correctly():
    assert compare_versions("1.0-1", "1.0-2") == -1
    assert compare_versions("1.0-2", "1.0-1") == 1
    assert compare_versions("1.0-1", "1.0-1") == 0
    assert compare_versions("1.0-1+b1", "1.0-1+b2") == -1
    assert compare_versions("2:1.0-1", "1.0-1") == 1
    with pytest.raises(ValueError):
        parse_version("not-a-version")


def test_normalise_expectations_accepts_valid_scope():
    normalised = patch_module._normalise_expectations([EXPECTATION_PATCH, EXPECTATION_DEFER])
    assert len(normalised) == 2
    assert normalised[0]["action"] == "patch"
    assert normalised[1]["action"] == "defer"
    assert normalised[1]["target_version"] is None


def test_normalise_expectations_rejects_kernel_package():
    with pytest.raises(ValueError, match="kernel"):
        patch_module._normalise_expectations([{**EXPECTATION_PATCH, "name": "linux-image-amd64"}])


def test_normalise_expectations_rejects_duplicate():
    with pytest.raises(ValueError, match="duplicate"):
        patch_module._normalise_expectations([EXPECTATION_PATCH, EXPECTATION_PATCH])


def test_normalise_expectations_rejects_defer_with_target():
    with pytest.raises(ValueError, match="null target version"):
        patch_module._normalise_expectations([{**EXPECTATION_DEFER, "target_version": "1.0-2"}])


def test_validate_patch_scope_validates_patch_package():
    installed = patch_module.parse_installed(INSTALLED_TEXT)
    results = patch_module.validate_patch_scope(
        [EXPECTATION_PATCH], installed, CANDIDATES,
        {"packages": {"curl": {"services": ["ssh"]}}, "services": {"ssh": {"health_checks": []}}},
    )
    assert results[0]["status"] == "validated"
    assert results[0]["data"]["observed_installed"] == "7.88.1-10"
    assert results[0]["data"]["target_version"] == "7.88.1-10+deb12u1"


def test_validate_patch_scope_detects_drift():
    installed = patch_module.parse_installed(INSTALLED_TEXT)
    drifted = {**EXPECTATION_PATCH, "expected_installed": "9.9.9"}
    results = patch_module.validate_patch_scope(
        [drifted], installed, CANDIDATES,
        {"packages": {}, "services": {}},
    )
    assert results[0]["status"] == "failed"
    assert results[0]["data"]["error"]["code"] == "drift_detected"


def test_validate_patch_scope_detects_unavailable_version():
    installed = patch_module.parse_installed(INSTALLED_TEXT)
    unavailable = {**EXPECTATION_PATCH, "target_version": "9.9.9"}
    results = patch_module.validate_patch_scope(
        [unavailable], installed, CANDIDATES,
        {"packages": {}, "services": {}},
    )
    assert results[0]["status"] == "failed"
    assert results[0]["data"]["error"]["code"] == "version_unavailable"


def test_validate_patch_scope_handles_missing_installed():
    installed = {}
    results = patch_module.validate_patch_scope(
        [EXPECTATION_PATCH], installed, CANDIDATES,
        {"packages": {}, "services": {}},
    )
    assert results[0]["status"] == "failed"
    assert results[0]["data"]["error"]["code"] == "installed_unknown"


def test_validate_patch_scope_defers_approved_package():
    installed = patch_module.parse_installed(INSTALLED_TEXT)
    results = patch_module.validate_patch_scope(
        [EXPECTATION_DEFER], installed, CANDIDATES,
        {"packages": {}, "services": {}},
    )
    assert results[0]["status"] == "deferred"


def test_host_result_aggregates_summary():
    results = [
        {"name": "curl", "status": "applied"},
        {"name": "demo-package", "status": "deferred"},
        {"name": "libc6", "status": "failed"},
    ]
    record = patch_module.host_result(results)
    assert record["status"] == "failed"
    assert record["summary"] == {"total": 3, "applied": 1, "skipped": 0, "deferred": 1, "failed": 1}


def test_error_result_matches_contract():
    record = patch_module.error_result("Patch failed (RuntimeError)")
    assert validate_patch_contract(envelope(record)) is None
    assert record["status"] == "error" and record["packages"] == {}


def test_contract_rejects_applied_without_after():
    record = patch_module.host_result([
        {"name": "curl", "architecture": "amd64", "status": "applied", "installed_before": "7.88.1-10",
         "installed_after": None, "target_version": "7.88.1-10+deb12u1",
         "action": "patch", "service_restart": [], "error": None, "detail": "ok"},
    ])
    data = envelope(record)
    with pytest.raises(ValueError, match="no installed_after"):
        validate_patch_contract(data)


def test_contract_rejects_failed_without_error():
    record = patch_module.host_result([
        {"name": "curl", "architecture": "amd64", "status": "failed", "installed_before": "7.88.1-10",
         "installed_after": "7.88.1-10", "target_version": "7.88.1-10+deb12u1",
         "action": "patch", "service_restart": [], "error": None, "detail": "ok"},
    ])
    data = envelope(record)
    with pytest.raises(ValueError, match="no error"):
        validate_patch_contract(data)


def test_contract_rejects_defer_with_target_version():
    record = patch_module.host_result([
        {"name": "curl", "architecture": "amd64", "status": "deferred", "installed_before": "7.88.1-10",
         "installed_after": "7.88.1-10", "target_version": "1.0-2",
         "action": "defer", "service_restart": [], "error": None, "detail": "ok"},
    ])
    data = envelope(record)
    with pytest.raises(ValueError, match="deferred but has a target version"):
        validate_patch_contract(data)


def load_playbook(name):
    return yaml.safe_load((ROOT / "playbooks" / name).read_text(encoding="utf-8"))


def test_patch_playbook_keeps_deployment_blocked_and_no_mutation_modules():
    play = load_playbook("patch.yml")[0]
    text = yaml.safe_dump(play)

    assert play["serial"] == 1
    assert play["become"] is True
    assert play["any_errors_fatal"] is True
    assert "patch_packages" in play["tasks"][0]
    assert "deployment_unblocked" in text

    gates = [task for task in play["tasks"] if "ansible.builtin.fail" in task]
    assert len(gates) >= 1

    for mutation in (
        "ansible.builtin.apt",
        "ansible.builtin.package",
        "ansible.builtin.service",
        "ansible.builtin.command",
        "ansible.builtin.shell",
        "ansible.builtin.copy",
        "ansible.builtin.template",
    ):
        assert mutation not in text


def test_patch_playbook_fails_when_any_package_fails():
    play = load_playbook("patch.yml")[0]
    fail_tasks = [t for t in play["tasks"] if "ansible.builtin.fail" in t]
    canary_fail = [t for t in fail_tasks if "canary package failed" in str(t)]
    assert canary_fail, "patch.yml must fail when a canary package fails"


def _validated(policy=None):
    policy = policy or {
        "schema_version": 1, "restart_policy": "configured-only",
        "services": {"curl-svc": {"restart": "on-change", "health_checks": []}},
        "packages": {"curl": {"services": ["curl-svc"]}},
    }
    expectations = patch_module._normalise_expectations([EXPECTATION_PATCH, EXPECTATION_DEFER])
    installed = patch_module.parse_installed(INSTALLED_TEXT)
    return expectations, patch_module.validate_patch_scope(expectations, installed, CANDIDATES, policy)


def test_execute_patch_blocked_changes_nothing_and_matches_contract(monkeypatch):
    calls = []
    monkeypatch.setattr(patch_module.subprocess, "run", lambda *a, **k: calls.append(a))
    expectations, validation = _validated()
    results = patch_module.execute_patch(validation, expectations, deployment_unblocked=False)
    assert calls == []
    by_name = {r["name"]: r for r in results}
    assert by_name["curl"]["status"] == "failed"
    assert by_name["curl"]["error"]["code"] == "deployment_blocked"
    assert by_name["curl"]["service_restart"] == []
    assert by_name["demo-package"]["status"] == "deferred"
    validate_patch_contract(envelope(patch_module.host_result(results)))


def test_execute_patch_check_mode_skips_without_restart(monkeypatch):
    monkeypatch.setattr(patch_module.subprocess, "run", lambda *a, **k: pytest.fail("ran a command"))
    expectations, validation = _validated()
    results = patch_module.execute_patch(validation, expectations, True, check_mode=True)
    curl = next(r for r in results if r["name"] == "curl")
    assert curl["status"] == "skipped" and curl["service_restart"] == []
    validate_patch_contract(envelope(patch_module.host_result(results)))


def test_execute_patch_restarts_only_after_successful_install(monkeypatch):
    order = []
    monkeypatch.setattr(patch_module, "apply_patch",
                        lambda name, arch, target, *_: order.append("apply") or (True, target, None))
    monkeypatch.setattr(patch_module, "restart_service",
                        lambda service, *_: order.append(f"restart:{service}") or (True, None))
    expectations, validation = _validated()
    results = patch_module.execute_patch(validation, expectations, True, check_mode=False)
    curl = next(r for r in results if r["name"] == "curl")
    assert order == ["apply", "restart:curl-svc"]
    assert curl["status"] == "applied"
    assert curl["installed_after"] == EXPECTATION_PATCH["target_version"]
    assert curl["service_restart"] == [{"service": "curl-svc", "restarted": True, "error": None}]
    validate_patch_contract(envelope(patch_module.host_result(results)))


def test_execute_patch_does_not_restart_when_install_fails(monkeypatch):
    restarts = []
    monkeypatch.setattr(patch_module, "apply_patch",
                        lambda *_: (False, None, {"code": "apt_install_failed", "message": "exit 100"}))
    monkeypatch.setattr(patch_module, "restart_service", lambda s, *_: restarts.append(s) or (True, None))
    expectations, validation = _validated()
    results = patch_module.execute_patch(validation, expectations, True, check_mode=False)
    curl = next(r for r in results if r["name"] == "curl")
    assert restarts == [] and curl["status"] == "failed"
    validate_patch_contract(envelope(patch_module.host_result(results)))


def test_execute_patch_fails_when_target_version_not_reached(monkeypatch):
    monkeypatch.setattr(patch_module, "apply_patch", lambda *_: (True, "7.88.1-10", None))
    monkeypatch.setattr(patch_module, "restart_service", lambda *_: pytest.fail("restarted"))
    expectations, validation = _validated()
    results = patch_module.execute_patch(validation, expectations, True, check_mode=False)
    curl = next(r for r in results if r["name"] == "curl")
    assert curl["status"] == "failed" and curl["error"]["code"] == "target_not_installed"


def test_patch_playbook_gate_catches_module_error():
    play = load_playbook("patch.yml")[0]
    gate = next(t for t in play["tasks"] if "canary package failed" in str(t))
    assert "host_patch.error is not none" in gate["when"]
