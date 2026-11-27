"""Build a validated assessment result from evidence and an advisory cache.

This is the deterministic bridge between the v1 contracts: it performs no network
access, trusts no model input and never authorizes approval or execution.
"""

from datetime import datetime, timezone

from patch_agent.assessment import canonical_sha256, validate_advisory_cache, validate_assessment_result
from patch_agent.debversion import compare_versions, is_fixed, parse_version
from patch_agent.evidence import validate_evidence_contract

URGENCY_PRIORITY = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "unimportant": "low",
    "not yet assigned": "medium",
    "end-of-life": "high",
}


def _timestamp(value=None):
    if value is not None:
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None:
            raise ValueError("assessed_at must be timezone-aware")
        return value
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _priority(urgencies):
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    return max((URGENCY_PRIORITY[value] for value in urgencies), key=order.get, default="medium")


def _parses(version):
    try:
        parse_version(version)
    except ValueError:
        return False
    return True


def _defer(priority, reason):
    return {"action": "defer", "proposed_version": None,
            "proposed_source_version": None, "priority": priority, "reason": reason}


def _assess_package(package_id, package, advisories):
    """Return one result for one evidence package."""
    installed = package["installed"]
    source = package["source"]
    label = package_id

    if source is None:
        return {
            "package": package_id, "installed": installed, "source": None,
            "status": "uncertain", "findings": [],
            "decision": _defer("medium", "source package unknown; advisories cannot be matched"),
        }

    if not advisories:
        return {
            "package": package_id, "installed": installed, "source": source,
            "status": "no_known_advisory", "findings": [], "decision": None,
        }

    if not _parses(installed) or not _parses(source["version"]):
        return {
            "package": package_id, "installed": installed, "source": source,
            "status": "uncertain",
            "findings": [{"advisory_id": "version-invalid", "status": "uncertain",
                          "fixed_version": None, "urgency": "not yet assigned",
                          "reason": "version_invalid"}],
            "decision": _defer("medium", "installed or source version is not a valid Debian version"),
        }

    findings = []
    for advisory in advisories:
        fixed = advisory["fixed_version"]
        if advisory["status"] == "open":
            findings.append({"advisory_id": advisory["id"], "status": "affected",
                             "fixed_version": None, "urgency": advisory["urgency"],
                             "reason": "advisory_open"})
        elif advisory["status"] == "undetermined":
            findings.append({"advisory_id": advisory["id"], "status": "uncertain",
                             "fixed_version": None, "urgency": advisory["urgency"],
                             "reason": "advisory_undetermined"})
        elif is_fixed(source["version"], fixed):
            findings.append({"advisory_id": advisory["id"], "status": "fixed",
                             "fixed_version": fixed, "urgency": advisory["urgency"],
                             "reason": "installed_at_or_after_fix"})
        else:
            findings.append({"advisory_id": advisory["id"], "status": "affected",
                             "fixed_version": fixed, "urgency": advisory["urgency"],
                             "reason": "installed_before_fix"})

    statuses = {finding["status"] for finding in findings}
    if "affected" in statuses:
        status = "affected"
    elif "uncertain" in statuses:
        status = "uncertain"
    else:
        status = "fixed"

    if status == "fixed":
        return {"package": package_id, "installed": installed, "source": source,
                "status": status, "findings": findings, "decision": None}

    if status == "uncertain":
        return {"package": package_id, "installed": installed, "source": source,
                "status": status, "findings": findings,
                "decision": _defer(_priority(f["urgency"] for f in findings),
                                    "advisory data is not conclusive; no patch is proposed")}

    affected = [finding for finding in findings if finding["status"] == "affected"]
    if any(finding["fixed_version"] is None for finding in affected):
        return {"package": package_id, "installed": installed, "source": source,
                "status": status, "findings": findings,
                "decision": _defer(_priority(f["urgency"] for f in affected),
                                    "at least one affected advisory has no fixed version")}

    fixed_versions = [finding["fixed_version"] for finding in affected]
    required = fixed_versions[0]
    for version in fixed_versions[1:]:
        if compare_versions(version, required) > 0:
            required = version

    viable = []
    for candidate in package["candidates"]:
        candidate_source = candidate["source"]
        if candidate_source is None:
            continue
        try:
            if compare_versions(candidate["version"], installed) <= 0:
                continue
            if not is_fixed(candidate_source["version"], required):
                continue
        except ValueError:
            continue
        viable.append(candidate)
    if not viable:
        return {"package": package_id, "installed": installed, "source": source,
                "status": status, "findings": findings,
                "decision": _defer(_priority(f["urgency"] for f in affected),
                                    "no installable candidate resolves every affected advisory")}

    proposed = viable[0]
    for candidate in viable[1:]:
        if compare_versions(candidate["version"], proposed["version"]) < 0:
            proposed = candidate

    return {
        "package": package_id, "installed": installed, "source": source,
        "status": status, "findings": findings,
        "decision": {
            "action": "patch", "proposed_version": proposed["version"],
            "proposed_source_version": proposed["source"]["version"],
            "priority": _priority(f["urgency"] for f in affected),
            "reason": f"install {proposed['version']}; resolves {label} advisories",
        },
    }


def build_assessment(evidence, cache, *, assessed_at=None):
    """Return a validated assessment result bound to ``evidence`` and ``cache``."""
    validate_evidence_contract(evidence)
    validate_advisory_cache(cache)

    assessed = _timestamp(assessed_at)
    if datetime.fromisoformat(evidence["collected_at"]) > datetime.fromisoformat(assessed):
        raise ValueError("evidence was collected after the assessment timestamp")
    if datetime.fromisoformat(cache["fetched_at"]) > datetime.fromisoformat(assessed):
        raise ValueError("advisory cache was fetched after the assessment timestamp")

    results = []
    for host_name in sorted(evidence["hosts"]):
        host = evidence["hosts"][host_name]
        if host["status"] != "ok":
            continue
        for package_id in sorted(host["packages"]):
            package = host["packages"][package_id]
            source_name = package["source"]["name"] if package["source"] else None
            advisories = cache["packages"].get(source_name, []) if source_name else []
            result = _assess_package(package_id, package, advisories)
            result["host"] = host_name
            results.append(result)

    if not results:
        raise ValueError("no assessable packages in the evidence")

    assessment = {
        "schema_version": 1,
        "assessed_at": assessed,
        "evidence_collected_at": evidence["collected_at"],
        "evidence_sha256": canonical_sha256(evidence),
        "advisory_fetched_at": cache["fetched_at"],
        "advisory_cache_sha256": canonical_sha256(cache),
        "release": cache["release"],
        "results": results,
    }
    validate_assessment_result(assessment)
    return assessment
