"""Validate the v1 observed-version verification result contract.

This helper is deliberately not connected to the execution backend yet.
A schema-valid ``failed`` record is still a blocked verification outcome.
"""

from datetime import datetime
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas/verify.schema.json"
VERIFY_VALIDATOR = Draft202012Validator(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
)


def validate_verify_contract(result: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent records.

    A passing validation alone must never enable a mutation job. Only an approved
    canary on an unblocked deployment path may proceed past verification.
    """
    VERIFY_VALIDATOR.validate(result)
    completed_at = datetime.fromisoformat(result["collected_at"])
    for name, package in result["packages"].items():
        if package["status"] == "pass":
            if package["observed_version"] != package["expected_version"]:
                raise ValueError(
                    f"package {name} passes but observed != expected version"
                )
            if any(check["status"] == "fail" for check in package["health_checks"]):
                raise ValueError(f"package {name} passes but a health check failed")
        if package["status"] == "error" and package["observed_version"] is not None:
            # The module reports "error" only when the version could not be observed.
            raise ValueError(f"package {name} is in error but has an observed version")
