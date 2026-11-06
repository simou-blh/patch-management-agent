from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from jsonschema import ValidationError
import pytest

from patch_agent.collector import publish_evidence, read_evidence
from patch_agent.evidence import evidence_max_age

ROOT = Path(__file__).resolve().parent.parent


def test_publish_preserves_source_timestamps_and_private_file_mode(tmp_path, evidence):
    original = deepcopy(evidence)
    result = publish_evidence(evidence, targets=evidence["targets"], directory=tmp_path)
    assert result == tmp_path / "evidence.json"
    assert read_evidence(result) == original == evidence
    assert not (tmp_path / "evidence.lock").exists()
    assert not list(tmp_path.glob(".evidence-*.tmp"))
    if os.name != "nt":
        assert result.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("failure", ["stale", "failed_host", "missing_host", "schema"])
def test_invalid_import_leaves_previous_collection_intact(tmp_path, evidence, failure):
    publish_evidence(evidence, targets=evidence["targets"], directory=tmp_path)
    previous = (tmp_path / "evidence.json").read_bytes()
    broken = deepcopy(evidence)
    if failure == "stale":
        broken["collected_at"] = "2000-01-01T00:00:00Z"
        for host in broken["hosts"].values():
            host["collected_at"] = broken["collected_at"]
    elif failure == "failed_host":
        broken["hosts"]["vm-02"].update(status="error", packages={},
            error={"code": "timeout", "message": "Synthetic inspection failure"})
    elif failure == "missing_host":
        del broken["hosts"]["vm-02"]
    else:
        broken["schema_version"] = 2
    with pytest.raises((ValueError, ValidationError)):
        publish_evidence(broken, targets=evidence["targets"], directory=tmp_path)
    assert (tmp_path / "evidence.json").read_bytes() == previous
    assert not (tmp_path / "evidence.lock").exists()


def test_interrupted_replace_preserves_previous_data_and_cleans_staging(
        tmp_path, evidence, monkeypatch):
    publish_evidence(evidence, targets=evidence["targets"], directory=tmp_path)
    before = (tmp_path / "evidence.json").read_bytes()

    def fail_replace(*args):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr("patch_agent.collector.os.replace", fail_replace)
    with pytest.raises(OSError):
        publish_evidence(evidence, targets=evidence["targets"], directory=tmp_path)
    assert (tmp_path / "evidence.json").read_bytes() == before
    assert not list(tmp_path.glob(".evidence-*.tmp"))
    assert not (tmp_path / "evidence.lock").exists()


def test_expiry_during_write_does_not_publish(tmp_path, evidence, monkeypatch):
    from patch_agent.evidence import validate_evidence_readiness

    calls = []

    def expire_before_replace(document, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise ValueError("collection evidence is stale")
        validate_evidence_readiness(document, **kwargs)

    monkeypatch.setattr("patch_agent.collector.validate_evidence_readiness", expire_before_replace)
    with pytest.raises(ValueError, match="stale"):
        publish_evidence(evidence, targets=evidence["targets"], directory=tmp_path)
    assert not (tmp_path / "evidence.json").exists()
    assert not list(tmp_path.glob(".evidence-*.tmp"))
    assert not (tmp_path / "evidence.lock").exists()


def test_concurrent_import_fails_without_removing_other_publishers_lock(tmp_path, evidence):
    lock = tmp_path / "evidence.lock"
    lock.write_text("another import", encoding="utf-8")
    with pytest.raises(ValueError, match="already locked"):
        publish_evidence(evidence, targets=evidence["targets"], directory=tmp_path)
    assert lock.read_text(encoding="utf-8") == "another import"
    assert not (tmp_path / "evidence.json").exists()


@pytest.mark.parametrize("regression", ["collection", "host"])
def test_late_older_results_cannot_replace_newer_results(tmp_path, evidence, regression):
    publish_evidence(evidence, targets=evidence["targets"], directory=tmp_path)
    older = deepcopy(evidence)
    timestamp = (datetime.fromisoformat(evidence["collected_at"]) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    for host in older["hosts"].values():
        host["collected_at"] = timestamp
    if regression == "collection":
        older["collected_at"] = timestamp
    with pytest.raises(ValueError, match="newer evidence"):
        publish_evidence(older, targets=evidence["targets"], directory=tmp_path)
    assert read_evidence(tmp_path / "evidence.json") == evidence


@pytest.mark.parametrize("value", ["", "0", "-1", "1.5", "NaN", "inf", " 300", "٣٠٠", "999999999999999999999"])
def test_missing_or_invalid_age_policy_blocks_import(tmp_path, evidence, monkeypatch, value):
    monkeypatch.setenv("PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS", value)
    with pytest.raises(ValueError, match="PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS"):
        publish_evidence(evidence, targets=evidence["targets"], directory=tmp_path)
    assert not (tmp_path / "evidence.json").exists()


def test_no_implicit_age_policy(monkeypatch):
    monkeypatch.delenv("PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS")
    with pytest.raises(ValueError, match="PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS"):
        evidence_max_age()


def test_operator_cli_imports_into_configured_state_directory(tmp_path, evidence):
    source = tmp_path / "inspection.json"
    source.write_text(json.dumps(evidence), encoding="utf-8")
    state = tmp_path / "state"
    env = {**os.environ, "PATCH_AGENT_DATA_DIR": str(state)}
    result = subprocess.run([sys.executable, "-m", "patch_agent.collector", str(source),
        "--targets", *evidence["targets"]], cwd=ROOT, env=env, capture_output=True,
        text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert read_evidence(state / "evidence.json") == evidence
    assert "Published validated inspection evidence" in result.stdout


def test_malformed_source_fails_without_echoing_contents(tmp_path):
    source = tmp_path / "inspection.json"
    source.write_text("not-json secret-value", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "patch_agent.collector", str(source),
        "--targets", "vm-01"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "could not be read as JSON" in result.stderr
    assert "secret-value" not in result.stderr
