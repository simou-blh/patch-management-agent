import hashlib
import importlib.util
from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError

from patch_agent.policies import load_default_policy, validate_policies
from patch_agent.preflight import validate_preflight_contract

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "playbooks/library/preflight.py"

spec = importlib.util.spec_from_file_location("preflight_module", MODULE_PATH)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)

DPKG_SAMPLE = (
    "curl\t7.88.1-10\tamd64\n"
    "libc6:amd64\t2.36-9+deb12u4\tamd64\n"
    "demo-package\t1.0-1\tall\n"
)

POLICY_SAMPLE = """\
curl:
  Installed: 7.88.1-10
  Candidate: 7.88.1-10+deb12u1
  Version table:
 *** 7.88.1-10 100
        100 /var/lib/dpkg/status
     7.88.1-10+deb12u1 500
        500 https://deb.debian.org/debian bookworm-security/main amd64 Packages
"""

EXPECTATION = {
    "name": "curl",
    "architecture": "amd64",
    "expected_installed": "7.88.1-10",
    "target_version": "7.88.1-10+deb12u1",
}


def passing_checks():
    return [
        preflight.check_privileges(0),
        preflight.check_disk(["/"], 100, usage=lambda path: (1000, 400, 600)),
        preflight.check_locks(["/lock"], probe=lambda path: False),
        preflight.check_apt_health("", 0),
        preflight.check_drift(
            preflight.parse_installed(DPKG_SAMPLE), [EXPECTATION]
        ),
        preflight.check_candidates(
            preflight.parse_policy_versions(POLICY_SAMPLE), [EXPECTATION]
        ),
    ]


def verified_backup():
    return {"status": "verified", "detail": "Backed up 1 file", "files": []}


def verified_recovery():
    return {"status": "verified", "detail": "Verified 1 artifact", "artifacts": []}


def envelope(record):
    return {
        "schema_version": 1,
        "collected_at": record["collected_at"],
        "targets": ["vm-01"],
        "hosts": {"vm-01": record},
    }


def test_privileges_require_root():
    assert preflight.check_privileges(0)["status"] == "pass"
    failed = preflight.check_privileges(1000)
    assert failed["status"] == "fail"
    assert failed["data"]["euid"] == 1000


def test_disk_check_passes_and_fails_against_the_threshold():
    usage = lambda path: (1000, 400, 600)
    assert preflight.check_disk(["/"], 500, usage=usage)["status"] == "pass"
    assert preflight.check_disk(["/"], 700, usage=usage)["status"] == "fail"


def test_disk_check_reports_an_unreadable_path():
    def usage(path):
        raise FileNotFoundError(path)

    check = preflight.check_disk(["/missing"], 100, usage=usage)
    assert check["status"] == "error"
    assert check["data"]["paths"][0]["detail"] == "FileNotFoundError"


def test_lock_check_passes_when_free_and_fails_when_held():
    assert preflight.check_locks(["/lock"], probe=lambda path: False)["status"] == "pass"
    held = preflight.check_locks(["/lock"], probe=lambda path: True)
    assert held["status"] == "fail"
    assert held["data"]["locks"][0]["detail"] == "lock is held"


def test_lock_probe_failure_is_an_error_not_a_pass():
    def probe(path):
        raise PermissionError(path)

    check = preflight.check_locks(["/lock"], probe=probe)
    assert check["status"] == "error"


def test_apt_health_interpretation():
    assert preflight.check_apt_health("", 0)["status"] == "pass"
    assert preflight.check_apt_health("", 1)["status"] == "error"
    unhealthy = preflight.check_apt_health("Missing files:\n  /var/lib/dpkg/info/x.list\n", 0)
    assert unhealthy["status"] == "fail"
    assert unhealthy["data"]["issues"] == 2


def test_parse_installed_is_architecture_qualified():
    assert preflight.parse_installed(DPKG_SAMPLE) == {
        "curl:amd64": "7.88.1-10",
        "libc6:amd64": "2.36-9+deb12u4",
        "demo-package:all": "1.0-1",
    }


def test_drift_passes_for_the_exact_approved_version():
    check = preflight.check_drift(preflight.parse_installed(DPKG_SAMPLE), [EXPECTATION])
    assert check["status"] == "pass"
    assert check["data"]["packages"][0]["observed_installed"] == "7.88.1-10"


