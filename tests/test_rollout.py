import importlib.util
from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError

from patch_agent.rollout import validate_rollout_contract

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "playbooks/library/sequential_rollout.py"

spec = importlib.util.spec_from_file_location("sequential_rollout_module", MODULE_PATH)
rollout_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout_module)


def make_step(name, status, detail="ok", data=None):
    return rollout_module.step_result(name, status, detail, data or {})


def make_host(target, preflight="ready", patch="completed", verify="passed",
              recover={}, action="proceed", collected_at="2026-11-06T12:00:00Z",
              error=None, blocking=None):
    record = rollout_module.host_rollout_result(
        target, make_step("preflight", preflight),
        make_step("patch", patch), make_step("verify", verify),
        recover, action, collected_at, error,
    )
    if blocking is not None:
        record["blocking"] = blocking
    return record


def envelope(hosts, targets=None, canary="vm-01"):
    if targets is None:
        targets = list(hosts.keys())
    return {
        "schema_version": 1,
        "collected_at": "2026-11-06T12:00:00Z",
        "targets": targets,
        "canary": canary,
        "hosts": hosts,
        "summary": {
            "total": len(hosts),
            "completed": sum(1 for h in hosts.values() if h["action"] == "proceed"),
            "failed": sum(1 for h in hosts.values() if h["action"] == "recover"),
            "stopped_early": any(h["action"] == "recover" for h in hosts.values()),
        },
        "error": None,
    }


def test_normalize_rollout_scope_orders_canary_first():
    ordered = rollout_module.normalize_rollout_scope(["vm-02", "vm-01", "vm-03"], "vm-01")
    assert ordered == ["vm-01", "vm-02", "vm-03"]


def test_normalize_rollout_scope_rejects_duplicate_targets():
    with pytest.raises(ValueError, match="unique"):
        rollout_module.normalize_rollout_scope(["vm-01", "vm-01"], "vm-01")


def test_normalize_rollout_scope_rejects_invalid_target():
    with pytest.raises(ValueError, match="invalid rollout target"):
        rollout_module.normalize_rollout_scope(["Bad Host"], "Bad Host")


def test_normalize_rollout_scope_rejects_canary_not_in_targets():
    with pytest.raises(ValueError, match="canary must be one of"):
        rollout_module.normalize_rollout_scope(["vm-01", "vm-02"], "vm-03")


def test_normalize_rollout_scope_rejects_empty_targets():
    with pytest.raises(ValueError, match="non-empty"):
        rollout_module.normalize_rollout_scope([], "vm-01")


def test_host_sequence_decision_proceeds_when_all_pass():
    assert rollout_module.host_sequence_decision("ready", "completed", "passed") == "proceed"


def test_host_sequence_decision_recovers_on_not_ready_preflight():
    assert rollout_module.host_sequence_decision("not_ready", "completed", "passed") == "recover"


def test_host_sequence_decision_recovers_on_failed_patch():
    assert rollout_module.host_sequence_decision("ready", "failed", "passed") == "recover"


def test_host_sequence_decision_recovers_on_failed_verify():
    assert rollout_module.host_sequence_decision("ready", "completed", "failed") == "recover"


def test_host_sequence_decision_recovers_on_error_preflight():
    assert rollout_module.host_sequence_decision("error", "completed", "passed") == "recover"


def test_rollout_should_stop_when_any_host_needs_recovery():
    hosts = {
        "vm-01": make_host("vm-01", action="proceed"),
        "vm-02": make_host("vm-02", patch="failed", action="recover"),
        "vm-03": make_host("vm-03", action="proceed"),
    }
    assert rollout_module.rollout_should_stop(list(hosts.values())) is True


def test_rollout_should_not_stop_when_all_proceed():
    hosts = {
        "vm-01": make_host("vm-01", action="proceed"),
        "vm-02": make_host("vm-02", action="proceed"),
    }
    assert rollout_module.rollout_should_stop(list(hosts.values())) is False


def test_rollout_result_summary_counts():
    hosts = {
        "vm-01": make_host("vm-01", action="proceed"),
        "vm-02": make_host("vm-02", patch="failed", action="recover"),
    }
    result = rollout_module.rollout_result(["vm-01", "vm-02"], "vm-01", hosts)
    assert result["summary"]["total"] == 2
    assert result["summary"]["completed"] == 1
    assert result["summary"]["failed"] == 1
    assert result["summary"]["stopped_early"] is True


def test_error_result_matches_contract():
    record = rollout_module.error_result("Rollout failed (RuntimeError)")
    assert validate_rollout_contract(record) is None
    assert record["error"]["code"] == "rollout_error"


