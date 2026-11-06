"""Validate the v1 recovery result contract.

This helper is deliberately not connected to the execution backend yet.
A schema-valid ``manual_required`` record is still a blocked recovery outcome.
"""

from datetime import datetime
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas/recover.schema.json"
RECOVER_VALIDATOR = Draft202012Validator(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
)


def validate_recover_contract(result: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent records.

    A passing validation alone must never enable a mutation job. Recovery only
    runs for the affected host after an approved canary failure.
    """
    RECOVER_VALIDATOR.validate(result)
    completed_at = datetime.fromisoformat(result["collected_at"])
    if result["manual_intervention"]:
        if result["repair"]["result"] == "succeeded" and not result["restoration"]["previous_packages"]:
            raise ValueError("manual intervention flagged but no recovery action was attempted")
    if not result["manual_intervention"]:
        if result["repair"]["result"] == "failed":
            raise ValueError("no manual intervention but repair failed")
        for entry in result["restoration"]["previous_packages"]:
            if entry["result"] == "failed":
                raise ValueError("no manual intervention but a previous-package restore failed")
        for entry in result["restoration"]["config_backups"]:
            if entry["result"] == "failed":
                raise ValueError("no manual intervention but a config restore failed")