def test_drift_fails_when_the_installed_version_changed():
    installed = {"curl:amd64": "7.88.1-11"}
    check = preflight.check_drift(installed, [EXPECTATION])
    assert check["status"] == "fail"
    assert check["data"]["packages"][0]["detail"] == (
        "installed version differs from the approved version"
    )


def test_drift_fails_when_the_package_is_missing():
    check = preflight.check_drift({}, [EXPECTATION])
    assert check["status"] == "fail"
    assert check["data"]["packages"][0]["detail"] == "package is not installed"


def test_drift_fails_when_architecture_is_ambiguous():
    installed = {"curl:amd64": "7.88.1-10", "curl:i386": "7.88.1-10"}
    expectation = {**EXPECTATION, "architecture": None}
    check = preflight.check_drift(installed, [expectation])
    assert check["status"] == "fail"
    assert check["data"]["packages"][0]["detail"] == (
        "multiple installed architectures; specify architecture"
    )


def test_drift_and_candidates_are_skipped_without_expectations():
    assert preflight.check_drift({}, [])["status"] == "skipped"
    assert preflight.check_candidates({}, [])["status"] == "skipped"


def test_policy_versions_ignore_dpkg_status_and_unsupported_origins():
    policy = """\
curl:
  Installed: 7.88.1-10
  Version table:
     7.88.1-10 100
        100 /var/lib/dpkg/status
     7.88.1-10+deb12u1 500
        500 cdrom://media/cdrom bookworm/main amd64 Packages
     7.88.1-10+deb12u2 500
        500 file:/srv/apt-mirror bookworm/main amd64 Packages
"""
    assert preflight.parse_policy_versions(policy) == {
        "curl": {"7.88.1-10+deb12u2": {"amd64"}}
    }


def test_candidates_pass_and_fail_against_available_versions():
    available = preflight.parse_policy_versions(POLICY_SAMPLE)
    assert preflight.check_candidates(available, [EXPECTATION])["status"] == "pass"

    missing = {**EXPECTATION, "target_version": "9.9.9"}
    check = preflight.check_candidates(available, [missing])
    assert check["status"] == "fail"
    assert check["data"]["packages"][0]["available_versions"] == ["7.88.1-10+deb12u1"]


def test_candidates_are_filtered_by_installed_architecture():
    policy = """\
curl:
  Version table:
     9.0-1 500
        500 https://repo.example.invalid/debian bookworm/main i386 Packages
     9.0-2 500
        500 https://repo.example.invalid/debian bookworm/main all Packages
"""
    available = preflight.parse_policy_versions(policy)

    wrong_arch = {**EXPECTATION, "target_version": "9.0-1"}
    assert preflight.check_candidates(available, [wrong_arch])["status"] == "fail"

    any_arch = {**EXPECTATION, "target_version": "9.0-2"}
    assert preflight.check_candidates(available, [any_arch])["status"] == "pass"

    unspecified = {**EXPECTATION, "architecture": None, "target_version": "9.0-1"}
    assert preflight.check_candidates(available, [unspecified])["status"] == "pass"


def test_expectation_validation_rejects_bad_scope():
    with pytest.raises(ValueError, match="invalid package name"):
        preflight.normalize_expectations([{"name": "Bad Name", "expected_installed": "1", "target_version": "2"}])
    with pytest.raises(ValueError, match="duplicate expectation"):
        preflight.normalize_expectations([EXPECTATION, EXPECTATION])
    with pytest.raises(ValueError, match="non-empty version"):
        preflight.normalize_expectations([{**EXPECTATION, "target_version": " "}])


def test_backup_copies_files_and_records_checksums(tmp_path):
    source = tmp_path / "configs"
    source.mkdir()
    (source / "demo.conf").write_bytes(b"setting=1\n")
    backup_root = tmp_path / "backups"

    record = preflight.backup_configs(
        [str(source)], str(backup_root), "vm-01", "2026-11-06T12:00:00Z", 1024 * 1024
    )

    assert record["status"] == "verified"
    assert len(record["files"]) == 1
    entry = record["files"][0]
    assert entry["sha256"] == hashlib.sha256(b"setting=1\n").hexdigest()
    assert Path(entry["backup"]).read_text(encoding="utf-8") == "setting=1\n"
    assert Path(entry["backup"]).is_relative_to(backup_root / "vm-01" / "20261106T120000Z")


