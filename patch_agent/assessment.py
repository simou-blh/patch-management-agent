"""Validate the v1 advisory-cache and assessment-result contracts.

Validation checks shape and internal consistency only. It does not fetch data, judge
freshness or authority, or make anything eligible for approval or execution.
"""

from datetime import datetime
import json
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from patch_agent.debversion import is_fixed, parse_version

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"
ADVISORY_VALIDATOR = Draft202012Validator(
    json.loads((SCHEMAS / "advisory-cache.schema.json").read_text(encoding="utf-8")))
ASSESSMENT_VALIDATOR = Draft202012Validator(
    json.loads((SCHEMAS / "assessment.schema.json").read_text(encoding="utf-8")))

# finding reason -> (finding status, whether a fixed version is required: True/False/None=either)
FINDING_REASONS = {
    "installed_before_fix": ("affected", True),
    "advisory_open": ("affected", False),
    "installed_at_or_after_fix": ("fixed", True),
    "advisory_undetermined": ("uncertain", False),
    "version_invalid": ("uncertain", None),
}


def _time(value: str) -> datetime:
    # The schema pattern fixes the shape; parsing also rejects impossible dates.
    return datetime.fromisoformat(value)


def validate_advisory_cache(cache: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent records."""
    ADVISORY_VALIDATOR.validate(cache)
    _time(cache["fetched_at"])
    uri = urlsplit(cache["source"]["uri"])
    if uri.username is not None or uri.password is not None:
        raise ValueError("advisory source URI must not contain credentials")
    if not uri.hostname:
        raise ValueError("advisory source URI requires a host")
    uri.port  # rejects nonnumeric/out-of-range ports
    for source_name, advisories in cache["packages"].items():
        ids = [advisory["id"] for advisory in advisories]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{source_name}: advisory ids must be unique")
        for advisory in advisories:
            if advisory["fixed_version"] is not None:
                # Reject at the boundary; "0" (not affected in that release) is valid.
                parse_version(advisory["fixed_version"])


def _check_finding(label: str, installed: str, finding: dict) -> None:
    status, needs_fixed = FINDING_REASONS[finding["reason"]]
    fixed = finding["fixed_version"]
    if finding["status"] != status:
        raise ValueError(f"{label} {finding['advisory_id']}: reason {finding['reason']} requires status {status}")
    if needs_fixed is True and fixed is None:
        raise ValueError(f"{label} {finding['advisory_id']}: reason {finding['reason']} requires a fixed version")
    if needs_fixed is False and fixed is not None:
        raise ValueError(f"{label} {finding['advisory_id']}: reason {finding['reason']} must not have a fixed version")
    if finding["reason"] == "installed_before_fix" and is_fixed(installed, fixed):
        raise ValueError(f"{label} {finding['advisory_id']}: installed version is not before the fix")
    if finding["reason"] == "installed_at_or_after_fix" and not is_fixed(installed, fixed):
        raise ValueError(f"{label} {finding['advisory_id']}: installed version is before the fix")
    if finding["reason"] == "version_invalid":
        try:
            parse_version(installed)
        except ValueError:
            return
        raise ValueError(f"{label} {finding['advisory_id']}: version_invalid but the installed version parses")


def _check_result(result: dict) -> None:
    label = f"{result['host']}/{result['package']}"
    findings = result["findings"]
    for finding in findings:
        _check_finding(label, result["installed"], finding)
    statuses = {finding["status"] for finding in findings}
    if "affected" in statuses:
        expected = "affected"
    elif "uncertain" in statuses:
        expected = "uncertain"
    elif findings:
        expected = "fixed"
    else:
        if result["source"] is not None:
            raise ValueError(f"{label}: a result without findings requires an unknown source package")
        expected = "uncertain"
    if result["status"] != expected:
        raise ValueError(f"{label}: status must be {expected} for these findings")

    decision = result["decision"]
    if result["status"] == "fixed":
        if decision is not None:
            raise ValueError(f"{label}: a fixed package has no decision")
        return
    if decision is None:
        raise ValueError(f"{label}: an affected or uncertain package needs a patch/defer decision")
    if decision["action"] == "defer":
        return
    if result["status"] != "affected":
        raise ValueError(f"{label}: only an affected package can be patched; defer uncertain ones")
    # Conservative rule: patch only to a version that resolves every affected finding.
    for finding in findings:
        if finding["status"] == "affected" and (
            finding["fixed_version"] is None
            or not is_fixed(decision["proposed_version"], finding["fixed_version"])
        ):
            raise ValueError(f"{label} {finding['advisory_id']}: proposed version does not resolve this finding; defer instead")


def validate_assessment_result(assessment: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent records."""
    ASSESSMENT_VALIDATOR.validate(assessment)
    assessed_at = _time(assessment["assessed_at"])
    for key in ("evidence_collected_at", "advisory_fetched_at"):
        if _time(assessment[key]) > assessed_at:
            raise ValueError(f"{key} is after assessed_at")
    seen = set()
    for result in assessment["results"]:
        key = (result["host"], result["package"])
        if key in seen:
            raise ValueError(f"duplicate result for {key[0]}/{key[1]}")
        seen.add(key)
        _check_result(result)
