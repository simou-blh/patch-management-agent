"""Validate v1 collection structure and readiness for collector consumption.

The operator importer and plan submission apply readiness checks before using it.
"""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from patch_agent.osquery import load_hosts

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas/evidence.schema.json"
EVIDENCE_VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def evidence_max_age() -> timedelta:
    """Read the operator's policy; missing or invalid policy blocks consumption."""
    value = os.environ.get("PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS", "")
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError("set PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS to a positive integer")
    try:
        return timedelta(seconds=int(value))
    except OverflowError as exc:
        raise ValueError("PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS is too large") from exc


def validate_evidence_contract(evidence: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent records.

    Failed-host records are valid diagnostics. Passing this check alone must never
    make them eligible for plan generation or execution.
    """
    EVIDENCE_VALIDATOR.validate(evidence)
    if set(evidence["targets"]) != set(evidence["hosts"]):
        raise ValueError("targets and host results must match exactly")

    # jsonschema's date-time format assertion needs optional dependencies. Parse
    # explicitly so impossible calendar dates are rejected in every environment.
    completed_at = datetime.fromisoformat(evidence["collected_at"])
    for name, host in evidence["hosts"].items():
        observed_at = datetime.fromisoformat(host["collected_at"])
        if observed_at > completed_at:
            raise ValueError(f"host {name} timestamp is after collection completion")
        for package in host["packages"].values():
            versions = [candidate["version"] for candidate in package["candidates"]]
            if len(versions) != len(set(versions)):
                raise ValueError("candidate versions must be unique; combine their repository origins")
            for candidate in package["candidates"]:
                for origin in candidate["origins"]:
                    uri = urlsplit(origin["uri"])
                    if uri.username is not None or uri.password is not None:
                        raise ValueError("repository origin URI must not contain credentials")
                    if uri.scheme in ("http", "https"):
                        if not uri.hostname:
                            raise ValueError("HTTP repository origin URI requires a host")
                        # Accessing port also rejects nonnumeric/out-of-range ports.
                        uri.port
                    elif not uri.path:
                        raise ValueError("file repository origin URI requires a path")


def validate_evidence_readiness(
    evidence: dict, *, targets: list[str], max_age: timedelta, now: datetime | None = None,
) -> None:
    """Require complete, successful, fresh results for the operator-selected targets.

    max_age is explicit operator policy, never chosen from evidence or model input.
    Passing does not establish provenance, package coverage or approval eligibility.
    No files are written, and existing approval consumers are not connected yet.
    """
    validate_evidence_contract(evidence)
    if (not isinstance(targets, list) or not targets
            or any(not isinstance(name, str) for name in targets)
            or len(targets) != len(set(targets))):
        raise ValueError("select one or more unique inventory hosts")
    if not set(targets) <= load_hosts().keys():
        raise ValueError("unknown inventory host")
    if set(targets) != set(evidence["targets"]):
        raise ValueError("evidence targets must match the requested targets exactly")
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise ValueError("max_age must be a positive timedelta")
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")

    timestamps = [("collection", evidence["collected_at"])]
    for name, host in evidence["hosts"].items():
        if host["status"] != "ok":
            raise ValueError(f"host {name} inspection failed; evidence is not ready")
        timestamps.append((f"host {name}", host["collected_at"]))
    for label, timestamp in timestamps:
        age = now - datetime.fromisoformat(timestamp)
        if age < timedelta(0):
            raise ValueError(f"{label} timestamp is in the future")
        if age > max_age:
            raise ValueError(f"{label} evidence is stale")
