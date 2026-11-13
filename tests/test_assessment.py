import copy
import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from patch_agent.assessment import (
    CONTRACT_ERRORS, canonical_sha256, validate_advisory_cache, validate_assessment_result)

FIXTURES = Path(__file__).parent / "fixtures" / "assessment"

# Result indexes in assessment-valid.json
PATCH, FIXED, CLEAN, OPEN, UNKNOWN = range(5)


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def defer(priority="low"):
    return {"action": "defer", "proposed_version": None, "proposed_source_version": None,
            "priority": priority, "reason": "x"}


def patch_to(version, source_version=None):
    return {"action": "patch", "proposed_version": version, "proposed_source_version": source_version or version,
            "priority": "low", "reason": "x"}


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


def test_contract_errors_cover_both_failure_types(cache):
    cache["extra"] = 1
    with pytest.raises(CONTRACT_ERRORS):
        validate_advisory_cache(cache)
    del cache["extra"]
    cache["fetched_at"] = "2026-02-30T00:00:00Z"
    with pytest.raises(CONTRACT_ERRORS):
        validate_advisory_cache(cache)


def test_canonical_sha256():
    assert canonical_sha256({"a": 1, "b": [1, 2]}) == canonical_sha256({"b": [1, 2], "a": 1})
    assert canonical_sha256({"a": 1}) != canonical_sha256({"a": 2})
    assert len(canonical_sha256({})) == 64


def test_fixture_binds_to_the_cache_fixture(cache, assessment):
    assert assessment["advisory_cache_sha256"] == canonical_sha256(cache)


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
    def query_token(c): c["source"]["uri"] = "https://security-tracker.debian.org/data.json?token=secret"
    def fragment(c): c["source"]["uri"] = "https://security-tracker.debian.org/data.json#frag"
    def impossible_date(c): c["fetched_at"] = "2026-02-30T00:00:00Z"
    def bad_port(c): c["source"]["uri"] = "https://security-tracker.debian.org:99999/data.json"
    return [duplicate_id, unparseable_fix, credentials, query_token, fragment, impossible_date, bad_port]


@pytest.mark.parametrize("mutate", cache_consistency_cases(), ids=lambda f: f.__name__)
def test_advisory_cache_consistency_errors(cache, mutate):
    mutate(cache)
    with pytest.raises(ValueError):
        validate_advisory_cache(cache)


def test_not_affected_marker_zero_is_a_valid_fixed_version(cache):
    cache["packages"]["demo-source"][0]["fixed_version"] = "0"
    validate_advisory_cache(cache)


# ---- assessment result: shape -----------------------------------------------

def assessment_shape_cases():
    def unknown_field(a): a["results"][PATCH]["extra"] = 1
    def bad_version(a): a["schema_version"] = 2
    def empty_results(a): a["results"] = []
    def missing_decision(a): del a["results"][PATCH]["decision"]
    def unknown_status(a): a["results"][PATCH]["status"] = "vulnerable"
    def unknown_reason(a): a["results"][PATCH]["findings"][0]["reason"] = "because"
    def patch_without_version(a): a["results"][PATCH]["decision"]["proposed_version"] = None
    def patch_without_source_version(a): a["results"][PATCH]["decision"]["proposed_source_version"] = None
    def defer_with_version(a): a["results"][OPEN]["decision"]["proposed_version"] = "2.0-2"
    def defer_with_source_version(a): a["results"][OPEN]["decision"]["proposed_source_version"] = "2.0-2"
    def missing_source_version(a): del a["results"][PATCH]["decision"]["proposed_source_version"]
    def bad_priority(a): a["results"][PATCH]["decision"]["priority"] = "urgent"
    def blank_reason(a): a["results"][PATCH]["decision"]["reason"] = "  "
    def bad_host(a): a["results"][PATCH]["host"] = "VM 01"
    def unqualified_package(a): a["results"][PATCH]["package"] = "demo-package"
    def omitted_source(a): del a["results"][PATCH]["source"]
    def missing_evidence_digest(a): del a["evidence_sha256"]
    def missing_cache_digest(a): del a["advisory_cache_sha256"]
    def short_digest(a): a["evidence_sha256"] = "abc123"
    def uppercase_digest(a): a["advisory_cache_sha256"] = a["advisory_cache_sha256"].upper()
    return [unknown_field, bad_version, empty_results, missing_decision, unknown_status, unknown_reason,
            patch_without_version, patch_without_source_version, defer_with_version, defer_with_source_version,
            missing_source_version, bad_priority, blank_reason, bad_host, unqualified_package, omitted_source,
            missing_evidence_digest, missing_cache_digest, short_digest, uppercase_digest]


