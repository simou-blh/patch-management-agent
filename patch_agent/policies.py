"""Validate the fixed service/restart and health-check policy allowlist.

Patch and verification playbooks must consult this policy instead of accepting
service names from a plan or a model. Validation here does not start a service.
"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas/policies.schema.json"
DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "policies/services.json"
POLICY_VALIDATOR = Draft202012Validator(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
)


def validate_policies(policy: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for dangling references."""
    POLICY_VALIDATOR.validate(policy)

    services = set(policy["services"])
    for package, entry in policy["packages"].items():
        unknown = [service for service in entry["services"] if service not in services]
        if unknown:
            raise ValueError(
                f"package {package} references unconfigured services: {', '.join(unknown)}"
            )

    if policy["restart_policy"] != "configured-only":
        raise ValueError("restart policy must be configured-only")


def load_default_policy() -> dict:
    policy = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    validate_policies(policy)
    return policy