def test_backup_is_not_attempted_without_a_root_or_paths(tmp_path):
    assert preflight.backup_configs([], None, "vm-01", "2026-11-06T12:00:00Z", 1)["status"] == (
        "not_attempted"
    )
    assert preflight.backup_configs([], str(tmp_path), "vm-01", "2026-11-06T12:00:00Z", 1)["status"] == (
        "not_attempted"
    )


def test_backup_rejects_relative_missing_and_oversized_paths(tmp_path):
    relative = preflight.backup_configs(
        ["relative/path"], str(tmp_path), "vm-01", "2026-11-06T12:00:00Z", 1024
    )
    assert relative["status"] == "failed"
    assert "absolute" in relative["detail"]

    missing = preflight.backup_configs(
        [str(tmp_path / "missing")], str(tmp_path), "vm-01", "2026-11-06T12:00:00Z", 1024
    )
    assert missing["status"] == "failed"
    assert "not found" in missing["detail"]

    large = tmp_path / "large.conf"
    large.write_text("x" * 100, encoding="utf-8")
    oversized = preflight.backup_configs(
        [str(large)], str(tmp_path), "vm-01", "2026-11-06T12:00:00Z", 10
    )
    assert oversized["status"] == "failed"
    assert "max_backup_bytes" in oversized["detail"]


def test_recovery_artifacts_are_verified_with_checksums(tmp_path):
    artifact = tmp_path / "curl.deb"
    artifact.write_bytes(b"deb-bytes")
    digest = hashlib.sha256(b"deb-bytes").hexdigest()

    record = preflight.check_recovery_artifacts(
        str(tmp_path), [{"name": "curl.deb", "sha256": digest}]
    )

    assert record["status"] == "verified"
    assert record["artifacts"] == [
        {"name": "curl.deb", "sha256": digest, "size": len(b"deb-bytes")}
    ]


def test_recovery_artifacts_reject_missing_escaping_and_mismatched_files(tmp_path):
    missing = preflight.check_recovery_artifacts(str(tmp_path), [{"name": "missing.deb"}])
    assert missing["status"] == "failed"
    assert "not found" in missing["detail"]

    escaping = preflight.check_recovery_artifacts(str(tmp_path), [{"name": "../outside.deb"}])
    assert escaping["status"] == "failed"
    assert "relative path" in escaping["detail"]

    artifact = tmp_path / "curl.deb"
    artifact.write_bytes(b"deb-bytes")
    mismatch = preflight.check_recovery_artifacts(
        str(tmp_path), [{"name": "curl.deb", "sha256": "0" * 64}]
    )
    assert mismatch["status"] == "failed"
    assert "checksum mismatch" in mismatch["detail"]


def test_recovery_artifacts_are_not_attempted_without_configuration(tmp_path):
    assert preflight.check_recovery_artifacts(None, [{"name": "x.deb"}])["status"] == (
        "not_attempted"
    )
    assert preflight.check_recovery_artifacts(str(tmp_path), [])["status"] == "not_attempted"


def test_ready_requires_every_check_and_preparation():
    ready = preflight.host_record(passing_checks(), verified_backup(), verified_recovery())
    assert ready["status"] == "ready"
    assert ready["blocking"] == []
    assert validate_preflight_contract(envelope(ready)) is None

    blocked = preflight.host_record(
        passing_checks(),
        {"status": "not_attempted", "detail": "No backup", "files": []},
        verified_recovery(),
    )
    assert blocked["status"] == "not_ready"
    assert blocked["blocking"] == ["backup"]
    assert validate_preflight_contract(envelope(blocked)) is None


def test_a_failed_check_blocks_readiness():
    checks = passing_checks()
    checks[3] = preflight.check_apt_health("", 1)
    record = preflight.host_record(checks, verified_backup(), verified_recovery())
    assert record["status"] == "not_ready"
    assert record["blocking"] == ["apt_health"]


def test_missing_checks_block_readiness():
    record = preflight.host_record(
        passing_checks()[:3], verified_backup(), verified_recovery()
    )
    assert record["status"] == "not_ready"
    assert "missing:apt_health" in record["blocking"]


def test_error_record_matches_the_contract():
    record = preflight.error_record("preflight_error", "Preflight failed (RuntimeError)")
    assert validate_preflight_contract(envelope(record)) is None
    assert record["status"] == "error" and record["checks"] == []


