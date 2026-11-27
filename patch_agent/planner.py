"""Generate a schema-valid patch plan from an assessment and its evidence.

The planner is deterministic: it performs no matching and trusts no model input.
Approval remains a separate human decision.
"""

from patch_agent.approval import validate_plan
from patch_agent.assessment import canonical_sha256, validate_assessment_result
from patch_agent.evidence import validate_evidence_contract

KERNEL_PREFIXES = ("linux-", "kernel")


def _advisory_ids(result):
    return [finding["advisory_id"] for finding in result["findings"]
            if finding["status"] in ("affected", "uncertain")]


def _entry(result, *, host, current_version, action, proposed_version, priority, reason):
    return {
        "host": host,
        "name": result["package"],
        "current_version": current_version,
        "proposed_version": proposed_version,
        "action": action,
        "priority": priority,
        "advisories": _advisory_ids(result),
        "reason": reason,
    }


def build_plan(assessment, evidence, *, run_id, canary=None, verification=None, recovery=None):
    """Return a plan validated against the evidence it was generated from."""
    validate_assessment_result(assessment)
    validate_evidence_contract(evidence)
    if assessment["evidence_sha256"] != canonical_sha256(evidence):
        raise ValueError("assessment is bound to a different evidence record")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id is required")

    targets = list(evidence["targets"])
    if not targets:
        raise ValueError("evidence has no targets")
    if any(evidence["hosts"][host]["status"] != "ok" for host in targets):
        raise ValueError("plans require successful evidence for every target")

    by_host = {host: [] for host in targets}
    for result in assessment["results"]:
        host = result["host"]
        if host not in by_host:
            raise ValueError(f"assessment result for host outside the evidence targets: {host}")
        by_host[host].append(result)

    packages = []
    for host in targets:
        entries = []
        for result in sorted(by_host[host], key=lambda item: item["package"]):
            decision = result["decision"]
            if decision is None:
                continue
            if decision["action"] == "patch" and result["package"].startswith(KERNEL_PREFIXES):
                entries.append(_entry(
                    result, host=host, current_version=result["installed"],
                    action="defer", proposed_version=None, priority=decision["priority"],
                    reason="kernel changes are deferred in the MVP"))
            elif decision["action"] == "patch":
                entries.append(_entry(
                    result, host=host, current_version=result["installed"],
                    action="patch", proposed_version=decision["proposed_version"],
                    priority=decision["priority"], reason=decision["reason"]))
            else:
                entries.append(_entry(
                    result, host=host, current_version=result["installed"],
                    action="defer", proposed_version=None,
                    priority=decision["priority"], reason=decision["reason"]))
        if not entries:
            first = sorted(evidence["hosts"][host]["packages"])[0]
            package = evidence["hosts"][host]["packages"][first]
            entries.append({
                "host": host, "name": first, "current_version": package["installed"],
                "proposed_version": None, "action": "defer", "priority": "low",
                "advisories": [], "reason": "no actionable advisory in the assessment",
            })
        packages.extend(entries)

    canary = canary or targets[0]
    if canary not in targets:
        raise ValueError("canary must be one of the selected targets")

    plan = {
        "run_id": run_id,
        "targets": targets,
        "canary": canary,
        "packages": packages,
        "verification": verification or [
            "installed package versions match the approved plan",
            "configured service health checks pass",
        ],
        "recovery": recovery or {
            "snapshot": f"baseline-before-{run_id}",
            "previous_packages": True,
            "config_backup": True,
        },
    }
    validate_plan(plan, evidence)
    return plan