@pytest.mark.parametrize("mutate", assessment_shape_cases(), ids=lambda f: f.__name__)
def test_assessment_shape_errors(assessment, mutate):
    mutate(assessment)
    with pytest.raises(ValidationError):
        validate_assessment_result(assessment)


# ---- assessment result: consistency -----------------------------------------

def assessment_consistency_cases():
    def duplicate_result(a): a["results"].append(copy.deepcopy(a["results"][PATCH]))
    def assessed_before_evidence(a): a["evidence_collected_at"] = "2026-10-30T09:31:00Z"
    def assessed_before_advisories(a): a["advisory_fetched_at"] = "2026-10-30T09:31:00Z"
    def impossible_date(a): a["assessed_at"] = "2026-02-30T00:00:00Z"
    def status_not_from_findings(a): a["results"][PATCH]["status"] = "fixed"
    def affected_but_source_is_fixed(a): a["results"][PATCH]["source"]["version"] = "1:1.0-3"
    def fixed_but_source_is_older(a): a["results"][FIXED]["source"]["version"] = "1:1.0-1"
    def reason_status_mismatch(a): a["results"][PATCH]["findings"][0]["status"] = "uncertain"
    def before_fix_without_fix(a): a["results"][PATCH]["findings"][0]["fixed_version"] = None
    def open_with_fix(a): a["results"][OPEN]["findings"][0]["fixed_version"] = "2.0-2"
    def fixed_with_decision(a): a["results"][FIXED]["decision"] = defer()
    def clean_with_decision(a): a["results"][CLEAN]["decision"] = defer()
    def affected_without_decision(a): a["results"][PATCH]["decision"] = None
    def patch_below_fix(a): a["results"][PATCH]["decision"] = patch_to("1:1.0-1+deb12u1")
    def patch_binary_ok_but_source_below_fix(a): a["results"][PATCH]["decision"] = patch_to("1:1.0-2+b1", "1:1.0-1")
    def patch_invalid_proposed_version(a): a["results"][PATCH]["decision"] = patch_to("???", "1:1.0-2")
    def patch_with_unfixed_finding(a): a["results"][OPEN]["decision"] = patch_to("2.0-2")
    def patch_uncertain(a): a["results"][UNKNOWN]["decision"] = patch_to("3.1-2") | {"priority": "medium"}
    def unknown_source_wrong_priority(a): a["results"][UNKNOWN]["decision"]["priority"] = "high"
    def findings_without_source(a): a["results"][PATCH]["source"] = None
    def no_findings_known_source_marked_uncertain(a): a["results"][CLEAN]["status"] = "uncertain"
    def no_findings_unknown_source_marked_clean(a): a["results"][UNKNOWN]["status"] = "no_known_advisory"
    def fixed_without_findings(a): a["results"][FIXED]["findings"] = []
    def version_invalid_but_versions_parse(a):
        a["results"][OPEN]["findings"].append({"advisory_id": "CVE-2026-0009", "status": "uncertain", "fixed_version": None, "urgency": "low", "reason": "version_invalid"})
    def invalid_installed_without_finding(a): a["results"][OPEN]["installed"] = "!!!"
    def invalid_source_version_without_finding(a): a["results"][OPEN]["source"]["version"] = "!!!"
    def compare_with_invalid_versions(a):
        a["results"][PATCH]["installed"] = "!!!"
        a["results"][PATCH]["findings"].append({"advisory_id": "CVE-2026-0009", "status": "uncertain", "fixed_version": None, "urgency": "low", "reason": "version_invalid"})
    def patch_with_uncertain_finding(a):
        a["results"][PATCH]["findings"].append({"advisory_id": "CVE-2026-0003", "status": "uncertain", "fixed_version": None, "urgency": "not yet assigned", "reason": "advisory_undetermined"})
    return [duplicate_result, assessed_before_evidence, assessed_before_advisories, impossible_date,
            status_not_from_findings, affected_but_source_is_fixed, fixed_but_source_is_older,
            reason_status_mismatch, before_fix_without_fix, open_with_fix, fixed_with_decision, clean_with_decision,
            affected_without_decision, patch_below_fix, patch_binary_ok_but_source_below_fix,
            patch_invalid_proposed_version, patch_with_unfixed_finding, patch_uncertain,
            unknown_source_wrong_priority, findings_without_source, no_findings_known_source_marked_uncertain,
            no_findings_unknown_source_marked_clean, fixed_without_findings, version_invalid_but_versions_parse,
            invalid_installed_without_finding, invalid_source_version_without_finding,
            compare_with_invalid_versions, patch_with_uncertain_finding]