def test_contract_rejects_a_ready_host_without_preparation():
    record = preflight.host_record(passing_checks(), verified_backup(), verified_recovery())
    record["backup"] = {"status": "not_attempted", "detail": "No backup", "files": []}
    with pytest.raises(ValueError, match="verified configuration backup"):
        validate_preflight_contract(envelope(record))


def test_contract_rejects_mismatched_targets():
    record = preflight.host_record(passing_checks(), verified_backup(), verified_recovery())
    data = envelope(record)
    data["targets"] = ["vm-02"]
    with pytest.raises(ValueError, match="match exactly"):
        validate_preflight_contract(data)


def load_playbook(name):
    return yaml.safe_load((ROOT / "playbooks" / name).read_text(encoding="utf-8"))


def test_preflight_playbook_emits_readiness_without_mutation_modules():
    play = load_playbook("preflight.yml")[0]
    text = yaml.safe_dump(play)

    assert play["become"] is True
    assert play["any_errors_fatal"] is False
    assert "preflight" in play["tasks"][0]
    assert "'schema_version': 1" in text
    assert "'targets': ansible_play_hosts_all" in text
    assert "fleet_preflight" in text

    gates = [task for task in play["tasks"] if "ansible.builtin.fail" in task]
    assert len(gates) == 1
    assert "when" in gates[0]

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


def test_default_service_policies_are_valid():
    policy = load_default_policy()
    assert policy["restart_policy"] == "configured-only"
    assert policy["packages"]["openssh-server"]["services"] == ["ssh"]
    assert policy["services"]["ssh"]["health_checks"] == [
        {"type": "tcp", "host": "127.0.0.1", "port": 22, "timeout_seconds": 5}
    ]


def test_policies_reject_unconfigured_service_references():
    policy = load_default_policy()
    policy["packages"]["openssh-server"]["services"] = ["not-configured"]
    with pytest.raises(ValueError, match="unconfigured services"):
        validate_policies(policy)


def test_policies_reject_unknown_fields_and_restart_values():
    policy = load_default_policy()
    policy["services"]["ssh"]["extra"] = True
    with pytest.raises(ValidationError):
        validate_policies(policy)

    policy = load_default_policy()
    policy["services"]["ssh"]["restart"] = "always"
    with pytest.raises(ValidationError):
        validate_policies(policy)


def _download_stub(created):
    """Pretend apt-get download wrote the files in ``created`` into cwd."""
    from types import SimpleNamespace

    calls = []

    def run(command, cwd=None, timeout=None):
        calls.append(command)
        for name in created.get(command[-1], []):
            (Path(cwd) / name).write_bytes(b"deb")
        return SimpleNamespace(returncode=0 if command[-1] in created else 100, stdout="", stderr="")

    return run, calls


def test_cache_previous_packages_downloads_installed_version(tmp_path):
    expectations = preflight.normalize_expectations([
        {"name": "openssh-server", "architecture": "amd64",
         "expected_installed": "1:9.2p1-2+deb12u3", "target_version": "1:9.2p1-2+deb12u4"},
    ])
    run, calls = _download_stub({
        "openssh-server:amd64=1:9.2p1-2+deb12u3": ["openssh-server_1%3a9.2p1-2+deb12u3_amd64.deb"],
    })
    specs, errors = preflight.cache_previous_packages(str(tmp_path / "cache"), expectations, run)
    assert errors == []
    assert calls == [["apt-get", "download", "openssh-server:amd64=1:9.2p1-2+deb12u3"]]
    assert specs == [{"name": "openssh-server_1%3a9.2p1-2+deb12u3_amd64.deb"}]
    verified = preflight.check_recovery_artifacts(str(tmp_path / "cache"), specs)
    assert verified["status"] == "verified"


def test_cache_previous_packages_reports_unobtainable_version(tmp_path):
    expectations = preflight.normalize_expectations([
        {"name": "curl", "expected_installed": "7.88.1-10", "target_version": "7.88.1-10+deb12u1"},
    ])
    run, _ = _download_stub({})
    specs, errors = preflight.cache_previous_packages(str(tmp_path), expectations, run)
    assert specs == [] and "could not be downloaded" in errors[0]


def test_cache_previous_packages_rejects_relative_dir():
    specs, errors = preflight.cache_previous_packages("cache", [], None)
    assert specs == [] and errors
