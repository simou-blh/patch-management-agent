import importlib.util
from pathlib import Path

import pytest
import yaml

from patch_agent.debversion import compare_versions, parse_version
from patch_agent.verify import validate_verify_contract

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "playbooks/library/verify_packages.py"

spec = importlib.util.spec_from_file_location("verify_packages_module", MODULE_PATH)
verify_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_module)

INSTALLED_TEXT = (
    "curl\t7.88.1-10+deb12u1\tamd64\n"
    "libc6:amd64\t2.36-9+deb12u4\tamd64\n"
    "demo-package\t1.0-1\tall\n"
)

EXPECTATION_PASS = {
    "name": "curl",
    "architecture": "amd64",
    "expected_version": "7.88.1-10+deb12u1",
}

EXPECTATION_FAIL = {
    "name": "curl",
    "architecture": "amd64",
    "expected_version": "9.9.9",
}

EXPECTATION_MISSING = {
    "name": "nonexistent",
    "architecture": None,
    "expected_version": "1.0-0",
}


def envelope(result):
    return {
        "schema_version": 1,
        "collected_at": result["collected_at"],
        "target": "vm-01",
        "packages": result["packages"],
        "summary": result["summary"],
        "error": result["error"],
    }


def test_compare_versions_orders_debian_correctly():
    assert compare_versions("1.0-1", "1.0-2") == -1
    assert compare_versions("1.0-2", "1.0-1") == 1
    assert compare_versions("1.0-1", "1.0-1") == 0
    assert compare_versions("1.0-1+b1", "1.0-1+b2") == -1
    assert compare_versions("2:1.0-1", "1.0-1") == 1
    with pytest.raises(ValueError):
        parse_version("not-a-version")


def test_parse_installed_is_architecture_qualified():
    installed = verify_module.parse_installed(INSTALLED_TEXT)
    assert installed == {
        "curl:amd64": "7.88.1-10+deb12u1",
        "libc6:amd64": "2.36-9+deb12u4",
        "demo-package:all": "1.0-1",
    }


def test_check_version_passes_when_observed_matches_expected():
    installed = verify_module.parse_installed(INSTALLED_TEXT)
    check = verify_module.check_version(installed, "curl", "amd64", "7.88.1-10+deb12u1")
    assert check["status"] == "pass"
    assert check["data"]["observed_version"] == "7.88.1-10+deb12u1"


def test_check_version_fails_when_observed_differs():
    installed = verify_module.parse_installed(INSTALLED_TEXT)
    check = verify_module.check_version(installed, "curl", "amd64", "9.9.9")
    assert check["status"] == "fail"


def test_check_version_errors_when_package_missing():
    installed = verify_module.parse_installed(INSTALLED_TEXT)
    check = verify_module.check_version(installed, "nonexistent", None, "1.0-0")
    assert check["status"] == "error"


def test_check_version_errors_on_ambiguous_architecture():
    installed = {"curl:amd64": "1.0-0", "curl:i386": "1.0-0"}
    check = verify_module.check_version(installed, "curl", None, "1.0-0")
    assert check["status"] == "error"


def test_normalise_expectations_rejects_duplicate():
    with pytest.raises(ValueError, match="duplicate"):
        verify_module._normalise_expectations([EXPECTATION_PASS, EXPECTATION_PASS])


def test_validate_verify_scope_passes_all():
    installed = verify_module.parse_installed(INSTALLED_TEXT)
    results = verify_module.validate_verify_scope(
        [EXPECTATION_PASS], installed,
        {"packages": {"curl": {"services": []}}, "services": {}},
        deployment_unblocked=False, check_mode=True,
    )
    assert results[0]["status"] == "pass"
    assert results[0]["observed_version"] == "7.88.1-10+deb12u1"


def test_validate_verify_scope_fails_on_mismatch():
    installed = verify_module.parse_installed(INSTALLED_TEXT)
    results = verify_module.validate_verify_scope(
        [EXPECTATION_FAIL], installed,
        {"packages": {}, "services": {}},
        deployment_unblocked=False, check_mode=True,
    )
    assert results[0]["status"] == "fail"


