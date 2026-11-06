"""Validate the v1 preflight contract, not its authority to patch.

This helper is deliberately not connected to plan submission or execution yet.
A schema-valid ``not_ready`` or ``error`` record is still a blocked target.
"""

from datetime import datetime
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas/preflight.schema.json"
PREFLIGHT_VALIDATOR = Draft202012Validator(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
)

REQUIRED_CHECKS = ("privileges", "disk", "apt_locks", "apt_health", "drift", "candidates")


def validate_preflight_contract(evidence: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent records.

    A passing check alone must never enable a mutation job. Only ``status: ready``
    hosts have no blocking entries, and even that is not an approval.
    """
    PREFLIGHT_VALIDATOR.validate(evidence)
    if set(evidence["targets"]) != set(evidence["hosts"]):
        raise ValueError("targets and host results must match exactly")

    completed_at = datetime.fromisoformat(evidence["collected_at"])
    for name, host in evidence["hosts"].items():
        observed_at = datetime.fromisoformat(host["collected_at"])
        if observed_at > completed_at:
            raise ValueError(f"host {name} timestamp is after preflight completion")

        check_ids = [check["id"] for check in host["checks"]]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError(f"host {name} has duplicate preflight checks")

        if host["status"] == "ready":
            missing = [check for check in REQUIRED_CHECKS if check not in check_ids]
            if missing:
                raise ValueError(f"host {name} is ready without checks: {', '.join(missing)}")
            for check in host["checks"]:
                if check["status"] != "pass":
                    raise ValueError(
                        f"host {name} is ready while {check['id']} is {check['status']}"
                    )
            if host["backup"]["status"] != "verified":
                raise ValueError(f"host {name} is ready without a verified configuration backup")
            if host["recovery_artifacts"]["status"] != "verified":
                raise ValueError(f"host {name} is ready without verified recovery artifacts")
            if host["blocking"]:
                raise ValueError(f"host {name} is ready with blocking entries")

        if host["status"] == "not_ready" and not host["blocking"]:
            raise ValueError(f"host {name} is not ready but reports no blocking reason")
