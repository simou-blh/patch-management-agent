import importlib.util
from pathlib import Path

import pytest
import yaml

from patch_agent.recover import validate_recover_contract

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "playbooks/library/recover_packages.py"

spec = importlib.util.spec_from_file_location("recover_packages_module", MODULE_PATH)
recover_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recover_module)

PREVIOUS_PACKAGES = [
    {"name": "curl", "previous_version": "7.88.1-10", "architecture": "amd64"},
]

CONFIG_PATHS = ["/etc/ssh/sshd_config"]


def envelope(result):
    return {
        "schema_version": 1,
        "collected_at": result["collected_at"],
        "target": "vm-01",
        "diagnostics": result["diagnostics"],
        "repair": result["repair"],
        "restoration": result["restoration"],
        "manual_intervention": result["manual_intervention"],
        "error": result["error"],
    }


def test_normalise_previous_packages_accepts_valid():
    normalised = recover_module._normalise_previous_packages(PREVIOUS_PACKAGES)
    assert len(normalised) == 1
    assert normalised[0]["name"] == "curl"
    assert normalised[0]["previous_version"] == "7.88.1-10"


def test_normalise_previous_packages_rejects_invalid():
    with pytest.raises(ValueError, match="invalid package name"):
        recover_module._normalise_previous_packages([{"name": "Bad Name", "previous_version": "1.0"}])
    with pytest.raises(ValueError, match="duplicate"):
        recover_module._normalise_previous_packages(PREVIOUS_PACKAGES + PREVIOUS_PACKAGES)


def test_normalise_config_paths_accepts_valid():
    normalised = recover_module._normalise_config_paths(CONFIG_PATHS)
    assert normalised == ["/etc/ssh/sshd_config"]


def test_normalise_config_paths_rejects_invalid():
    with pytest.raises(ValueError, match="absolute without"):
        recover_module._normalise_config_paths(["relative/path"])
    with pytest.raises(ValueError, match="absolute without"):
        recover_module._normalise_config_paths(["/etc/../passwd"])
    with pytest.raises(ValueError, match="duplicate"):
        recover_module._normalise_config_paths(CONFIG_PATHS + CONFIG_PATHS)


def test_capture_diagnostics_returns_all_sections():
    diagnostics = recover_module.capture_diagnostics()
    assert set(diagnostics) == {"dpkg_audit", "apt_policy", "service_status"}
    assert "returncode" in diagnostics["dpkg_audit"]
    assert "returncode" in diagnostics["apt_policy"]
    assert "returncode" in diagnostics["service_status"]


def test_bounded_apt_repair_is_not_attempted_when_blocked():
    repair = recover_module.bounded_apt_repair(False, True)
    assert repair["attempted"] is False
    assert repair["result"] == "not_attempted"
    assert repair["dry_run"] is True
    assert "blocked" in repair["detail"]


def test_restore_previous_package_is_not_attempted_when_blocked():
    result = recover_module.restore_previous_package(
        "curl", "7.88.1-10", "amd64", False, True,
    )
    assert result["attempted"] is False
    assert result["result"] == "not_attempted"


def test_restore_config_backup_is_not_attempted_when_blocked():
    result = recover_module.restore_config_backup("/etc/ssh/sshd_config", None, False, True)
    assert result["attempted"] is False
    assert result["result"] == "not_attempted"


def test_host_result_manual_required_when_repair_fails():
    diagnostics = {"dpkg_audit": {"issues": 0}, "apt_policy": {}, "service_status": {}}
    repair = {"attempted": True, "result": "failed", "detail": "apt failed"}
    previous = [{"name": "curl", "previous_version": "1.0-0", "architecture": "amd64",
                 "attempted": True, "result": "succeeded", "detail": "ok"}]
    config = [{"path": "/etc/ssh/sshd_config", "attempted": True,
               "result": "succeeded", "detail": "ok"}]
    record = recover_module.host_result(
        diagnostics, repair, previous, config, manual_intervention=False,
    )
    assert record["status"] == "failed"
    assert record["manual_intervention"] is False


def test_host_result_manual_required_when_flagged():
    diagnostics = {"dpkg_audit": {"issues": 0}, "apt_policy": {}, "service_status": {}}
    repair = {"attempted": False, "result": "not_attempted", "detail": "blocked"}
    record = recover_module.host_result(
        diagnostics, repair, [], [], manual_intervention=True,
    )
    assert record["status"] == "manual_required"
    assert record["manual_intervention"] is True


def test_error_result_matches_contract():
    record = recover_module.error_result("Recovery failed (RuntimeError)")
    assert validate_recover_contract(envelope(record)) is None
    assert record["status"] == "error"
    assert record["manual_intervention"] is True


def test_contract_rejects_no_intervention_but_repair_failed():
    diagnostics = {"dpkg_audit": {"issues": 0}, "apt_policy": {}, "service_status": {}}
    repair = {"attempted": True, "command": "apt-get install -f -y --dry-run",
              "dry_run": False, "result": "failed", "detail": "apt failed"}
    record = recover_module.host_result(
        diagnostics, repair, [], [], manual_intervention=False,
    )
    with pytest.raises(ValueError, match="no manual intervention but repair failed"):
        validate_recover_contract(envelope(record))


