from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from jsonschema import ValidationError
import pytest

from patch_agent.evidence import validate_evidence_contract, validate_evidence_readiness

FIXTURES = Path(__file__).parent / "fixtures/evidence"
NOW = datetime(2026, 10, 30, 9, 5, tzinfo=timezone.utc)
MAX_AGE = timedelta(minutes=5)  # Synthetic test policy, not a project default.


@pytest.fixture
def collection():
    return json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8"))


def check(collection, **overrides):
    options = {"targets": ["vm-01"], "max_age": MAX_AGE, "now": NOW}
    options.update(overrides)
    return validate_evidence_readiness(collection, **options)


def test_fresh_complete_collection_passes_without_mutation(collection):
    original = deepcopy(collection)
    assert check(collection) is None
    assert collection == original


def test_age_boundary_uses_each_host_not_only_collection_completion(collection):
    # Host is exactly five minutes old; the envelope completed two seconds later.
    check(collection)
    with pytest.raises(ValueError, match="host vm-01 evidence is stale"):
        check(collection, now=NOW + timedelta(microseconds=1))


def test_retimestamping_envelope_does_not_refresh_old_host_data(collection):
    collection["collected_at"] = "2026-10-30T09:05:00Z"
    collection["hosts"]["vm-01"]["collected_at"] = "2026-10-30T08:59:59Z"
    with pytest.raises(ValueError, match="host vm-01 evidence is stale"):
        check(collection)


def test_expired_collection_is_rejected(collection):
    with pytest.raises(ValueError, match="collection evidence is stale"):
        check(collection, now=NOW + timedelta(minutes=1))


def test_future_collection_is_rejected_without_clock_skew_allowance(collection):
    collection["collected_at"] = "2026-10-30T09:05:00.000001Z"
    with pytest.raises(ValueError, match="collection timestamp is in the future"):
        check(collection)


def test_timestamp_equal_to_now_is_accepted(collection):
    collection["collected_at"] = collection["hosts"]["vm-01"]["collected_at"]
    check(collection, now=datetime(2026, 10, 30, 9, tzinfo=timezone.utc))


def test_failed_host_remains_valid_diagnostics_but_cannot_pass_readiness():
    collection = json.loads((FIXTURES / "partial-error.json").read_text(encoding="utf-8"))
    validate_evidence_contract(collection)
    with pytest.raises(ValueError, match="host vm-02 inspection failed"):
        check(collection, targets=["vm-01", "vm-02"])


@pytest.mark.parametrize("change", ["missing_host", "empty_packages", "missing_timestamp"])
def test_incomplete_collection_is_rejected(collection, change):
    if change == "missing_host":
        collection["targets"].append("vm-02")
    elif change == "empty_packages":
        collection["hosts"]["vm-01"]["packages"] = {}
    else:
        del collection["hosts"]["vm-01"]["collected_at"]
    with pytest.raises((ValueError, ValidationError)):
        check(collection)


@pytest.mark.parametrize("targets", [["vm-01", "vm-02"], ["vm-02"]])
def test_collection_must_match_operator_request(collection, targets):
    with pytest.raises(ValueError, match="requested targets exactly"):
        check(collection, targets=targets)


def test_unrequested_host_cannot_be_hidden_in_valid_collection(collection):
    collection["targets"].append("vm-02")
    collection["hosts"]["vm-02"] = deepcopy(collection["hosts"]["vm-01"])
    with pytest.raises(ValueError, match="requested targets exactly"):
        check(collection)
    check(collection, targets=["vm-02", "vm-01"])  # Order is irrelevant.


def test_structurally_valid_unknown_inventory_host_is_rejected(collection):
    collection["targets"] = ["unknown-host"]
    collection["hosts"] = {"unknown-host": collection["hosts"]["vm-01"]}
    validate_evidence_contract(collection)
    with pytest.raises(ValueError, match="unknown inventory host"):
        check(collection, targets=["unknown-host"])


@pytest.mark.parametrize("targets", [[], ["vm-01", "vm-01"], "vm-01", [None]])
def test_invalid_operator_selection_is_rejected(collection, targets):
    with pytest.raises(ValueError, match="unique inventory hosts"):
        check(collection, targets=targets)


@pytest.mark.parametrize("max_age", [timedelta(0), timedelta(seconds=-1), 300, None])
def test_age_policy_must_be_explicit_and_positive(collection, max_age):
    with pytest.raises(ValueError, match="positive timedelta"):
        check(collection, max_age=max_age)


@pytest.mark.parametrize("now", [datetime(2026, 10, 30, 9, 5), "2026-10-30T09:05:00Z"])
def test_clock_must_be_timezone_aware(collection, now):
    with pytest.raises(ValueError, match="timezone-aware"):
        check(collection, now=now)


def test_equivalent_timezone_aware_clock_gives_same_result(collection):
    check(collection, now=NOW.astimezone(timezone(timedelta(hours=3))))


def test_default_clock_checks_old_evidence_instead_of_reusing_its_timestamp(collection):
    collection["collected_at"] = "2000-01-01T00:00:00Z"
    collection["hosts"]["vm-01"]["collected_at"] = "2000-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="stale"):
        check(collection, now=None)
