from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
import pytest

from patch_agent.evidence import EVIDENCE_VALIDATOR, validate_evidence_contract
from patch_agent.approval import validate_plan

FIXTURES = Path(__file__).parent / "fixtures/evidence"


@pytest.fixture
def collection():
    return json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8"))


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(EVIDENCE_VALIDATOR.schema)


@pytest.mark.parametrize("name", ["valid.json", "partial-error.json"])
def test_documented_examples_validate_without_mutating_input(name):
    evidence = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    original = deepcopy(evidence)
    assert validate_evidence_contract(evidence) is None
    assert evidence == original


def test_documented_missing_installed_version_is_rejected():
    evidence = json.loads((FIXTURES / "invalid-missing-installed.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError, match="installed"):
        validate_evidence_contract(evidence)


@pytest.mark.parametrize("field", ["schema_version", "collected_at", "targets", "hosts"])
def test_required_collection_fields(collection, field):
    del collection[field]
    with pytest.raises(ValidationError):
        validate_evidence_contract(collection)


@pytest.mark.parametrize("version", [2, "1", True])
def test_unknown_or_mistyped_schema_version(collection, version):
    collection["schema_version"] = version
    with pytest.raises(ValidationError):
        validate_evidence_contract(collection)


@pytest.mark.parametrize("targets", [[], ["vm-01", "vm-01"], ["vm-01\n"], ["../vm-01"]])
def test_invalid_target_selection(collection, targets):
    collection["targets"] = targets
    with pytest.raises(ValidationError):
        validate_evidence_contract(collection)


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_host_results_must_match_selected_targets(collection, change):
    if change == "missing":
        collection["targets"].append("vm-02")
    else:
        collection["hosts"]["vm-02"] = deepcopy(collection["hosts"]["vm-01"])
    with pytest.raises(ValueError, match="match exactly"):
        validate_evidence_contract(collection)


@pytest.mark.parametrize("timestamp", [
    "not-a-date", "2026-02-30T09:00:00Z", "2026-10-30T09:00:00",
    "2026-10-30T12:00:00+03:00", "2026-10-30T09:00:00Z\n",
])
@pytest.mark.parametrize("location", ["collection", "host"])
def test_timestamps_require_real_utc_dates(collection, timestamp, location):
    target = collection if location == "collection" else collection["hosts"]["vm-01"]
    target["collected_at"] = timestamp
    with pytest.raises((ValueError, ValidationError)):
        validate_evidence_contract(collection)


def test_host_timestamp_cannot_follow_collection_completion(collection):
    collection["hosts"]["vm-01"]["collected_at"] = "2026-10-30T09:00:03Z"
    with pytest.raises(ValueError, match="after collection completion"):
        validate_evidence_contract(collection)


@pytest.mark.parametrize("year", ["2000", "2100"])
def test_contract_validation_does_not_claim_freshness(collection, year):
    collection["collected_at"] = f"{year}-01-01T00:00:00.123456Z"
    collection["hosts"]["vm-01"]["collected_at"] = f"{year}-01-01T00:00:00Z"
    validate_evidence_contract(collection)


@pytest.mark.parametrize("change", ["empty_packages", "success_with_error", "failure_with_packages", "failure_without_error"])
def test_host_status_cannot_hide_failure_or_partial_packages(collection, change):
    host = collection["hosts"]["vm-01"]
    if change == "empty_packages":
        host["packages"] = {}
    elif change == "success_with_error":
        host["error"] = {"code": "partial", "message": "Inspection failed"}
    else:
        host["status"] = "error"
        if change == "failure_with_packages":
            host["error"] = {"code": "partial", "message": "Inspection failed"}
        else:
            host["packages"] = {}
    with pytest.raises(ValidationError):
        validate_evidence_contract(collection)


@pytest.mark.parametrize("change", ["missing_source", "no_origin", "numeric_version", "blank_version", "extra_field"])
def test_incomplete_or_ambiguous_package_data(collection, change):
    package = collection["hosts"]["vm-01"]["packages"]["demo-package:amd64"]
    if change == "missing_source":
        del package["source"]
    elif change == "no_origin":
        package["candidates"][0]["origins"] = []
    elif change == "numeric_version":
        package["installed"] = 1
    elif change == "blank_version":
        package["installed"] = " "
    else:
        package["command"] = "not permitted"
    with pytest.raises(ValidationError):
        validate_evidence_contract(collection)


def test_same_version_from_two_origins_is_one_candidate(collection):
    candidates = collection["hosts"]["vm-01"]["packages"]["demo-package:amd64"]["candidates"]
    duplicate = deepcopy(candidates[0])
    duplicate["origins"][0]["suite"] = "bookworm-security"
    candidates.append(duplicate)
    with pytest.raises(ValueError, match="candidate versions must be unique"):
        validate_evidence_contract(collection)
    candidates[0]["origins"].extend(candidates.pop()["origins"])
    validate_evidence_contract(collection)


@pytest.mark.parametrize("uri", [
    "https://", "file://", "https://[broken]", "https://repo.example.invalid:invalid/debian",
    "https://user:password@repo.example.invalid/debian",
])
def test_invalid_or_credential_bearing_repository_origin(collection, uri):
    package = collection["hosts"]["vm-01"]["packages"]["demo-package:amd64"]
    package["candidates"][0]["origins"][0]["uri"] = uri
    with pytest.raises(ValueError):
        validate_evidence_contract(collection)


def test_local_file_repository_origin_is_supported(collection):
    package = collection["hosts"]["vm-01"]["packages"]["demo-package:amd64"]
    package["candidates"][0]["origins"][0]["uri"] = "file:///srv/apt-mirror"
    validate_evidence_contract(collection)


def test_multiarch_identity_and_unknown_source_are_explicit(collection):
    packages = collection["hosts"]["vm-01"]["packages"]
    packages["demo-package:arm64"] = deepcopy(packages["demo-package:amd64"])
    packages["demo-package:arm64"]["source"] = None
    packages["demo-package:arm64"]["candidates"] = []
    validate_evidence_contract(collection)
    assert packages["demo-package:amd64"]["installed"] == "1:1.0-1"
    packages["demo-package"] = packages.pop("demo-package:arm64")
    with pytest.raises(ValidationError):
        validate_evidence_contract(collection)


def test_new_envelope_does_not_silently_replace_legacy_approval_evidence(collection, plan):
    with pytest.raises(ValueError, match="unknown target"):
        validate_plan(plan, collection)