def test_contract_rejects_no_intervention_but_restore_failed():
    diagnostics = {"dpkg_audit": {"issues": 0}, "apt_policy": {}, "service_status": {}}
    repair = {"attempted": False, "command": "not run", "dry_run": True,
              "result": "not_attempted", "detail": "blocked"}
    previous = [{"name": "curl", "previous_version": "1.0-0", "architecture": "amd64",
                 "attempted": True, "result": "failed", "detail": "restore failed"}]
    record = recover_module.host_result(
        diagnostics, repair, previous, [], manual_intervention=False,
    )
    with pytest.raises(ValueError, match="previous-package restore failed"):
        validate_recover_contract(envelope(record))


def load_playbook(name):
    return yaml.safe_load((ROOT / "playbooks" / name).read_text(encoding="utf-8"))


def test_recover_playbook_keeps_deployment_blocked_and_no_mutation_modules():
    play = load_playbook("recover.yml")[0]
    text = yaml.safe_dump(play)

    assert play["serial"] == 1
    assert play["become"] is True
    assert play["any_errors_fatal"] is True
    assert "recover_packages" in play["tasks"][0]
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


def test_recover_playbook_fails_when_manual_intervention_required():
    play = load_playbook("recover.yml")[0]
    fail_tasks = [t for t in play["tasks"] if "ansible.builtin.fail" in t]
    manual_fail = [t for t in fail_tasks if "manual intervention" in str(t)]
    assert manual_fail, "recover.yml must fail when manual intervention is required"


SIMULATION_WITH_REMOVAL = (
    "Inst curl [7.88.1-10+deb12u1] (7.88.1-10 Debian:12.12/stable [amd64])\n"
    "Remv libfoo1 [1.0-1]\n"
)


def _fake_apt(monkeypatch, outputs, installed="7.88.1-10"):
    """Feed apt-get/dpkg-query results in order and record the commands run."""
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0] == "dpkg-query":
            return recover_module.subprocess.CompletedProcess(command, 0, installed, "")
        returncode, stdout = outputs.pop(0)
        return recover_module.subprocess.CompletedProcess(command, returncode, stdout, "err")

    monkeypatch.setattr(recover_module.subprocess, "run", fake_run)
    return calls


def test_planned_removals_reads_simulation():
    assert recover_module.planned_removals(SIMULATION_WITH_REMOVAL) == ["libfoo1"]
    assert recover_module.planned_removals("Inst curl [1]\nConf curl\n") == []


def test_live_repair_runs_for_real_after_clean_simulation(monkeypatch):
    calls = _fake_apt(monkeypatch, [(0, "Conf curl\n"), (0, "done")])
    repair = recover_module.bounded_apt_repair(True, check_mode=False)
    assert calls[0][:4] == ["apt-get", "install", "-f", "-s"]
    assert calls[1][:4] == ["apt-get", "install", "-f", "-y"]
    assert "--dry-run" not in calls[1] and "-s" not in calls[1]
    assert repair["attempted"] is True and repair["dry_run"] is False
    assert repair["result"] == "succeeded"


def test_live_repair_refuses_to_remove_packages(monkeypatch):
    calls = _fake_apt(monkeypatch, [(0, SIMULATION_WITH_REMOVAL)])
    repair = recover_module.bounded_apt_repair(True, check_mode=False)
    assert len(calls) == 1
    assert repair["result"] == "failed" and "libfoo1" in repair["detail"]


def test_restore_previous_package_downgrades_and_verifies(monkeypatch):
    calls = _fake_apt(monkeypatch, [(0, "Inst curl\n"), (0, "done")], installed="7.88.1-10")
    result = recover_module.restore_previous_package("curl", "7.88.1-10", "amd64", True, False)
    assert "--allow-downgrades" in calls[1] and "curl:amd64=7.88.1-10" in calls[1]
    assert calls[2][0] == "dpkg-query"
    assert result["result"] == "succeeded"


def test_restore_previous_package_fails_when_version_not_reached(monkeypatch):
    _fake_apt(monkeypatch, [(0, "Inst curl\n"), (0, "done")], installed="7.88.1-10+deb12u1")
    result = recover_module.restore_previous_package("curl", "7.88.1-10", "amd64", True, False)
    assert result["result"] == "failed" and "expected 7.88.1-10" in result["detail"]


def test_restore_config_backup_without_backup_fails_cleanly():
    result = recover_module.restore_config_backup("/etc/ssh/sshd_config", None, True, False)
    assert result["result"] == "failed" and result["attempted"] is False


def test_restore_config_backup_copies_and_verifies(tmp_path):
    backup = tmp_path / "backup.conf"
    target = tmp_path / "live.conf"
    backup.write_text("Port 22\n")
    target.write_text("Port 2222\n")
    result = recover_module.restore_config_backup(str(target), str(backup), True, False)
    assert result["result"] == "succeeded"
    assert target.read_text() == "Port 22\n"
