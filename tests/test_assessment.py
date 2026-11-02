import copy
import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from patch_agent.assessment import validate_advisory_cache, validate_assessment_result

FIXTURES = Path(__file__).parent / "fixtures" / "assessment"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def cache():
    return load("advisory-cache-valid.json")


@pytest.fixture
def assessment():
    return load("assessment-valid.json")


def test_valid_fixtures_pass(cache, assessment):
    validate_advisory_cache(cache)
    validate_assessment_result(assessment)


def test_validators_do_not_mutate_input(cache, assessment):
    before = copy.deepcopy((cache, assessment))
    validate_advisory_cache(cache)
    validate_assessment_result(assessment)
    assert (cache, assessment) == before


# ---- advisory cache ---------------------------------------------------------

def cache_shape_cases():
    def unknown_field(c): c["extra"] = 1
    def bad_version(c): c["schema_version"] = 2
    def missing_packages(c): del c["packages"]
    def empty_packages(c): c["packages"] = {}
    def offset_time(c): c["fetched_at"] = "2026-10-30T08:00:00+01:00"
    def bad_source_name(c): c["packages"] = {"Bad Name": c["packages"]["demo-source"]}
    def resolved_without_fix(c): c["packages"]["demo-source"][0]["fixed_version"] = None
    def open_with_fix(c): c["packages"]["open-source"][0]["fixed_version"] = "2.0-2"
    def unknown_status(c): c["packages"]["demo-source"][0]["status"] = "fixed"
    def unknown_urgency(c): c["packages"]["demo-source"][0]["urgency"] = "urgent"
    def whitespace_version(c): c["packages"]["demo-source"][0]["fixed_version"] = "1.0 2"
    def empty_advisory_list(c): c["packages"]["demo-source"] = []
    def non_http_source(c): c["source"]["uri"] = "ftp://example.invalid/data"
    return [unknown_field, bad_version, missing_packages, empty_packages, offset_time, bad_source_name,
            resolved_without_fix, open_with_fix, unknown_status, unknown_urgency, whitespace_version,
            empty_advisory_list, non_http_source]


@pytest.mark.parametrize("mutate", cache_shape_cases(), ids=lambda f: f.__name__)
def test_advisory_cache_shape_errors(cache, mutate):
    mutate(cache)
    with pytest.raises(ValidationError):
        validate_advisory_cache(cache)


def cache_consistency_cases():
    def duplicate_id(c): c["packages"]["demo-source"].append(dict(c["packages"]["demo-source"][0]))
    def unparseable_fix(c): c["packages"]["demo-source"][0]["fixed_version"] = "abc"
    def credentials(c): c["source"]["uri"] = "https://user:pw@security-tracker.debian.org/data.json"
    def impossible_date(c): c["fetched_at"] = "2026-02-30T00:00:00Z"
    def bad_port(c): c["source"]["uri"] = "https://security-tracker.debian.org:99999/data.json"
    return [duplicate_id, unparseable_fix, credentials, impossible_date, bad_port]


@pytest.mark.parametrize("mutate", cache_consistency_cases(), ids=lambda f: f.__name__)
def test_advisory_cache_consistency_errors(cache, mutate):
    mutate(cache)
    with pytest.raises(ValueError):
        validate_advisory_cache(cache)


def test_not_affected_marker_zero_is_a_valid_fixed_version(cache):
    cache["packages"]["demo-source"][0]["fixed_version"] = "0"
    validate_advisory_cache(cache)


# ---- assessment result ------------------------------------------------------

def assessment_shape_cases():
    def unknown_field(a): a["results"][0]["extra"] = 1
    def bad_version(a): a["schema_version"] = 2
    def empty_results(a): a["results"] = []
    def missing_decision(a): del a["results"][0]["decision"]
    def unknown_status(a): a["results"][0]["status"] = "vulnerable"
    def unknown_reason(a): a["results"][0]["findings"][0]["reason"] = "because"
    def patch_without_version(a): a["results"][0]["decision"]["proposed_version"] = None
    def defer_with_version(a): a["results"][2]["decision"]["proposed_version"] = "2.0-2"
    def bad_priority(a): a["results"][0]["decision"]["priority"] = "urgent"
    def blank_reason(a): a["results"][0]["decision"]["reason"] = "  "
    def bad_host(a): a["results"][0]["host"] = "VM 01"
    def unqualified_package(a): a["results"][0]["package"] = "demo-package"
    def omitted_source(a): del a["results"][0]["source"]
    return [unknown_field, bad_version, empty_results, missing_decision, unknown_status, unknown_reason,
            patch_without_version, defer_with_version, bad_priority, blank_reason, bad_host,
            unqualified_package, omitted_source]


