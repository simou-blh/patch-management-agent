import json
from pathlib import Path

import pytest

from patch_agent.assessment import canonical_sha256
from patch_agent.assessment_builder import build_assessment

FIXTURES = Path(__file__).parent / "fixtures" / "assessment"
ORIGIN = {"uri": "https://repo.example.invalid/debian", "suite": "bookworm", "component": "main"}


def load_cache():
    return json.loads((FIXTURES / "advisory-cache-valid.json").read_text(encoding="utf-8"))


def package(installed, source_name, source_version, candidates=()):
    return {
        "installed": installed,
        "source": {"name": source_name, "version": source_version} if source_name else None,
        "candidates": [
            {"version": version,
             "source": {"name": name, "version": source} if name else None,
             "origins": [ORIGIN]}
            for version, name, source in candidates
        ],
    }


def evidence(packages, *, host="vm-01", timestamp="2026-10-30T09:00:00Z"):
    return {"schema_version": 1, "collected_at": timestamp, "targets": [host],
            "hosts": {host: {"status": "ok", "collected_at": timestamp,
                              "packages": packages, "error": None}}}


def build(packages, cache=None):
    return build_assessment(evidence(packages), cache or load_cache(),
                            assessed_at="2026-11-27T00:00:00Z")


def test_affected_package_proposes_installable_candidate():
    result = build({"demo-package:amd64": package(
        "1:1.0-1", "demo-source", "1:1.0-1",
        [("1:1.0-2", "demo-source", "1:1.0-2")])})["results"][0]
    assert result["status"] == "affected"
    assert result["decision"]["action"] == "patch"
    assert result["decision"]["proposed_version"] == "1:1.0-2"
    assert result["decision"]["priority"] == "high"


def test_open_advisory_defers():
    result = build({"open-package:amd64": package(
        "2.0-1", "open-source", "2.0-1",
        [("2.0-2", "open-source", "2.0-2")])})["results"][0]
    assert result["status"] == "affected"
    assert result["decision"]["action"] == "defer"
    assert result["decision"]["proposed_version"] is None


def test_undetermined_advisory_is_uncertain_and_defers():
    result = build({"pending-package:amd64": package(
        "1.0-1", "pending-source", "1.0-1")})["results"][0]
    assert result["status"] == "uncertain"
    assert result["decision"]["action"] == "defer"


def test_unknown_source_is_uncertain():
    result = build({"mystery:amd64": package("3.1-1", None, None)})["results"][0]
    assert result["status"] == "uncertain"
    assert result["findings"] == []
    assert result["decision"]["priority"] == "medium"


def test_no_known_advisory_is_explicit():
    result = build({"clean-package:amd64": package("4.2-1", "clean-source", "4.2-1")})["results"][0]
    assert result["status"] == "no_known_advisory"
    assert result["decision"] is None


def test_invalid_installed_version_marks_uncertain():
    result = build({"demo-package:amd64": package("!!!", "demo-source", "1:1.0-1")})["results"][0]
    assert result["status"] == "uncertain"
    assert result["findings"][0]["reason"] == "version_invalid"


def test_no_installable_candidate_defers():
    result = build({"demo-package:amd64": package(
        "1:1.0-1", "demo-source", "1:1.0-1",
        [("1:1.0-1", "demo-source", "1:1.0-1")])})["results"][0]
    assert result["status"] == "affected"
    assert result["decision"]["action"] == "defer"
    assert "no installable candidate" in result["decision"]["reason"]


def test_assessment_binds_its_inputs():
    cache = load_cache()
    collection = evidence({"demo-package:amd64": package("1:1.0-1", "demo-source", "1:1.0-1")})
    assessment = build_assessment(collection, cache, assessed_at="2026-11-27T00:00:00Z")
    assert assessment["evidence_sha256"] == canonical_sha256(collection)
    assert assessment["advisory_cache_sha256"] == canonical_sha256(cache)


def test_assessment_timestamp_cannot_precede_inputs():
    with pytest.raises(ValueError):
        build_assessment(evidence({"demo-package:amd64": package("1:1.0-1", "demo-source", "1:1.0-1")}),
                         load_cache(), assessed_at="2026-10-30T08:59:00Z")


def test_failed_hosts_are_skipped():
    collection = evidence({"demo-package:amd64": package("1:1.0-1", "demo-source", "1:1.0-1")})
    collection["targets"] = ["vm-01", "vm-02"]
    collection["hosts"]["vm-02"] = {"status": "error", "collected_at": collection["collected_at"],
                                     "packages": {}, "error": {"code": "timeout", "message": "down"}}
    assessment = build_assessment(collection, load_cache(), assessed_at="2026-11-27T00:00:00Z")
    assert {result["host"] for result in assessment["results"]} == {"vm-01"}


def test_no_assessable_packages_is_rejected():
    collection = {"schema_version": 1, "collected_at": "2026-10-30T09:00:00Z",
                  "targets": ["vm-01"],
                  "hosts": {"vm-01": {"status": "error", "collected_at": "2026-10-30T09:00:00Z",
                                       "packages": {}, "error": {"code": "down", "message": "down"}}}}
    with pytest.raises(ValueError, match="no assessable packages"):
        build_assessment(collection, load_cache(), assessed_at="2026-11-27T00:00:00Z")