def test_validate_verify_scope_errors_on_missing():
    installed = verify_module.parse_installed(INSTALLED_TEXT)
    results = verify_module.validate_verify_scope(
        [EXPECTATION_MISSING], installed,
        {"packages": {}, "services": {}},
        deployment_unblocked=False, check_mode=True,
    )
    assert results[0]["status"] == "error"


def test_host_result_aggregates_summary():
    results = [
        {"name": "curl", "status": "pass"},
        {"name": "libc6", "status": "fail"},
        {"name": "demo-package", "status": "error"},
    ]
    record = verify_module.host_result(results)
    assert record["status"] == "failed"
    assert record["summary"] == {"total": 3, "passed": 1, "failed": 1, "error": 1}


def test_error_result_matches_contract():
    record = verify_module.error_result("Verify failed (RuntimeError)")
    assert validate_verify_contract(envelope(record)) is None
    assert record["status"] == "error" and record["packages"] == {}


def test_contract_rejects_pass_with_mismatched_versions():
    record = verify_module.host_result([
        {"name": "curl", "status": "pass", "detail": "ok",
         "expected_version": "1.0-0", "observed_version": "2.0-0",
         "version_check": {"name": "curl", "architecture": None, "status": "pass",
                           "detail": "ok", "data": {}},
         "health_checks": [], "architecture": None},
    ])
    with pytest.raises(ValueError, match="observed != expected"):
        validate_verify_contract(envelope(record))


def test_tcp_health_probe_reports_unreachable():
    result = verify_module.check_tcp_health("ssh", "127.0.0.1", 1, 1)
    assert result["status"] == "fail"
    assert result["check"] == "tcp"


def test_systemd_health_is_skipped_when_blocked():
    result = verify_module.check_systemd_health("ssh", "ssh.service", False, True)
    assert result["status"] == "skipped"
    assert "blocked" in result["detail"]


def test_run_health_checks_rejects_unknown_type():
    checks = verify_module.run_health_checks(
        "svc", {"health_checks": [{"type": "bogus"}]}, False, True,
    )
    assert checks[0]["status"] == "error"


def load_playbook(name):
    return yaml.safe_load((ROOT / "playbooks" / name).read_text(encoding="utf-8"))


def test_verify_playbook_keeps_deployment_blocked_and_no_mutation_modules():
    play = load_playbook("verify.yml")[0]
    text = yaml.safe_dump(play)

    assert play["serial"] == 1
    assert play["become"] is True
    assert play["any_errors_fatal"] is False
    assert "verify_packages" in play["tasks"][0]
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


def test_verify_playbook_fails_when_verification_fails():
    play = load_playbook("verify.yml")[0]
    fail_tasks = [t for t in play["tasks"] if "ansible.builtin.fail" in t]
    verify_fail = [t for t in fail_tasks if "verification failed" in str(t)]
    assert verify_fail, "verify.yml must fail when verification fails"


def test_contract_accepts_error_for_missing_package():
    installed = verify_module.parse_installed("curl\t7.88.1-10\tamd64\n")
    expectations = verify_module._normalise_expectations(
        [{"name": "openssl", "architecture": "amd64", "expected_version": "3.0.15-1~deb12u1"}])
    results = verify_module.validate_verify_scope(expectations, installed, {"packages": {}}, False)
    record = verify_module.host_result(results)
    assert results[0]["status"] == "error"
    validate_verify_contract({
        "schema_version": 1, "collected_at": record["collected_at"], "target": "vm-01",
        "packages": record["packages"], "summary": record["summary"], "error": record["error"],
    })


def test_verify_playbook_gate_catches_module_error():
    play = load_playbook("verify.yml")[0]
    gate = next(t for t in play["tasks"] if "ansible.builtin.fail" in t)
    assert "host_verify.error is not none" in gate["when"]
