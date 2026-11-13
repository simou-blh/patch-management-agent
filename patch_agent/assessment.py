"""Validate the v1 advisory-cache and assessment-result contracts.

Validation checks shape and internal consistency only. It does not fetch data, judge
freshness or authority, or make anything eligible for approval or execution.
"""

from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, ValidationError

from patch_agent.approval import canonical
from patch_agent.debversion import is_fixed, parse_version

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"
ADVISORY_VALIDATOR = Draft202012Validator(
    json.loads((SCHEMAS / "advisory-cache.schema.json").read_text(encoding="utf-8")))
ASSESSMENT_VALIDATOR = Draft202012Validator(
    json.loads((SCHEMAS / "assessment.schema.json").read_text(encoding="utf-8")))

# Both validators raise one of these; callers can catch the tuple.
CONTRACT_ERRORS = (ValidationError, ValueError)

# finding reason -> (finding status, whether a fixed version is required: True/False/None=either)
FINDING_REASONS = {
    "installed_before_fix": ("affected", True),
    "advisory_open": ("affected", False),
    "installed_at_or_after_fix": ("fixed", True),
    "advisory_undetermined": ("uncertain", False),
    "version_invalid": ("uncertain", None),
}
COMPARING_REASONS = ("installed_before_fix", "installed_at_or_after_fix")


def canonical_sha256(document) -> str:
    """SHA-256 of an input record in the project's canonical JSON form (approval.canonical)."""
    return hashlib.sha256(canonical(document).encode()).hexdigest()


def _time(value: str) -> datetime:
    # The schema pattern fixes the shape; parsing also rejects impossible dates.
    return datetime.fromisoformat(value)


def _parses(version: str) -> bool:
    try:
        parse_version(version)
    except ValueError:
        return False
    return True


def validate_advisory_cache(cache: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent records."""
    ADVISORY_VALIDATOR.validate(cache)
    _time(cache["fetched_at"])
    uri = urlsplit(cache["source"]["uri"])
    if uri.username is not None or uri.password is not None:
        raise ValueError("advisory source URI must not contain credentials")
    if uri.query or uri.fragment:
        raise ValueError("advisory source URI must not contain a query or fragment")
    if not uri.hostname:
        raise ValueError("advisory source URI requires a host")
    _ = uri.port  # raises ValueError for a nonnumeric or out-of-range port
    for source_name, advisories in cache["packages"].items():
        ids = [advisory["id"] for advisory in advisories]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{source_name}: advisory ids must be unique")
        for advisory in advisories:
            if advisory["fixed_version"] is not None:
                # Reject at the boundary; "0" (not affected in that release) is valid.
                parse_version(advisory["fixed_version"])


def _check_finding(label: str, source_version: str, versions_ok: bool, finding: dict) -> None:
    where = f"{label} {finding['advisory_id']}"
    status, needs_fixed = FINDING_REASONS[finding["reason"]]
    fixed = finding["fixed_version"]
    if finding["status"] != status:
        raise ValueError(f"{where}: reason {finding['reason']} requires status {status}")
    if needs_fixed is True and fixed is None:
        raise ValueError(f"{where}: reason {finding['reason']} requires a fixed version")
    if needs_fixed is False and fixed is not None:
        raise ValueError(f"{where}: reason {finding['reason']} must not have a fixed version")
    if finding["reason"] in COMPARING_REASONS:
        if not versions_ok:
            raise ValueError(f"{where}: cannot compare unparseable versions")
        # Advisories carry source package versions, so the source version is compared.
        fixed_already = is_fixed(source_version, fixed)
        if finding["reason"] == "installed_before_fix" and fixed_already:
            raise ValueError(f"{where}: source version is not before the fix")
        if finding["reason"] == "installed_at_or_after_fix" and not fixed_already:
            raise ValueError(f"{where}: source version is before the fix")


def _check_result(result: dict) -> None:
    label = f"{result['host']}/{result['package']}"
    source = result["source"]
    findings = result["findings"]
    if source is None and findings:
        raise ValueError(f"{label}: findings require a known source package")

    versions_ok = True
    if source is not None:
        versions_ok = _parses(result["installed"]) and _parses(source["version"])
        has_invalid = any(f["reason"] == "version_invalid" for f in findings)
        if versions_ok and has_invalid:
            raise ValueError(f"{label}: version_invalid but the installed and source versions parse")
        if not versions_ok and not has_invalid:
            raise ValueError(f"{label}: an unparseable installed or source version needs a version_invalid finding")
    for finding in findings:
        _check_finding(label, source["version"] if source else "", versions_ok, finding)

    statuses = {finding["status"] for finding in findings}
    if "affected" in statuses:
        expected = "affected"
    elif "uncertain" in statuses:
        expected = "uncertain"
    elif findings:
        expected = "fixed"
    elif source is None:
        expected = "uncertain"
    else:
        expected = "no_known_advisory"
    if result["status"] != expected:
        raise ValueError(f"{label}: status must be {expected} for these findings")

    decision = result["decision"]
    if expected in ("fixed", "no_known_advisory"):
        if decision is not None:
            raise ValueError(f"{label}: a {expected} package has no decision")
        return
    if decision is None:
        raise ValueError(f"{label}: an affected or uncertain package needs a patch/defer decision")
    if source is None and decision["priority"] != "medium":
        raise ValueError(f"{label}: priority defaults to medium when the source package is unknown")
    if decision["action"] == "defer":
        return
    if expected != "affected":
        raise ValueError(f"{label}: only an affected package can be patched; defer uncertain ones")
    if "uncertain" in statuses:
        raise ValueError(f"{label}: cannot patch while a finding is uncertain; defer instead")
    if not _parses(decision["proposed_version"]):
        raise ValueError(f"{label}: proposed version is not a valid Debian version")
    # Conservative rule: patch only to a version that resolves every affected finding.
    for finding in findings:
        if finding["status"] == "affected" and (
            finding["fixed_version"] is None
            or not is_fixed(decision["proposed_source_version"], finding["fixed_version"])
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
