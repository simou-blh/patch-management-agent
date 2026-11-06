"""Validate the v1 sequential rollout result contract.

A rollout that stopped early because a host needed recovery is still valid;
the failed host and its recovery are recorded, and later hosts are absent.
"""

from datetime import datetime
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas/rollout.schema.json"
ROLLOUT_VALIDATOR = Draft202012Validator(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
)


def validate_rollout_contract(result: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent records.

    A passing validation alone must never enable a live rollout. Only an approved
    canary on an unblocked deployment path may proceed past the canary host.
    """
    ROLLOUT_VALIDATOR.validate(result)

    # Error records may have empty targets/hosts; skip consistency checks.
    if result["error"] is not None:
        return

    if result["canary"] not in result["targets"]:
        raise ValueError("canary must be one of the rollout targets")

    completed_at = datetime.fromisoformat(result["collected_at"])
    for name, host in result["hosts"].items():
        observed_at = datetime.fromisoformat(host["collected_at"])
        if observed_at > completed_at:
            raise ValueError(f"host {name} timestamp is after rollout completion")

        if host["action"] == "recover":
            if not host["blocking"]:
                raise ValueError(f"host {name} is marked recover but has no blocking reason")
            if host["error"] is not None and host["error"].get("code") == "unreachable":
                continue  # unreachable hosts are expected to need recovery
        elif host["action"] == "proceed":
            if host["blocking"]:
                raise ValueError(f"host {name} is marked proceed but has blocking entries")
            if host["preflight"]["status"] != "ready":
                raise ValueError(f"host {name} proceeds but preflight is not ready")
            if host["patch"]["status"] not in ("completed", "skipped", "empty"):
                raise ValueError(f"host {name} proceeds but patch did not complete")
            if host["verify"]["status"] != "passed":
                raise ValueError(f"host {name} proceeds but verification did not pass")

    if result["summary"]["stopped_early"]:
        recovering = [
            name for name, host in result["hosts"].items()
            if host["action"] == "recover"
        ]
        if not recovering:
            raise ValueError("rollout stopped early but no host needs recovery")
        # The recovering host should be the last one in the hosts dict
        last_host = list(result["hosts"].keys())[-1]
        if last_host not in recovering:
            raise ValueError("rollout stopped early but recovery did not run on the last recorded host")