@pytest.mark.parametrize("mutate", assessment_consistency_cases(), ids=lambda f: f.__name__)
def test_assessment_consistency_errors(assessment, mutate):
    mutate(assessment)
    with pytest.raises(ValueError):
        validate_assessment_result(assessment)


# ---- assessment result: accepted variations ---------------------------------

def test_unparseable_installed_version_with_invalid_finding_defers(assessment):
    result = assessment["results"][OPEN]
    result["installed"] = "!!!"
    result["findings"].append({"advisory_id": "CVE-2026-0009", "status": "uncertain", "fixed_version": None,
                               "urgency": "low", "reason": "version_invalid"})
    validate_assessment_result(assessment)


def test_unparseable_source_version_with_invalid_finding_defers(assessment):
    result = assessment["results"][CLEAN]
    result["source"]["version"] = "not-a-version"
    result["findings"] = [{"advisory_id": "CVE-2026-0009", "status": "uncertain", "fixed_version": None,
                           "urgency": "medium", "reason": "version_invalid"}]
    result["status"] = "uncertain"
    result["decision"] = defer("medium")
    validate_assessment_result(assessment)


def test_undetermined_advisory_defers(assessment):
    result = assessment["results"][CLEAN]
    result["findings"] = [{"advisory_id": "CVE-2026-0003", "status": "uncertain", "fixed_version": None,
                           "urgency": "not yet assigned", "reason": "advisory_undetermined"}]
    result["status"] = "uncertain"
    result["decision"] = defer("medium")
    validate_assessment_result(assessment)


def test_source_epoch_makes_package_newer_than_fix(assessment):
    assessment["results"][FIXED]["source"]["version"] = "2:0.1-1"
    validate_assessment_result(assessment)


def test_binary_version_does_not_decide_the_comparison(assessment):
    # A binNMU installed version is newer than the fix, but the source version is not.
    result = assessment["results"][PATCH]
    result["installed"] = "1:1.0-1+b1"
    validate_assessment_result(assessment)
    result["decision"] = patch_to("1:1.0-2+b1", "1:1.0-2") | {"priority": "high"}
    validate_assessment_result(assessment)


def test_mixed_resolved_and_open_findings_must_defer(assessment):
    result = assessment["results"][PATCH]
    result["findings"].append({"advisory_id": "CVE-2026-0009", "status": "affected", "fixed_version": None,
                               "urgency": "low", "reason": "advisory_open"})
    with pytest.raises(ValueError):
        validate_assessment_result(assessment)
    result["decision"] = defer("high")
    validate_assessment_result(assessment)


def test_all_clean_assessment_is_explicit(assessment):
    assessment["results"] = [assessment["results"][CLEAN]]
    validate_assessment_result(assessment)
