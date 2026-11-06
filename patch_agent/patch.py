"""Validate the v1 exact-version patch result contract.

This helper is deliberately not connected to the execution backend yet.
A schema-valid ``failed`` record is still a blocked patch outcome.
"""

from datetime import datetime
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas/patch.schema.json"
PATCH_VALIDATOR = Draft202012Validator(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
)


def validate_patch_contract(result: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent records.

    A passing validation alone must never enable a mutation job. Only an approved
    canary on an unblocked deployment path may apply changes.
    """
    PATCH_VALIDATOR.validate(result)
    completed_at = datetime.fromisoformat(result["collected_at"])
    for name, package in result["packages"].items():
        observed_before = package["installed_before"]
        observed_after = package["installed_after"]
        if package["action"] == "defer":
            if package["target_version"] is not None:
                raise ValueError(f"package {name} is deferred but has a target version")
            if package["status"] != "deferred":
                raise ValueError(f"package {name} is deferred but status is {package['status']}")
        if package["status"] == "applied":
            if observed_after is None:
                raise ValueError(f"package {name} is applied but has no installed_after")
            if package["error"] is not None:
                raise ValueError(f"package {name} is applied but has an error")
        if package["status"] == "failed":
            if package["error"] is None:
                raise ValueError(f"package {name} is failed but has no error")
        for restart in package["service_restart"]:
            if not restart["restarted"] and restart["error"] is None:
                raise ValueError(
                    f"package {name} service {restart['service']} not restarted without error"
                )