def test_contract_accepts_full_successful_rollout():
    hosts = {
        "vm-01": make_host("vm-01", action="proceed"),
        "vm-02": make_host("vm-02", action="proceed"),
        "vm-03": make_host("vm-03", action="proceed"),
    }
    data = envelope(hosts, ["vm-01", "vm-02", "vm-03"], "vm-01")
    assert validate_rollout_contract(data) is None


def test_contract_accepts_stopped_early_with_recovery():
    hosts = {
        "vm-01": make_host("vm-01", action="proceed"),
        "vm-02": make_host("vm-02", patch="failed", action="recover",
                           blocking=["patch"], error=None),
    }
    data = envelope(hosts, ["vm-01", "vm-02"], "vm-01")
    assert validate_rollout_contract(data) is None


def test_contract_rejects_canary_not_in_targets():
    hosts = {"vm-01": make_host("vm-01", action="proceed")}
    data = envelope(hosts, ["vm-01"], "vm-02")
    with pytest.raises(ValueError, match="canary must be one of"):
        validate_rollout_contract(data)


def test_contract_rejects_proceed_host_with_blocking():
    hosts = {
        "vm-01": make_host("vm-01", action="proceed", blocking=["patch"]),
    }
    data = envelope(hosts, ["vm-01"], "vm-01")
    with pytest.raises((ValueError, ValidationError)):
        validate_rollout_contract(data)


def test_contract_rejects_proceed_host_with_failed_preflight():
    hosts = {
        "vm-01": make_host("vm-01", preflight="not_ready", action="proceed"),
    }
    data = envelope(hosts, ["vm-01"], "vm-01")
    with pytest.raises((ValueError, ValidationError)):
        validate_rollout_contract(data)


def test_contract_rejects_proceed_host_with_failed_patch():
    hosts = {
        "vm-01": make_host("vm-01", patch="failed", action="proceed"),
    }
    data = envelope(hosts, ["vm-01"], "vm-01")
    with pytest.raises((ValueError, ValidationError)):
        validate_rollout_contract(data)


def test_contract_rejects_proceed_host_with_failed_verify():
    hosts = {
        "vm-01": make_host("vm-01", verify="failed", action="proceed"),
    }
    data = envelope(hosts, ["vm-01"], "vm-01")
    with pytest.raises((ValueError, ValidationError)):
        validate_rollout_contract(data)


def test_contract_rejects_recover_host_without_blocking():
    hosts = {
        "vm-01": make_host("vm-01", patch="failed", action="recover", blocking=[]),
    }
    data = envelope(hosts, ["vm-01"], "vm-01")
    with pytest.raises((ValueError, ValidationError)):
        validate_rollout_contract(data)


def test_contract_rejects_stopped_early_without_recovery():
    hosts = {
        "vm-01": make_host("vm-01", action="proceed"),
    }
    data = envelope(hosts, ["vm-01"], "vm-01")
    data["summary"]["stopped_early"] = True
    with pytest.raises(ValueError, match="no host needs recovery"):
        validate_rollout_contract(data)


def load_playbook(name):
    return yaml.safe_load((ROOT / "playbooks" / name).read_text(encoding="utf-8"))


def test_rollout_playbook_is_serial_and_no_mutation_modules():
    play = load_playbook("rollout.yml")[0]
    text = yaml.safe_dump(play)

    assert play["serial"] == 1
    assert play["become"] is True
    assert play["any_errors_fatal"] is False
    assert "preflight" in play["tasks"][0]
    assert "patch_packages" in play["tasks"][1]
    assert "verify_packages" in play["tasks"][2]
    assert "sequential_rollout" in play["tasks"][3]
    assert "recover_packages" in play["tasks"][4]

    gates = [task for task in play["tasks"] if "ansible.builtin.fail" in task]
    assert len(gates) == 1
    assert "when" in gates[0]

    # Recovery is conditional on the rollout decision
    recover_task = play["tasks"][4]
    assert "when" in recover_task
    assert "rollout_decision.action" in str(recover_task["when"])

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


def test_rollout_playbook_stops_on_recovery():
    play = load_playbook("rollout.yml")[0]
    fail_tasks = [t for t in play["tasks"] if "ansible.builtin.fail" in t]
    stop_fail = [t for t in fail_tasks if "Rollout stopped" in str(t)]
    assert stop_fail, "rollout.yml must stop when a host needs recovery"


def test_host_rollout_result_names_blocking_stages():
    record = rollout_module.host_rollout_result(
        "vm-01", "ready", "failed", "passed", {}, "recover")
    assert record["blocking"] == ["patch"]
    proceed = rollout_module.host_rollout_result(
        "vm-01", "ready", "completed", "passed", {}, "proceed")
    assert proceed["blocking"] == []