@pytest.mark.parametrize("mutate", assessment_shape_cases(), ids=lambda f: f.__name__)
def test_assessment_shape_errors(assessment, mutate):
    mutate(assessment)
    with pytest.raises(ValidationError):
        validate_assessment_result(assessment)


def assessment_consistency_cases():
    def duplicate_result(a): a["results"].append(copy.deepcopy(a["results"][0]))
    def assessed_before_evidence(a): a["evidence_collected_at"] = "2026-10-30T09:31:00Z"
    def assessed_before_advisories(a): a["advisory_fetched_at"] = "2026-10-30T09:31:00Z"
    def impossible_date(a): a["assessed_at"] = "2026-02-30T00:00:00Z"
    def status_not_from_findings(a): a["results"][0]["status"] = "fixed"
    def affected_but_installed_is_fixed(a): a["results"][0]["installed"] = "1:1.0-3"
    def fixed_but_installed_is_older(a): a["results"][1]["installed"] = "1:1.0-1"
    def reason_status_mismatch(a): a["results"][0]["findings"][0]["status"] = "uncertain"
    def before_fix_without_fix(a): a["results"][0]["findings"][0]["fixed_version"] = None
    def open_with_fix(a): a["results"][2]["findings"][0]["fixed_version"] = "2.0-2"
    def fixed_with_decision(a): a["results"][1]["decision"] = {"action": "defer", "proposed_version": None, "priority": "low", "reason": "x"}
    def affected_without_decision(a): a["results"][0]["decision"] = None
    def patch_below_fix(a): a["results"][0]["decision"]["proposed_version"] = "1:1.0-1+deb12u1"
    def patch_with_unfixed_finding(a):
        a["results"][2]["decision"] = {"action": "patch", "proposed_version": "2.0-2", "priority": "low", "reason": "x"}
    def patch_uncertain(a):
        a["results"][3]["decision"] = {"action": "patch", "proposed_version": "3.1-2", "priority": "low", "reason": "x"}
    def no_findings_with_known_source(a): a["results"][3]["source"] = {"name": "mystery-source", "version": "3.1-1"}
    def invalid_reason_but_version_parses(a):
        a["results"][3]["findings"] = [{"advisory_id": "CVE-2026-0003", "status": "uncertain", "fixed_version": None, "urgency": "low", "reason": "version_invalid"}]
    def fixed_without_findings(a):
        a["results"][1]["findings"] = []
    return [duplicate_result, assessed_before_evidence, assessed_before_advisories, impossible_date,
            status_not_from_findings, affected_but_installed_is_fixed, fixed_but_installed_is_older,
            reason_status_mismatch, before_fix_without_fix, open_with_fix, fixed_with_decision,
            affected_without_decision, patch_below_fix, patch_with_unfixed_finding, patch_uncertain,
            no_findings_with_known_source, invalid_reason_but_version_parses, fixed_without_findings]


@pytest.mark.parametrize("mutate", assessment_consistency_cases(), ids=lambda f: f.__name__)
def test_assessment_consistency_errors(assessment, mutate):
    mutate(assessment)
    with pytest.raises(ValueError):
        validate_assessment_result(assessment)


def test_unparseable_installed_version_is_uncertain(assessment):
    result = assessment["results"][3]
    result["installed"] = "not-a-version"
    result["source"] = {"name": "mystery-source", "version": "x"}
    result["findings"] = [{"advisory_id": "CVE-2026-0003", "status": "uncertain", "fixed_version": None,
                           "urgency": "medium", "reason": "version_invalid"}]
    validate_assessment_result(assessment)


def test_undetermined_advisory_can_be_deferred(assessment):
    result = assessment["results"][3]
    result["source"] = {"name": "pending-source", "version": "3.1-1"}
    result["findings"] = [{"advisory_id": "CVE-2026-0003", "status": "uncertain", "fixed_version": None,
                           "urgency": "not yet assigned", "reason": "advisory_undetermined"}]
    validate_assessment_result(assessment)


def test_epoch_makes_installed_newer_than_fix(assessment):
    result = assessment["results"][1]
    result["installed"] = "2:0.1-1"
    validate_assessment_result(assessment)


def test_mixed_resolved_and_open_findings_must_defer(assessment):
    result = assessment["results"][0]
    result["findings"].append({"advisory_id": "CVE-2026-0009", "status": "affected", "fixed_version": None,
                               "urgency": "low", "reason": "advisory_open"})
    with pytest.raises(ValueError):
        validate_assessment_result(assessment)
    result["decision"] = {"action": "defer", "proposed_version": None, "priority": "high", "reason": "x"}
    validate_assessment_result(assessment)
